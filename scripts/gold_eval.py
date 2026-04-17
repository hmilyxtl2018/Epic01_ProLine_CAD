"""Gold-tier evaluation for ParseAgent output against hand-annotated ground truth.

用法:
  python scripts/gold_eval.py --gold agents/parse_agent/gold/jijia_gold.yaml \
      --site-model exp/parse_results/run_p0_all/66861c26/site_model.json
  python scripts/gold_eval.py --run-dir exp/parse_results/run_p0_all/66861c26   # 自动推断
  python scripts/gold_eval.py --baseline old_gold.json  # regression 模式

输出 (JSON):
  {
    "classification": {strict_accuracy, loose_accuracy, per_type_precision_recall, ...},
    "aggregate_ranges": {type -> {actual, expected_range, in_range}},
    "link_ranges": {...},
    "block_details": [{block, expected_type, actual_types, strict_hits, loose_hits, count_actual, count_expected, ...}],
    "gold_score": 0.xxx,
    "summary": "human-readable text"
  }
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

# Windows GBK stdout → UTF-8 wrapper (防止 emoji/中文/bullets 崩溃)
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required. pip install pyyaml", file=sys.stderr)
    sys.exit(2)


# ────────────────────────────────────────────────────────────────────
# Loading
# ────────────────────────────────────────────────────────────────────
def load_gold(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_site_model(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


# ────────────────────────────────────────────────────────────────────
# Block-level classification
# ────────────────────────────────────────────────────────────────────
def evaluate_block_classification(gold: dict, assets: list[dict]) -> dict:
    """Per-block expected vs actual. 'Ambiguous' blocks excluded from strict P/R."""
    block_ann: dict = gold.get("block_annotations", {})

    # asset -> (block_name, type, confidence)
    by_block: dict[str, list[dict]] = defaultdict(list)
    for a in assets:
        bn = a.get("block_name")
        if bn:
            by_block[bn].append(a)

    block_details = []
    strict_hits_total = 0
    loose_hits_total = 0
    scored_total = 0  # 非 Ambiguous 的 annotated block 实例数
    low_conf_total = 0

    # 用于 per-type P/R
    per_type_tp: Counter = Counter()
    per_type_fp: Counter = Counter()
    per_type_fn: Counter = Counter()

    for block_name, spec in block_ann.items():
        expected = spec.get("expected_type")
        alt = set(spec.get("acceptable_alt") or [])
        conf_min = float(spec.get("confidence_min", 0.0))
        expected_count = spec.get("count")

        instances = by_block.get(block_name, [])
        actual_types = Counter(i.get("type", "Other") for i in instances)
        actual_count = len(instances)

        strict_hits = sum(1 for i in instances if i.get("type") == expected)
        loose_hits = sum(
            1 for i in instances if i.get("type") == expected or i.get("type") in alt
        )
        low_conf = sum(1 for i in instances if (i.get("confidence") or 0.0) < conf_min)

        count_ok = (expected_count is None) or (
            abs(actual_count - expected_count) <= max(2, expected_count * 0.05)
        )

        if expected == "Ambiguous":
            # 不计入分类准确率, 也不统计 FP/FN
            pass
        else:
            scored_total += actual_count
            strict_hits_total += strict_hits
            loose_hits_total += loose_hits
            low_conf_total += low_conf

            # P/R (per expected type)
            per_type_tp[expected] += strict_hits
            per_type_fn[expected] += actual_count - strict_hits
            for t, c in actual_types.items():
                if t != expected:
                    per_type_fp[t] += c

        block_details.append({
            "block": block_name,
            "expected_type": expected,
            "acceptable_alt": sorted(alt),
            "actual_types": dict(actual_types),
            "count_actual": actual_count,
            "count_expected": expected_count,
            "count_ok": count_ok,
            "strict_hits": strict_hits,
            "loose_hits": loose_hits,
            "strict_accuracy": (strict_hits / actual_count) if actual_count else None,
            "loose_accuracy": (loose_hits / actual_count) if actual_count else None,
            "low_confidence_count": low_conf,
        })

    # per-type P/R
    per_type_pr = {}
    all_types = set(per_type_tp) | set(per_type_fp) | set(per_type_fn)
    for t in sorted(all_types):
        tp = per_type_tp[t]
        fp = per_type_fp[t]
        fn = per_type_fn[t]
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (
            2 * precision * recall / (precision + recall)
            if (precision + recall) > 0
            else 0.0
        )
        per_type_pr[t] = {
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
        }

    macro_f1 = (
        sum(x["f1"] for x in per_type_pr.values()) / len(per_type_pr)
        if per_type_pr
        else 0.0
    )

    return {
        "scored_instances": scored_total,
        "strict_accuracy": (strict_hits_total / scored_total) if scored_total else 0.0,
        "loose_accuracy": (loose_hits_total / scored_total) if scored_total else 0.0,
        "low_confidence_rate": (low_conf_total / scored_total) if scored_total else 0.0,
        "per_type": per_type_pr,
        "macro_f1": round(macro_f1, 4),
        "block_details": block_details,
    }


# ────────────────────────────────────────────────────────────────────
# Aggregate type-count ranges
# ────────────────────────────────────────────────────────────────────
def evaluate_aggregate_ranges(gold: dict, assets: list[dict]) -> dict:
    expected: dict = gold.get("expected_type_counts", {})
    actual_counts = Counter(a.get("type", "Other") for a in assets)

    result: dict[str, dict] = {}
    hits = 0
    total = 0
    for t, rng in expected.items():
        lo = rng.get("min", 0)
        hi = rng.get("max", 10**9)
        act = actual_counts.get(t, 0)
        in_range = lo <= act <= hi
        if in_range:
            hits += 1
        total += 1
        result[t] = {
            "actual": act,
            "min": lo,
            "max": hi,
            "in_range": in_range,
        }
    return {
        "per_type": result,
        "pass_rate": (hits / total) if total else 0.0,
        "actual_counts": dict(actual_counts),
    }


# ────────────────────────────────────────────────────────────────────
# Link count ranges
# ────────────────────────────────────────────────────────────────────
def evaluate_link_ranges(gold: dict, links: list[dict]) -> dict:
    expected: dict = gold.get("expected_link_counts", {})
    actual_counts = Counter(l.get("link_type", "?") for l in links)

    result: dict[str, dict] = {}
    hits = 0
    total = 0
    for t, rng in expected.items():
        lo = rng.get("min", 0)
        hi = rng.get("max", 10**9)
        act = actual_counts.get(t, 0)
        in_range = lo <= act <= hi
        if in_range:
            hits += 1
        total += 1
        result[t] = {
            "actual": act,
            "min": lo,
            "max": hi,
            "in_range": in_range,
        }
    return {
        "per_type": result,
        "pass_rate": (hits / total) if total else 0.0,
        "actual_counts": dict(actual_counts),
    }


# ────────────────────────────────────────────────────────────────────
# Layer purity (optional, from gold.layer_annotations)
# ────────────────────────────────────────────────────────────────────
def evaluate_layer_annotations(gold: dict, assets: list[dict]) -> dict:
    expected: dict = gold.get("layer_annotations", {})
    if not expected:
        return {"per_layer": {}, "pass_rate": 1.0}

    by_layer: dict[str, list[dict]] = defaultdict(list)
    for a in assets:
        by_layer[a.get("layer", "")].append(a)

    result: dict[str, dict] = {}
    hits = 0
    total = 0
    for lname, spec in expected.items():
        dom = spec.get("dominant_type")
        purity_min = float(spec.get("expected_purity", 0.0))
        entries = by_layer.get(lname, [])
        if not entries:
            result[lname] = {"present": False, "dominant_actual": None, "purity": 0.0, "ok": False}
            total += 1
            continue
        tc = Counter(a.get("type", "Other") for a in entries)
        top, top_n = tc.most_common(1)[0]
        purity = top_n / len(entries)
        dominant_ok = (dom is None) or (top == dom)
        purity_ok = purity >= purity_min
        ok = dominant_ok and purity_ok
        if ok:
            hits += 1
        total += 1
        result[lname] = {
            "present": True,
            "dominant_expected": dom,
            "dominant_actual": top,
            "purity": round(purity, 3),
            "purity_min": purity_min,
            "dominant_ok": dominant_ok,
            "purity_ok": purity_ok,
            "ok": ok,
            "count": len(entries),
        }
    return {"per_layer": result, "pass_rate": (hits / total) if total else 1.0}


# ────────────────────────────────────────────────────────────────────
# Master scorer
# ────────────────────────────────────────────────────────────────────
def compute_gold_score(cls: dict, agg: dict, links: dict, layers: dict) -> float:
    """0.40 loose_accuracy + 0.25 macro_f1 + 0.20 aggregate_pass + 0.10 links_pass + 0.05 layer_pass"""
    return round(
        0.40 * cls["loose_accuracy"]
        + 0.25 * cls["macro_f1"]
        + 0.20 * agg["pass_rate"]
        + 0.10 * links["pass_rate"]
        + 0.05 * layers["pass_rate"],
        4,
    )


# ────────────────────────────────────────────────────────────────────
# Formatting
# ────────────────────────────────────────────────────────────────────
def render_summary(report: dict) -> str:
    lines = []
    c = report["classification"]
    lines.append("=" * 70)
    lines.append(f"Gold Evaluation — {report['meta']['gold_file']}")
    lines.append(f"Site Model: {report['meta']['site_model']}")
    lines.append("=" * 70)
    lines.append("")
    lines.append("[Classification — Named Blocks]")
    lines.append(
        f"  Scored instances:   {c['scored_instances']}  "
        f"(Ambiguous blocks excluded)"
    )
    lines.append(f"  Strict accuracy:    {c['strict_accuracy']:.3f}")
    lines.append(f"  Loose accuracy:     {c['loose_accuracy']:.3f}  (with acceptable_alt)")
    lines.append(f"  Macro F1:           {c['macro_f1']:.3f}")
    lines.append(f"  Low-confidence:     {c['low_confidence_rate']:.3f}  (below block.confidence_min)")
    lines.append("")
    lines.append("  Per-type P/R/F1:")
    for t, pr in c["per_type"].items():
        lines.append(
            f"    {t:<15} P={pr['precision']:.3f}  R={pr['recall']:.3f}  "
            f"F1={pr['f1']:.3f}  (tp={pr['tp']}, fp={pr['fp']}, fn={pr['fn']})"
        )
    lines.append("")

    agg = report["aggregate_ranges"]
    lines.append("[Aggregate Type Counts]")
    lines.append(f"  Pass rate: {agg['pass_rate']:.3f}")
    for t, d in agg["per_type"].items():
        flag = "OK" if d["in_range"] else "FAIL"
        lines.append(f"  [{flag:4}] {t:<15} actual={d['actual']}  range=[{d['min']},{d['max']}]")
    lines.append("")

    lnk = report["link_ranges"]
    lines.append("[Link Counts]")
    lines.append(f"  Pass rate: {lnk['pass_rate']:.3f}")
    for t, d in lnk["per_type"].items():
        flag = "OK" if d["in_range"] else "FAIL"
        lines.append(f"  [{flag:4}] {t:<15} actual={d['actual']}  range=[{d['min']},{d['max']}]")
    lines.append("")

    lay = report["layer_annotations"]
    if lay["per_layer"]:
        lines.append("[Layer Purity]")
        lines.append(f"  Pass rate: {lay['pass_rate']:.3f}")
        for name, d in lay["per_layer"].items():
            flag = "OK" if d.get("ok") else "FAIL"
            dominant = d.get("dominant_actual") or "-"
            lines.append(
                f"  [{flag:4}] {name:<12} dominant={dominant}  purity={d.get('purity', 0):.2f}"
            )
        lines.append("")

    lines.append("[Block Details — Bottom-10 by loose_accuracy]")
    worst = sorted(
        [b for b in c["block_details"] if b["expected_type"] != "Ambiguous" and b["count_actual"]],
        key=lambda x: (x["loose_accuracy"] or 0, -x["count_actual"]),
    )[:10]
    for b in worst:
        la = b["loose_accuracy"]
        la_s = f"{la:.2f}" if la is not None else "n/a"
        actual_top = (
            max(b["actual_types"].items(), key=lambda kv: kv[1])[0]
            if b["actual_types"]
            else "-"
        )
        lines.append(
            f"  {b['block']:<24} expect={b['expected_type']:<12} "
            f"got={actual_top:<10} n={b['count_actual']:<4} loose={la_s}"
        )
    lines.append("")

    lines.append(f"[GOLD SCORE] {report['gold_score']:.4f}")
    lines.append("")
    return "\n".join(lines)


# ────────────────────────────────────────────────────────────────────
# Main
# ────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", default="agents/parse_agent/gold/jijia_gold.yaml")
    ap.add_argument("--site-model", help="Path to site_model.json")
    ap.add_argument("--run-dir", help="Directory containing site_model.json (alternative to --site-model)")
    ap.add_argument("--output", help="Write full report as JSON to this path")
    ap.add_argument("--baseline", help="Baseline gold-eval JSON for regression comparison")
    ap.add_argument("--regression-threshold", type=float, default=0.02,
                    help="gold_score drop greater than this → exit 1 (default 0.02)")
    ap.add_argument("--quiet", action="store_true", help="Only print gold_score line")
    args = ap.parse_args()

    gold_path = Path(args.gold)
    if not gold_path.is_absolute():
        gold_path = Path.cwd() / gold_path

    if args.site_model:
        sm_path = Path(args.site_model)
    elif args.run_dir:
        sm_path = Path(args.run_dir) / "site_model.json"
    else:
        print("ERROR: must provide --site-model or --run-dir", file=sys.stderr)
        sys.exit(2)

    gold = load_gold(gold_path)
    sm = load_site_model(sm_path)
    assets = sm.get("assets", [])
    links = sm.get("links", [])

    cls = evaluate_block_classification(gold, assets)
    agg = evaluate_aggregate_ranges(gold, assets)
    lnk = evaluate_link_ranges(gold, links)
    lay = evaluate_layer_annotations(gold, assets)
    score = compute_gold_score(cls, agg, lnk, lay)

    report = {
        "meta": {
            "gold_file": str(gold_path.name),
            "site_model": str(sm_path),
            "cad_source": sm.get("cad_source"),
            "total_assets": len(assets),
            "total_links": len(links),
            "gold_filename": gold.get("filename"),
        },
        "classification": cls,
        "aggregate_ranges": agg,
        "link_ranges": lnk,
        "layer_annotations": lay,
        "gold_score": score,
    }

    if args.output:
        Path(args.output).write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    if args.quiet:
        print(f"gold_score={score}")
    else:
        print(render_summary(report))

    # Regression check
    if args.baseline:
        base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
        base_score = base.get("gold_score", 0.0)
        delta = score - base_score
        print(f"[Regression] baseline={base_score:.4f}  current={score:.4f}  delta={delta:+.4f}")
        if delta < -args.regression_threshold:
            print(
                f"REGRESSION: gold_score dropped by {-delta:.4f} "
                f"(threshold {args.regression_threshold})",
                file=sys.stderr,
            )
            sys.exit(1)


if __name__ == "__main__":
    main()
