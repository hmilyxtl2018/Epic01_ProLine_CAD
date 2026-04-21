"""S2-T4: Quarantine 周聚合脚本 — 把 LLM 提议的候选词条整理成人审 CSV。

工作流:
  1. 扫描 quarantine 目录 (默认 exp/llm_classifications/) 下所有 *.jsonl
  2. 解析每条 propose_taxonomy_term 记录
  3. 按 (term_normalized, asset_type) 聚合: 计数 + 合并 evidence + 取最早/最晚时间戳
  4. 排序: count DESC, term ASC
  5. 输出 CSV 供人工 review (列: term, asset_type, count, evidence_samples,
     first_seen, last_seen, term_hash, decision)

输出 CSV 中 `decision` 列默认为空, 由人审填入 approve / reject / merge_with=...

人审通过的词条由后续脚本 (Phase 5) 写入 _BLOCK_ASSET_PATTERNS / 黄金词表。

用法:
    python scripts/promote_taxonomy_terms.py \
        --quarantine-dir exp/llm_classifications \
        --out exp/llm_classifications/review_$(date +%Y%m%d).csv \
        [--min-count 1]

参考:
- agents/parse_agent/tools/registry.py::propose_taxonomy_term (生产者)
- ExcPlan/parse_agent_ga_execution_plan.md §4 S2-T4
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import sys
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

log = logging.getLogger(__name__)

# 单条 evidence 在 CSV 中显示的最大数量 (避免单元格过长)
_MAX_EVIDENCE_SAMPLES = 5
# evidence 拼接分隔符 (CSV 内安全)
_EVIDENCE_JOIN = " | "


@dataclass
class Aggregated:
    """单个 (term, asset_type) 的聚合结果。"""
    term: str
    asset_type: str
    term_hash: str
    count: int = 0
    evidence: set[str] = field(default_factory=set)
    first_seen: float = float("inf")
    last_seen: float = 0.0
    runs: set[str] = field(default_factory=set)  # 来源 jsonl stem


def _normalize_term(t: str) -> str:
    """归一化 term 用作聚合 key: NFKC + 折叠大小写 + 去首尾空白。"""
    return unicodedata.normalize("NFKC", t).casefold().strip()


def iter_quarantine_records(quarantine_dir: Path) -> Iterable[tuple[str, dict]]:
    """逐行 yield (run_id, record) — 跳过损坏行并记录 warning。"""
    if not quarantine_dir.exists():
        log.warning("quarantine dir does not exist: %s", quarantine_dir)
        return
    for jsonl_file in sorted(quarantine_dir.glob("*.jsonl")):
        run_id = jsonl_file.stem
        with jsonl_file.open(encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError as exc:
                    log.warning(
                        "skip malformed line %s:%d: %s",
                        jsonl_file, lineno, exc,
                    )
                    continue
                if not isinstance(rec, dict):
                    log.warning("skip non-object %s:%d", jsonl_file, lineno)
                    continue
                yield run_id, rec


def aggregate(quarantine_dir: Path) -> dict[tuple[str, str], Aggregated]:
    """聚合所有 quarantine 记录。

    Key = (normalized_term, asset_type)。
    同一 normalized term 在不同 asset_type 下分开统计 (人审决定哪条入库)。
    """
    bucket: dict[tuple[str, str], Aggregated] = {}
    for run_id, rec in iter_quarantine_records(quarantine_dir):
        term_raw = rec.get("term")
        atype = rec.get("asset_type")
        if not isinstance(term_raw, str) or not isinstance(atype, str):
            continue
        norm = _normalize_term(term_raw)
        if not norm:
            continue
        key = (norm, atype)
        agg = bucket.get(key)
        if agg is None:
            agg = Aggregated(
                term=term_raw,
                asset_type=atype,
                term_hash=str(rec.get("term_hash", "") or ""),
            )
            bucket[key] = agg
        agg.count += 1
        for ev in rec.get("evidence", []) or []:
            if isinstance(ev, str) and ev.strip():
                agg.evidence.add(ev.strip())
        ts = rec.get("ts")
        if isinstance(ts, (int, float)):
            agg.first_seen = min(agg.first_seen, float(ts))
            agg.last_seen = max(agg.last_seen, float(ts))
        agg.runs.add(run_id)
    return bucket


def write_review_csv(
    aggregated: dict[tuple[str, str], Aggregated],
    out_path: Path,
    min_count: int = 1,
) -> int:
    """写人审 CSV。返回写入行数 (不含表头)。"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rows = [a for a in aggregated.values() if a.count >= min_count]
    rows.sort(key=lambda a: (-a.count, a.term))

    with out_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "term", "asset_type", "count", "evidence_samples",
            "first_seen", "last_seen", "run_count", "term_hash", "decision",
        ])
        for a in rows:
            ev_list = sorted(a.evidence)[:_MAX_EVIDENCE_SAMPLES]
            ev_cell = _EVIDENCE_JOIN.join(ev_list)
            writer.writerow([
                a.term,
                a.asset_type,
                a.count,
                ev_cell,
                f"{a.first_seen:.0f}" if a.first_seen != float("inf") else "",
                f"{a.last_seen:.0f}" if a.last_seen else "",
                len(a.runs),
                a.term_hash,
                "",  # decision 列待人填
            ])
    return len(rows)


