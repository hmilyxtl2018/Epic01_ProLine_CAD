"""LLM 质量评估矩阵 — 对 8 个 DWG 逐一调用 LLM 打分。

用法:
    $env:ANTHROPIC_AUTH_TOKEN = "sk-..."
    $env:ANTHROPIC_BASE_URL   = "https://xiaoai.plus"
    $env:ANTHROPIC_MODEL      = "claude-opus-4-6"
    python scripts/quality_matrix_llm.py

输出:
    1. 控制台质量矩阵表格
    2. exp/parse_results/run_p0_all/llm_quality_matrix.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from agents.parse_agent.llm_quality import LLMQualityEvaluator, ECoTResult

RESULTS_DIR = PROJECT_ROOT / "exp" / "parse_results" / "run_p0_all"

DIMS = [
    "classification_accuracy", "confidence_calibration",
    "coverage", "semantic_richness", "actionability", "overall",
]


def load_results() -> list[tuple[dict, dict]]:
    pairs = []
    for d in sorted(RESULTS_DIR.iterdir()):
        if not d.is_dir():
            continue
        meta_p = d / "meta.json"
        sm_p = d / "site_model.json"
        if not meta_p.exists() or not sm_p.exists():
            continue
        meta = json.loads(meta_p.read_text(encoding="utf-8"))
        sm = json.loads(sm_p.read_text(encoding="utf-8"))
        pairs.append((meta, sm))

    def key(p):
        n = p[0].get("filename", "")
        return (0, n) if "机加" in n else (1, n)
    pairs.sort(key=key)
    return pairs


def main():
    parser = argparse.ArgumentParser(description="LLM 质量评估矩阵")
    parser.add_argument(
        "--runs", type=int, default=1,
        help="每个文件重复评估次数，维度分数取均值（默认 1；建议 3 降噪）",
    )
    parser.add_argument(
        "--resume", action="store_true",
        help="跳过 llm_quality_matrix.json 里已成功评估且 runs 达标的文件",
    )
    parser.add_argument(
        "--only", type=str, default="",
        help="仅评估 filename 子串匹配的文件（逗号分隔多项）",
    )
    args = parser.parse_args()
    runs = max(1, args.runs)

    evaluator = LLMQualityEvaluator()
    pairs = load_results()

    # --only 过滤
    only_filters = [s.strip() for s in args.only.split(",") if s.strip()]
    if only_filters:
        pairs = [p for p in pairs if any(f in p[0].get("filename", "") for f in only_filters)]

    # --resume: 读取已有 matrix.json
    out_path = RESULTS_DIR / "llm_quality_matrix.json"
    existing: dict[str, dict] = {}
    if args.resume and out_path.exists():
        try:
            for r in json.loads(out_path.read_text(encoding="utf-8")):
                if r.get("runs", 0) >= runs and r.get("overall", -1) >= 0:
                    existing[r["filename"]] = r
        except Exception as exc:
            print(f"警告: 无法读取已有 matrix.json ({exc})，将重新评估", flush=True)

    print(f"找到 {len(pairs)} 个解析结果，开始 LLM 评估（runs={runs}，resume={args.resume}，已跳过={len(existing)}）…\n")

    # DIMENSION_WEIGHTS 用于均值后重新计算 overall
    from agents.parse_agent.llm_quality import DIMENSION_WEIGHTS

    rows: list[dict] = list(existing.values())  # 预填已完成
    for meta, sm in pairs:
        if meta.get("filename", "") in existing:
            print(f"[SKIP] {meta['filename']} (resume)", flush=True)
            continue
        name = meta.get("filename", "?")
        print(f"[LLM ] {name} ×{runs} …", flush=True)

        run_results: list[ECoTResult] = []
        run_scores_per_dim: dict[str, list[float]] = {d: [] for d in DIMS if d != "overall"}
        t0 = time.perf_counter()
        err_msg = ""
        for i in range(runs):
            try:
                result: ECoTResult = evaluator.evaluate(sm, meta)
                run_results.append(result)
                for d in run_scores_per_dim:
                    run_scores_per_dim[d].append(getattr(result.score, d))
                print(f"    run {i+1}/{runs}: overall={result.score.overall:.3f}", flush=True)
            except Exception as exc:
                err_msg = str(exc)
                print(f"    run {i+1}/{runs} ERROR: {exc}", flush=True)
                break
        dt = time.perf_counter() - t0

        if not run_results:
            row = {
                "filename": name,
                "assets": len(sm.get("assets", [])),
                "links":  len(sm.get("links", [])),
                "rule_verdict": "?",
                **{d: -1.0 for d in DIMS},
                "error": err_msg or "no runs completed",
                "runs": 0,
            }
            rows.append(row)
            continue

        # 均值 + stdev
        dim_mean = {d: round(statistics.fmean(v), 4) for d, v in run_scores_per_dim.items()}
        dim_stdev = {
            d: round(statistics.pstdev(v), 4) if len(v) > 1 else 0.0
            for d, v in run_scores_per_dim.items()
        }
        overall_mean = round(
            sum(DIMENSION_WEIGHTS[d] * dim_mean[d] for d in DIMENSION_WEIGHTS),
            4,
        )

        # 以最后一轮作为“代表”结果，提供 judgments/evidence/verification 细节
        last = run_results[-1]
        score = last.score

        print(
            f"    → {dt:.1f}s, means: " +
            ", ".join(f"{d[:5]}={dim_mean[d]:.2f}±{dim_stdev[d]:.2f}" for d in dim_mean) +
            f", overall={overall_mean:.3f}"
        )

        v_confirmed = sum(1 for v in last.verification if v.verdict == "CONFIRMED")
        v_contra = sum(1 for v in last.verification if v.verdict == "CONTRADICTED")
        v_unverif = sum(1 for v in last.verification if v.verdict == "UNVERIFIABLE")
        print(f"    verification (last run): {v_confirmed} confirmed, {v_contra} contradicted, {v_unverif} unverifiable")
        print(f"    sampling: {last.sample_size}/{last.total_assets} ({last.sampling_coverage:.1%})")

        meta_conf = {n: j.confidence for n, j in score.judgments.items()}

        row = {
            "filename": name,
            "assets": len(sm.get("assets", [])),
            "links":  len(sm.get("links", [])),
            "rule_verdict": sm.get("statistics", {}).get("quality", {}).get("verdict", "?"),
            # 均值分数（维度 + overall）
            **dim_mean,
            "overall": overall_mean,
            # 降噪指标
            "runs": len(run_results),
            "score_stdev": dim_stdev,
            "run_scores": run_scores_per_dim,
            # 代表轮详情
            "meta_confidence": meta_conf,
            "missed_types": score.missed_types,
            "suspicious_assets": score.suspicious_assets,
            "recommendations": score.recommendations,
            "judgments": {
                dim_name: {
                    "score": j.score,
                    "confidence": j.confidence,
                    "evidence_ids": j.evidence_ids,
                    "observation": j.observation,
                    "inference": j.inference,
                    "uncertainty": j.uncertainty,
                }
                for dim_name, j in score.judgments.items()
            },
            "evidence": [{"id": e.id, "category": e.category, "fact": e.fact} for e in last.evidence],
            "verification": [
                {"claim": v.claim, "verdict": v.verdict, "detail": v.detail}
                for v in last.verification
            ],
            "sampling_coverage": last.sampling_coverage,
        }
        rows.append(row)

        # 增量持久化: 每个文件完成后立即写 matrix.json,防止后续挂起丢数据
        try:
            out_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:
            print(f"    警告: 增量写入失败 ({exc})", flush=True)

    # ── 表格 ──
    hdr_dims = " ".join(f"{d[:7]:>7s}" for d in DIMS)
    print("\n" + "=" * 130)
    print(f"{'文件':^40s} {'assets':>7s} {'links':>6s} {'rule':>12s} {hdr_dims}")
    print("=" * 130)
    for r in rows:
        vals = " ".join(f"{r.get(d, -1):7.2f}" for d in DIMS)
        print(f"{r['filename']:40s} {r['assets']:7d} {r['links']:6d} {r['rule_verdict']:>12s} {vals}")
    print("=" * 130)

    # ── Detail ──
    print("\n── LLM 发现的缺失类型 ──")
    for r in rows:
        missed = r.get("missed_types", [])
        if missed:
            print(f"  {r['filename']:40s} → {', '.join(missed)}")

    print("\n── LLM 改进建议 ──")
    for r in rows:
        recs = r.get("recommendations", [])
        if recs:
            print(f"  {r['filename']}:")
            for rec in recs:
                print(f"    • {rec}")

    print("\n── LLM 推理摘要 (per-dimension) ──")
    for r in rows:
        judgments = r.get("judgments", {})
        if judgments:
            print(f"  {r['filename']}:")
            for dim_name, j in judgments.items():
                obs = j.get("observation", "")[:120]
                conf = j.get("confidence", 0)
                eids = ", ".join(j.get("evidence_ids", []))
                print(f"    [{dim_name[:12]:12s}] score={j.get('score',0):.2f} conf={conf:.2f} evidence=[{eids}]")
                if obs:
                    print(f"      observation: {obs}{'…' if len(j.get('observation',''))>120 else ''}")

    # ── Verification ──
    print("\n── 后验验证 ──")
    for r in rows:
        verifs = r.get("verification", [])
        contradicted = [v for v in verifs if v.get("verdict") == "CONTRADICTED"]
        if contradicted:
            print(f"  {r['filename']} — {len(contradicted)} CONTRADICTED:")
            for v in contradicted:
                print(f"    ✗ {v['claim']}: {v['detail']}")
        else:
            print(f"  {r['filename']} — all claims verified or unverifiable")

    # ── Persist ──
    out = out_path
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n结果已保存: {out.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
