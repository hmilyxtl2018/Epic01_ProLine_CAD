"""
DXF 文件预览生成器 — 渲染所有 DXF 为 PNG 图片
运行: python preview_dxf_files.py
输出: ../test_data/previews/ 目录下的 PNG 文件
"""
import os
import sys
import glob

import ezdxf
from ezdxf.addons.drawing import Frontend, RenderContext
from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

TEST_DATA = os.path.join(os.path.dirname(__file__), "..", "test_data")
PREVIEW_DIR = os.path.join(TEST_DATA, "previews")
os.makedirs(PREVIEW_DIR, exist_ok=True)


def render_dxf(filepath, output_png, dpi=150):
    """渲染单个 DXF 文件为 PNG"""
    try:
        doc = ezdxf.readfile(filepath)
    except Exception as e:
        print(f"  ❌ 打开失败: {e}")
        return False

    msp = doc.modelspace()
    entity_count = len(list(msp))

    fig = plt.figure(dpi=dpi)
    ax = fig.add_axes([0, 0, 1, 1])
    ctx = RenderContext(doc)
    out = MatplotlibBackend(ax)

    Frontend(ctx, out).draw_layout(msp)

    ax.set_aspect("equal")
    ax.set_facecolor("#1a1a2e")

    # auto-fit
    ax.autoscale()
    fig.set_size_inches(16, 10)

    fig.savefig(output_png, dpi=dpi, bbox_inches="tight",
                facecolor="#1a1a2e", edgecolor="none")
    plt.close(fig)

    size_kb = os.path.getsize(output_png) / 1024
    print(f"  ✅ {os.path.basename(output_png):50s} ({entity_count} entities, {size_kb:.0f}KB)")
    return True


def main():
    print("=" * 70)
    print("  DXF 文件预览生成")
    print("=" * 70)

    # --- 生成的航空底图 ---
    generated = [
        "tier1_wing_leading_edge_workshop.dxf",
        "tier2_fuselage_join_facility.dxf",
        "tier3_pulse_line_fal.dxf",
        "reference_points_offset.dxf",
    ]

    print(f"\n🏭 航空车间底图 ({len(generated)} 个)")
    for fname in generated:
        fpath = os.path.join(TEST_DATA, fname)
        if not os.path.exists(fpath):
            print(f"  ⏭️  不存在: {fname}")
            continue
        out_png = os.path.join(PREVIEW_DIR, fname.replace(".dxf", ".png"))
        render_dxf(fpath, out_png)

    # --- ezdxf 真实 DXF ---
    ezdxf_dir = os.path.join(TEST_DATA, "real_world", "ezdxf")
    if os.path.isdir(ezdxf_dir):
        dxf_files = sorted(glob.glob(os.path.join(ezdxf_dir, "*.dxf")))
        print(f"\n📄 ezdxf 真实 DXF ({len(dxf_files)} 个)")
        for fpath in dxf_files:
            fname = os.path.basename(fpath)
            out_png = os.path.join(PREVIEW_DIR, f"real_ezdxf_{fname.replace('.dxf', '.png')}")
            render_dxf(fpath, out_png)

    print(f"\n📁 预览输出目录: {os.path.abspath(PREVIEW_DIR)}")
    pngs = glob.glob(os.path.join(PREVIEW_DIR, "*.png"))
    print(f"   共生成 {len(pngs)} 张预览图")


if __name__ == "__main__":
    main()
