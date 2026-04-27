"""一键诊断"图层树→已识别 为空 / 图层为空"到底卡在哪一层。

Usage
-----
    python -m scripts.diagnose_run <run_id>
    python -m scripts.diagnose_run --latest      # 最新一条 ParseAgent run

输出按"信号衰减链"分 5 层，每层告诉你三件事：
  ✅ 数据是什么
  ❌ 如果是 0/空，根因是什么
  🔧 怎么修

5 层信号链
----------
    L0  上传校验          ← upload + format detect
    L1  ezdxf 解析         ← layer_names / block_names / entity_total
    L2  candidates 抽取     ← parse_agent 把 L1 转成 token 候选
    L3  taxonomy 匹配       ← matched (= 已识别) / quarantine
    L4  enrichment 13 步    ← A_normalize / B_softmatch / C_arbiter / ...
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

# Windows cmd 默认 GBK 输出会被 emoji ✅ ❌ ⚖ 直接打挂 — 强制 UTF-8。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

from sqlalchemy import text

from app import deps as _deps
from app.deps import init_engine


# 自动落盘 dev 默认 DSN，让脚本「干就完了」 — 不必先 source dev_up.ps1
# Lite stack (db/docker-compose.db-lite.yml) 端口 5434；Full Timescale 端口 5433。
# 你已经在跑 lite，就保持 5434；如果是 full 把环境变量自己改。
_DEV_DEFAULT_DSN = "postgresql+psycopg2://proline:proline_dev@localhost:5434/proline_cad"
if not os.getenv("POSTGRES_DSN"):
    os.environ["POSTGRES_DSN"] = _DEV_DEFAULT_DSN
    print(
        f"\033[2m[diagnose_run] POSTGRES_DSN unset — falling back to dev default "
        f"({_DEV_DEFAULT_DSN}). Override with $env:POSTGRES_DSN=... if needed.\033[0m"
    )


GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"


def _bullet(ok: bool, label: str, value: Any, hint: str = "") -> None:
    icon = f"{GREEN}✅{RESET}" if ok else f"{RED}❌{RESET}"
    val_str = json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else str(value)
    print(f"  {icon} {label:<32}{val_str}")
    if not ok and hint:
        print(f"     {YELLOW}🔧 {hint}{RESET}")


def _section(title: str) -> None:
    print(f"\n{BOLD}{CYAN}━━ {title} ━━{RESET}")


def _open_session():
    if _deps._SessionLocal is None:
        raise RuntimeError("init_engine() did not initialize _SessionLocal")
    return _deps._SessionLocal()


def diagnose(run_id: str) -> int:
    init_engine()
    with _open_session() as db:
        row = db.execute(
            text(
                """
                SELECT
                    mc.id, mc.agent, mc.status, mc.created_at,
                    mc.input_payload, mc.output_payload
                FROM mcp_contexts mc
                WHERE mc.id::text = :rid
                """
            ),
            {"rid": run_id},
        ).mappings().first()

        if not row:
            print(f"{RED}Run {run_id} not found.{RESET}")
            return 2

        ip = row["input_payload"] or {}
        op = row["output_payload"] or {}
        summary = (op.get("summary") or {})
        semantics = (op.get("semantics") or {})
        enrich = (op.get("llm_enrichment") or {})
        sections = enrich.get("sections") or {}

        # ── L0: 上传校验 ───────────────────────────────────
        _section("L0 · 上传校验 (FastAPI 入口)")
        _bullet(bool(ip.get("upload_path")), "upload_path", ip.get("upload_path") or "(missing)",
                "前端上传失败或 input_payload 没写入。重新上传。")
        _bullet(bool(ip.get("detected_format")), "detected_format", ip.get("detected_format") or "(missing)",
                "魔术字节检测失败 — 文件不是合法 dwg/dxf。换文件。")
        _bullet(row["status"] in ("FINISHED", "SUCCESS", "DONE"), "status", row["status"],
                "Run 还没跑完或者出错。先看 worker 日志。")

        # ── L1: ezdxf 解析 ────────────────────────────────
        _section("L1 · ezdxf 解析 (parse/cad_parser.py)")
        layer_names = summary.get("layer_names") or []
        block_names = summary.get("block_names") or []
        entity_total = summary.get("entity_total") or 0
        warnings = (op.get("quality") or {}).get("parse_warnings") or summary.get("warnings") or []

        _bullet(entity_total > 0, "entity_total", entity_total,
                "DXF 没有任何实体 — 文件实际是空图。原图就是空的，不是程序问题。")
        _bullet(bool(layer_names), "layer_names (非 0/Defpoints)", f"{len(layer_names)} 条 → {layer_names[:5]}",
                "所有内容都画在了 \"0\" 图层（很常见！）。这不是 bug — _parse_dxf 把 \"0\" 和 \"Defpoints\" 主动过滤了。"
                " 想让 \"0\" 图层也参与识别 → 改 app/services/parse/cad_parser.py 的过滤白名单。")
        _bullet(bool(block_names), "block_names", f"{len(block_names)} 条 → {block_names[:5]}",
                "DWG 没有任何块定义 — 通常意味着这是纯几何手画图，没有可识别的 INSERT 实体。"
                " 仍然能跑，只是 candidates 只能从 layer_names 来。")
        _bullet(not warnings, "warnings", warnings or "[]",
                "有解析警告。看 dwg_parser_unavailable / dxf_structure_error 等具体值。")

        # ── L2: candidates 抽取 ────────────────────────────
        _section("L2 · candidates 抽取 (从 L1 的 layer/block 名生成 token 候选)")
        cand_count = semantics.get("candidate_count") or len(semantics.get("candidates") or [])
        # 兜底：worker 把 candidate 划进 matched/quarantine 后 candidate_count 字段
        # 不一定回填，可能是 0；用 matched+quarantine 反推真实候选数。
        matched_count_for_l2 = semantics.get("matched_terms_count") or 0
        quar_count_for_l2 = semantics.get("quarantine_terms_count") or 0
        effective_cand = cand_count or (matched_count_for_l2 + quar_count_for_l2)
        _bullet(effective_cand > 0, "候选总数（含 matched+quarantine）", effective_cand,
                "L1 给的 layer/block 名经清洗后全部为空（纯数字、过短、纯特殊字符）。"
                " 检查 _extract_candidates(): app/services/parse/cad_parser.py")
        if cand_count == 0 and effective_cand > 0:
            print(f"     {DIM}注：semantics.candidate_count={cand_count} 但 matched+quarantine={effective_cand} —"
                  f" worker 没回填 candidate_count 字段，这是 bookkeeping bug，不影响业务。{RESET}")

        # ── L3: taxonomy 匹配（已识别 = matched_terms）────
        _section("L3 · taxonomy 匹配（已识别 = matched_terms）")
        matched_count = semantics.get("matched_terms_count") or 0
        quar_count = semantics.get("quarantine_terms_count") or 0

        # taxonomy_terms 表里 gold 数量
        gold_count = db.execute(
            text(
                "SELECT COUNT(*) FROM taxonomy_terms "
                "WHERE deleted_at IS NULL AND source IN ('gold','llm_promoted','manual')"
            )
        ).scalar() or 0

        _bullet(gold_count > 0, "taxonomy_terms (gold) 总数", gold_count,
                "★ 这是最常见的根因 ★ — taxonomy_terms 表里没有 gold 词条。"
                " 解决：python scripts/sync_corpus_to_minio.py  或重新跑 corpus/seeds.yaml 同步。"
                " 没有 gold，所有 candidate 都进 quarantine，'已识别' 永远是 0。")
        _bullet(matched_count > 0, "matched_terms_count (='已识别')", matched_count,
                "candidate 在 taxonomy_terms 里一个都没匹中。要么 gold 是空（看上一行），"
                " 要么这次 DWG 用的命名不在 corpus/seeds.yaml 覆盖范围内。")
        _bullet(True, "quarantine_terms_count", quar_count)  # 信息性

        # ── L4: enrichment 13 步 ──────────────────────────
        _section("L4 · enrichment pipeline（A→M 13 步）")
        steps_run = enrich.get("steps_run") or []
        timings = enrich.get("timings_ms") or {}
        errors = enrich.get("errors") or {}

        _bullet(bool(steps_run), "steps_run 数量", len(steps_run) or 0,
                "enrichment 整个没跑。看 mcp_contexts.output_payload.errors，"
                " 多半是 embedder / db 连接 / corpus 读取失败。")

        for step in ("A_normalize", "B_softmatch", "C_arbiter", "D_cluster_proposals", "K_asset_extract"):
            sec = sections.get(step) or {}
            err = errors.get(step)
            if err:
                print(f"  {RED}❌ {step:<24}ERROR: {err.splitlines()[0]}{RESET}")
                continue
            if step == "A_normalize":
                items = sec.get("items") or []
                stats = sec.get("stats") or {}
                _bullet(stats.get("input", 0) > 0, f"  {step}.input", stats.get("input"),
                        "A 没收到 candidates → L2 输出为空（看上面 L2 行）。")
                _bullet(len(items) > 0, f"  {step}.items[]", len(items))
            elif step == "B_softmatch":
                stats = sec.get("stats") or {}
                _bullet(stats.get("gold_size", 0) > 0, f"  {step}.gold_size", stats.get("gold_size"),
                        "★ B 拿不到 gold ★ — taxonomy_terms 是空（看 L3 第 1 行）。"
                        " B 是 '已识别' 的核心算子；gold=0 → matches=[] → C promote=0。")
                _bullet(stats.get("input", 0) > 0, f"  {step}.input (quarantine)", stats.get("input"),
                        "quarantine_terms 是空 → 没东西可以做软匹配。")
                _bullet(stats.get("produced", 0) > 0, f"  {step}.produced", stats.get("produced"),
                        "embedder 没产出任何相似度 → 看 LLM_PROVIDER 环境变量；"
                        " stub embedder 不会失败，但 openai 没 key 会静默回 0。")
            elif step == "C_arbiter":
                counts = sec.get("counts") or {}
                pc = sec.get("promotion_candidates") or []
                _bullet(counts.get("promote", 0) > 0,
                        f"  {step}.counts.promote (=最终已识别)", counts.get("promote"),
                        "B 给的 matches 没一个跨过 0.86 阈值。看 B.thresholds.accept；"
                        " 多半要么 corpus 词太少（<50），要么命名差异太大。")
                print(f"     {DIM}counts: {counts}{RESET}")
                if pc:
                    print(f"     {DIM}promotion_candidates 样例: {[p.get('term_normalized') or p.get('best_match') for p in pc[:3]]}{RESET}")
            elif step == "D_cluster_proposals":
                proposals = sec.get("proposals") or []
                _bullet(len(proposals) > 0, f"  {step}.proposals", len(proposals),
                        "quarantine 不足 / 太散 → 聚不出 cluster。这在 quarantine<5 时是正常的。")
            elif step == "K_asset_extract":
                assets = sec.get("assets") or []
                _bullet(len(assets) > 0, f"  {step}.assets", len(assets),
                        "K 是从 matched_terms 派生 asset 的。matched=0 → assets=0。")

        # ── 综合诊断 ────────────────────────────────────
        _section("⚖ 综合诊断（最可能的单点根因）")
        b_section = sections.get("B_softmatch") or {}
        b_gold_size = (b_section.get("stats") or {}).get("gold_size", 0)

        if entity_total == 0:
            print(f"  {RED}● 原图就是空的（entity_total=0）。这是文件问题，不是程序问题。{RESET}")
        elif not layer_names and not block_names:
            print(f"  {RED}● DWG 所有内容都画在 '0' 图层 + 没有 BLOCK 定义。{RESET}")
            print(f"  {YELLOW}  这是文件问题（设计师没规范分层）。但程序也可以更宽容 — 把 '0' 加入候选。{RESET}")
        elif gold_count > 0 and b_gold_size == 0:
            print(f"  {RED}● ★ 时序错位 ★ 这次 run 跑的时候 taxonomy_terms 还没初始化（B 拿到 gold_size=0），"
                  f"但现在表里已经有 {gold_count} 条 gold。{RESET}")
            print(f"  {YELLOW}  解决：删掉这个 run，重新上传同一份文件 — Worker 这次能拿到 gold 了。{RESET}")
            print(f"     在 dashboard 点删除 → 重新拖文件，1 分钟搞定。")
        elif gold_count == 0:
            print(f"  {RED}● ★ 最可能的根因 ★ taxonomy_terms 表是空的。{RESET}")
            print(f"  {YELLOW}  这是程序问题（corpus 没初始化）。修复：{RESET}")
            print(f"     python -m scripts.sync_corpus_to_minio")
            print(f"     或重新执行 alembic upgrade + 启动时 init seeder。")
        elif effective_cand > 0 and matched_count == 0:
            print(f"  {YELLOW}● 候选有 {effective_cand} 条，但一个都没命中 gold（共 {gold_count} 条）。{RESET}")
            # 看看 layer / block 命名长什么样，给文件 vs 程序的判定
            anonymous_blocks = sum(1 for b in block_names if b.startswith(("A$", "*")))
            numeric_blocks = sum(1 for b in block_names if b and b[1:].isdigit() and len(b) <= 4)
            generic_layers = [
                ln for ln in layer_names
                if ln.lower() in {"hatch", "0", "defpoints"} or "." in ln or len(ln) < 3
            ]
            file_smell = (
                anonymous_blocks > len(block_names) * 0.5
                or numeric_blocks > len(block_names) * 0.5
                or len(generic_layers) >= len(layer_names) * 0.5
            )
            if file_smell:
                print(f"  {RED}  → 这是文件问题。命名特征：{RESET}")
                print(f"  {DIM}    匿名 block (A$/*): {anonymous_blocks}/{len(block_names)}")
                print(f"    纯数字 block (D0/D1/...): {numeric_blocks}/{len(block_names)}")
                print(f"    通用图层 (hatch/dwgmodels.com/系统图层): {generic_layers}{RESET}")
                print(f"  {YELLOW}  这种 DXF 通常是从 dwgmodels.com / GrabCAD 等图库下载的样图，没有业务语义。{RESET}")
                print(f"  {YELLOW}  解决：用真实工厂图（中文 '清洗机/珩磨机/缸盖装配' 或 英文 'HARDING/EXTAR/Landis'）。{RESET}")
            else:
                print(f"  {YELLOW}  这通常是文件问题（命名规范和 corpus 不一致），但 corpus 也可能太薄。{RESET}")
                sample = (semantics.get("candidates") or [])[:8]
                if sample:
                    print(f"  {DIM}  candidate 样例: {[c.get('term_normalized') for c in sample]}{RESET}")
        elif matched_count > 0:
            print(f"  {GREEN}● 数据链条正常 — '已识别'={matched_count}。如果 UI 仍显示空，看前端：{RESET}")
            print(f"     web/src/app/sites/[runId]/page.tsx 是否在读 enrich.sections.C_arbiter.promotion_candidates")
            print(f"     还是在读 output_payload.semantics.matched_terms。两者口径有差。")
        else:
            print(f"  {YELLOW}● 信号链有断点但不在常见位置。逐行回看上面 L0–L4。{RESET}")

        # 友好提示
        print(f"\n{DIM}查看完整 enrichment JSON：psql → SELECT output_payload->'llm_enrichment' FROM mcp_contexts WHERE id='{run_id}';{RESET}\n")
        return 0


def _resolve_latest() -> str:
    init_engine()
    with _open_session() as db:
        row = db.execute(
            text(
                "SELECT id FROM mcp_contexts WHERE agent='ParseAgent' "
                "AND deleted_at IS NULL ORDER BY created_at DESC LIMIT 1"
            )
        ).first()
        if not row:
            print(f"{RED}No ParseAgent run found.{RESET}", file=sys.stderr)
            sys.exit(2)
        return str(row[0])


def main() -> int:
    p = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    p.add_argument("run_id", nargs="?", help="mcp_contexts.id; omit with --latest")
    p.add_argument("--latest", action="store_true", help="diagnose the most recent ParseAgent run")
    args = p.parse_args()

    if args.latest:
        run_id = _resolve_latest()
        print(f"{DIM}Latest run: {run_id}{RESET}")
    elif args.run_id:
        run_id = args.run_id
    else:
        p.error("provide run_id or --latest")
        return 2

    return diagnose(run_id)


if __name__ == "__main__":
    sys.exit(main())