def upsert_quarantine_db(
    aggregated: dict[tuple[str, str], Aggregated],
    dsn: str,
    min_count: int = 1,
    mcp_context_id: str | None = None,
) -> tuple[int, int]:
    """Dual-write aggregated rows into ``quarantine_terms``.

    Returns ``(inserted, updated)``. Already-decided rows (decision NOT NULL
    and != 'pending') are NEVER overwritten -- the partial UNIQUE keeps a
    decided row alive, so an UPSERT that would clobber a human decision is
    explicitly skipped via the WHERE clause on DO UPDATE.

    Conflict target uses the partial unique index
    ``uq_quarantine_terms_term_type_alive``
    (defined in alembic 0004_taxonomy_quarantine).
    """
    try:
        import psycopg2
        from psycopg2.extras import Json
    except ImportError as exc:  # pragma: no cover - handled at boundary
        raise RuntimeError(
            "psycopg2 is required for --db mode; install with `pip install psycopg2-binary`"
        ) from exc

    rows = [a for a in aggregated.values() if a.count >= min_count]
    inserted = 0
    updated = 0
    sql = (
        "INSERT INTO quarantine_terms "
        "(term_normalized, term_display, asset_type, count, evidence, "
        " first_seen, last_seen, decision, mcp_context_id) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, NULL, %s) "
        "ON CONFLICT (term_normalized, asset_type) "
        "WHERE deleted_at IS NULL "
        "DO UPDATE SET "
        "  count       = EXCLUDED.count, "
        "  evidence    = EXCLUDED.evidence, "
        "  last_seen   = EXCLUDED.last_seen, "
        "  term_display= EXCLUDED.term_display "
        "WHERE quarantine_terms.decision IS NULL "
        "   OR quarantine_terms.decision = 'pending' "
        "RETURNING (xmax = 0) AS was_insert"
    )
    conn = psycopg2.connect(dsn, connect_timeout=10)
    try:
        with conn.cursor() as cur:
            for a in rows:
                norm = _normalize_term(a.term)
                ev_payload = sorted(a.evidence)
                fs = (
                    datetime.fromtimestamp(a.first_seen, tz=timezone.utc)
                    if a.first_seen != float("inf")
                    else datetime.now(tz=timezone.utc)
                )
                ls = (
                    datetime.fromtimestamp(a.last_seen, tz=timezone.utc)
                    if a.last_seen
                    else fs
                )
                cur.execute(
                    sql,
                    (
                        norm,
                        a.term,
                        a.asset_type,
                        a.count,
                        Json(ev_payload),
                        fs,
                        ls,
                        mcp_context_id,
                    ),
                )
                result = cur.fetchone()
                if result is None:
                    # Conflict hit a row whose decision is already final --
                    # skip silently (audit trail preserved by NOT touching).
                    continue
                if result[0]:
                    inserted += 1
                else:
                    updated += 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        # Explicit close: psycopg2's `with connect()` only commits, leaving
        # the handle alive; that leaks idle connections across calls in the
        # same process and causes subsequent libpq handshakes to stall.
        conn.close()
    return inserted, updated


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument(
        "--quarantine-dir", type=Path,
        default=Path("exp/llm_classifications"),
        help="quarantine jsonl 目录 (默认 exp/llm_classifications/)",
    )
    parser.add_argument(
        "--out", type=Path, required=True,
        help="输出 CSV 路径 (例如 exp/llm_classifications/review_20251201.csv)",
    )
    parser.add_argument(
        "--min-count", type=int, default=1,
        help="只输出 count ≥ N 的候选 (默认 1)",
    )
    parser.add_argument(
        "--db", action="store_true",
        help="Also upsert into quarantine_terms table. "
             "Requires POSTGRES_DSN env var (or --dsn).",
    )
    parser.add_argument(
        "--dsn", type=str, default=None,
        help="Postgres DSN for --db mode. Defaults to $POSTGRES_DSN.",
    )
    parser.add_argument(
        "--mcp-context-id", type=str, default=None,
        help="Optional mcp_context_id to tag DB rows with (for audit trail).",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="打印 INFO 日志",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(message)s",
    )

    aggregated = aggregate(args.quarantine_dir)
    n = write_review_csv(aggregated, args.out, min_count=args.min_count)
    print(f"wrote {n} review rows to {args.out}", file=sys.stderr)

    if args.db:
        # psycopg2 wants the bare libpq DSN, not the SQLAlchemy URL form.
        raw_dsn = args.dsn or os.environ.get("POSTGRES_DSN", "")
        if not raw_dsn:
            print("--db requires POSTGRES_DSN env var or --dsn", file=sys.stderr)
            return 2
        dsn = raw_dsn.replace("postgresql+psycopg2://", "postgresql://", 1)
        ins, upd = upsert_quarantine_db(
            aggregated, dsn, min_count=args.min_count,
            mcp_context_id=args.mcp_context_id,
        )
        print(
            f"db: inserted={ins} updated={upd} "
            f"(skipped any rows with finalized decision)",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
