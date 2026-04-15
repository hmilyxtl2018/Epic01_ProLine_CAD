"""
从 CPACS D150 定义文件提取机身段几何，导出为 STEP AP214 文件。

依赖环境：conda tigl_env (conda install -c dlr-sc tigl3 tixi3)
用法：
    conda run -n tigl_env python scripts/acquire_fuselage_step.py
"""

import os
import sys
from pathlib import Path

# ════════════════ 路径定义 ════════════════
SCRIPT_DIR = Path(__file__).parent
SPIKE_DIR = SCRIPT_DIR.parent
CPACS_FILE = SPIKE_DIR / "test_data" / "cpacs" / "D150_v30.xml"
CPACS_FALLBACK = SPIKE_DIR / "test_data" / "cpacs" / "simpletest.cpacs.xml"
OUTPUT_DIR = SPIKE_DIR / "test_data" / "design_model"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_FULL = OUTPUT_DIR / "fuselage_full.stp"
OUTPUT_SECTION_A = OUTPUT_DIR / "fuselage_section_a.stp"
OUTPUT_SECTION_B = OUTPUT_DIR / "fuselage_section_b.stp"


def pick_cpacs_file():
    """选择可用的 CPACS 文件：优先 D150，退回 simpletest。"""
    if CPACS_FILE.exists():
        print(f"[INFO] 使用定义文件: {CPACS_FILE.name} ({CPACS_FILE.stat().st_size / 1024:.1f} KB)")
        return str(CPACS_FILE)
    elif CPACS_FALLBACK.exists():
        print(f"[WARN] D150_v30.xml 未找到，使用回退文件: {CPACS_FALLBACK.name}")
        return str(CPACS_FALLBACK)
    else:
        print("[ERROR] 未找到任何 CPACS 文件！请先运行数据下载步骤。")
        sys.exit(1)


def export_step_tigl(cpacs_path: str):
    """使用 TiGL 从 CPACS 文件导出机身段 STEP 文件。"""
    try:
        import tixi3.tixi3wrapper as tixi3wrapper
        import tigl3.tigl3wrapper as tigl3wrapper
    except ImportError:
        print("[ERROR] 未检测到 tigl3/tixi3！请在 conda tigl_env 环境中运行本脚本。")
        print("        conda create -n tigl_env -c dlr-sc tigl3 tixi3 python=3.10 -y")
        print("        conda run -n tigl_env python scripts/acquire_fuselage_step.py")
        sys.exit(1)

    tixi_h = tixi3wrapper.Tixi3()
    tigl_h = tigl3wrapper.Tigl3()

    print(f"[STEP 1] 加载 CPACS 定义文件...")
    tixi_h.open(cpacs_path)

    print("[STEP 2] 初始化 TiGL 几何引擎...")
    tigl_h.open(tixi_h, "")

    # ── 查询飞机基础信息 ──
    try:
        fuselage_count = tigl_h.getFuselageCount()
        wing_count = tigl_h.getWingCount()
        print(f"[INFO] 检测到: 机身={fuselage_count} 个, 机翼={wing_count} 个")
    except Exception:
        print("[INFO] 无法查询飞机基础信息，继续导出...")

    # ── 导出完整飞机几何 STEP ──
    print(f"[STEP 3] 导出完整飞机几何 → {OUTPUT_FULL.name} ...")
    tigl_h.exportSTEP(str(OUTPUT_FULL))
    if OUTPUT_FULL.exists():
        print(f"[OK] {OUTPUT_FULL.name}  ({OUTPUT_FULL.stat().st_size / 1024:.1f} KB)")
    else:
        print(f"[WARN] 完整 STEP 未生成")

    # ── 尝试导出机身专用 STEP（如 TiGL 版本支持） ──
    try:
        print(f"[STEP 4] 尝试单独导出机身几何 → {OUTPUT_SECTION_A.name} ...")
        tigl_h.fuselageExportIGES(str(OUTPUT_SECTION_A), 1)
        if OUTPUT_SECTION_A.exists():
            print(f"[OK] {OUTPUT_SECTION_A.name}  ({OUTPUT_SECTION_A.stat().st_size / 1024:.1f} KB)")
    except Exception as e:
        print(f"[INFO] 单独机身导出不支持（{e}），完整 STEP 已足够用于测试。")

    tigl_h.close()
    tixi_h.close()
    print("\n[完成] STEP 文件生成完毕，保存在:", OUTPUT_DIR)


def verify_output():
    """验证输出文件可用性。"""
    print("\n[验证] 检查输出文件...")
    any_ok = False
    for f in OUTPUT_DIR.glob("*.stp"):
        size = f.stat().st_size
        status = "OK" if size > 10_000 else "WARN (< 10KB)"
        print(f"  [{status}] {f.name}  ({size / 1024:.1f} KB)")
        any_ok = any_ok or (size > 10_000)

    if any_ok:
        print("[验证通过] 至少一个 STEP 文件 > 10KB，可供后续点云合成使用。")
    else:
        print("[验证失败] 未找到有效 STEP 文件！")
        sys.exit(1)


if __name__ == "__main__":
    cpacs_path = pick_cpacs_file()
    export_step_tigl(cpacs_path)
    verify_output()
