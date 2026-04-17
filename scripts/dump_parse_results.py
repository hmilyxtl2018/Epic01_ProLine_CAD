"""批量运行 ParseAgent 全管线，持久化 8 个 DWG 的解析结果。

用法:
    python -m scripts.dump_parse_results
"""

from pathlib import Path
import time

from agents.parse_agent.service import ParseService
from agents.parse_agent.result_store import ParseResultWriter

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REAL_WORLD = PROJECT_ROOT / "spikes" / "spike_01_dwg_parse" / "test_data" / "real_world"

DWG_FILES = [
    "example_2000.dwg",               # IN-DWG-006  G-VER-2000
    "example_2007.dwg",               # IN-DWG-007  G-VER-2007
    "example_2018.dwg",               # IN-DWG-008  G-VER-2018
    "20180109_机加车间平面布局图.dwg",   # IN-DWG-001  G-P0-BASE-01
    "cold_rolled_steel_production.dwg",# IN-DWG-003  G-P0-BASE-02
    "fish_processing_plant.dwg",       # IN-DWG-002  G-SIZE-L
    "woodworking_plant.dwg",           # IN-DWG-004  G-SIZE-S
    "woodworking_factory_1.dwg",       # IN-DWG-005  G-SIZE-M
]

RUN_ID = "run_p0_all"


def main():
    svc = ParseService()
    writer = ParseResultWriter(base_dir=PROJECT_ROOT / "exp" / "parse_results")

    for name in DWG_FILES:
        path = REAL_WORLD / name
        if not path.exists():
            print(f"[SKIP] {name} — 文件不存在")
            continue

        content = path.read_bytes()
        print(f"[RUN ] {name} ({len(content):,} bytes) ...", flush=True)
        t0 = time.perf_counter()

        result = svc.execute_full(content, name)
        out_dir = writer.write(
            filename=result.filename,
            file_content=result.file_content,
            format_detected=result.format_detected,
            raw_entities=result.raw_entities,
            site_model=result.site_model,
            mcp_context=result.mcp_context,
            run_id=RUN_ID,
        )

        elapsed = time.perf_counter() - t0
        sm = result.site_model
        print(
            f"[DONE] {name} → {out_dir.relative_to(PROJECT_ROOT)}"
            f"  | {len(sm.assets)} assets, {len(sm.links)} links"
            f"  | {elapsed:.1f}s"
        )

    # Print output tree
    results_dir = PROJECT_ROOT / "exp" / "parse_results" / RUN_ID
    print(f"\n=== 输出目录: {results_dir.relative_to(PROJECT_ROOT)} ===")
    for d in sorted(results_dir.iterdir()):
        if d.is_dir():
            files = sorted(d.iterdir())
            total = sum(f.stat().st_size for f in files)
            print(f"  {d.name}/  ({total:,} bytes)")
            for f in files:
                print(f"    {f.name:25s}  {f.stat().st_size:>10,} bytes")


if __name__ == "__main__":
    main()
