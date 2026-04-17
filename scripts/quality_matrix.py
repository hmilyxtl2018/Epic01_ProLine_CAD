"""从 exp/parse_results/run_p0_all 提取 8 个 DWG 的解析质量矩阵。"""

import json
from pathlib import Path
from collections import Counter

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = PROJECT_ROOT / "exp" / "parse_results" / "run_p0_all"

# input-id → hash mapping built from meta.json
rows = []
for d in sorted(RESULTS_DIR.iterdir()):
    if not d.is_dir():
        continue
    meta_path = d / "meta.json"
    sm_path = d / "site_model.json"
    if not meta_path.exists() or not sm_path.exists():
        continue

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    sm = json.loads(sm_path.read_text(encoding="utf-8"))

    filename = meta.get("filename", "?")
    quality = sm.get("statistics", {}).get("quality", {})
    assets = sm.get("assets", [])
    links = sm.get("links", [])

    # type distribution
    type_counter = Counter(a.get("type", "?") for a in assets)

    rows.append({
        "filename": filename,
        "hash": d.name,
        "file_bytes": meta.get("file_bytes", 0),
        "total_assets": len(assets),
        "total_links": len(links),
        "type_dist": dict(type_counter.most_common()),
        **quality,
    })

# Sort: 机加车间 first, then by filename
def sort_key(r):
    name = r["filename"]
    if "机加" in name:
        return (0, name)
    return (1, name)

rows.sort(key=sort_key)

# ── Pretty print ──
QUALITY_FIELDS = [
    "avg_confidence", "min_confidence", "max_confidence",
    "stdev_confidence", "low_confidence_count", "low_confidence_ratio",
    "classified_ratio", "verdict",
]

print("=" * 120)
print(f"{'文件':^45s} {'assets':>7s} {'links':>6s} {'avg_conf':>9s} {'min':>5s} "
      f"{'max':>5s} {'stdev':>6s} {'low_cnt':>8s} {'low_ratio':>10s} "
      f"{'cls_ratio':>10s} {'verdict':>12s}")
print("=" * 120)

for r in rows:
    print(f"{r['filename']:45s} {r['total_assets']:7d} {r['total_links']:6d} "
          f"{r.get('avg_confidence', 0):9.4f} {r.get('min_confidence', 0):5.3f} "
          f"{r.get('max_confidence', 0):5.3f} {r.get('stdev_confidence', 0):6.4f} "
          f"{r.get('low_confidence_count', 0):8d} {r.get('low_confidence_ratio', 0):10.4f} "
          f"{r.get('classified_ratio', 0):10.4f} {r.get('verdict', 'N/A'):>12s}")

print("=" * 120)

# Type distribution detail
print("\n── Asset Type 分布 ──")
for r in rows:
    dist_str = ", ".join(f"{k}:{v}" for k, v in r["type_dist"].items())
    print(f"  {r['filename']:45s} → {dist_str}")
