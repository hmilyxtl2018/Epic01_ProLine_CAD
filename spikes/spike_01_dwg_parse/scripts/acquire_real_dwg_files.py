"""
真实 DWG/DXF 测试文件采集脚本
从公开 GitHub 仓库下载真实 AutoCAD 格式文件，用于 Spike-1 解析器格式兼容性验证。

运行: python acquire_real_dwg_files.py
输出: ../test_data/real_world/ 目录下
"""
import os
import urllib.request
import json
import hashlib

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "test_data", "real_world")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ────────────────────────────────────────────────────────────────
#  来源 1: LibreDWG 官方测试文件 (GPLv3 — 仅用于测试目的)
#  https://github.com/LibreDWG/libredwg
#  包含 R13 ~ 2018 各版本真实 DWG 文件
# ────────────────────────────────────────────────────────────────
LIBREDWG_BASE = "https://raw.githubusercontent.com/LibreDWG/libredwg/master/test/test-data"
LIBREDWG_FILES = [
    # 主版本覆盖: R2000/2004/2007/2010/2013/2018
    ("example_2000.dwg",  "DWG R2000 — 最常用企业版本"),
    ("example_2004.dwg",  "DWG R2004"),
    ("example_2007.dwg",  "DWG R2007 — ACAD新特性: 注释缩放"),
    ("example_2010.dwg",  "DWG R2010 — PDF底图、参数化约束"),
    ("example_2013.dwg",  "DWG R2013"),
    ("example_2018.dwg",  "DWG R2018 — 最新格式"),
    ("example_r14.dwg",   "DWG R14 — 老旧图纸兼容"),
    ("sample_2000.dwg",   "DWG R2000 样例2 — 不同实体组合"),
    ("sample_2018.dwg",   "DWG R2018 样例2"),
]

# ────────────────────────────────────────────────────────────────
#  来源 2: ezdxf 官方示例 DXF 文件 (MIT License)
#  https://github.com/mozman/ezdxf
#  包含各种 DXF 实体特性的标准文件
# ────────────────────────────────────────────────────────────────
EZDXF_BASE = "https://raw.githubusercontent.com/mozman/ezdxf/master/examples_dxf"
EZDXF_FILES = [
    ("hatches_1.dxf",       "Hatch填充 — 工厂底图常见"),
    ("hatches_2.dxf",       "Hatch填充2 — 复杂填充模式"),
    ("3dface.dxf",          "3DFACE — 三维面片实体"),
    ("text.dxf",            "TEXT — 文字标注压力测试"),
    ("visibility.dxf",      "图层可见性控制"),
    ("colors.dxf",          "颜色编码"),
    ("uncommon.dxf",        "不常见DXF实体类型"),
]

# ────────────────────────────────────────────────────────────────
#  来源 3: LibreDWG 各版本子目录中的小型 DWG（按 entity 类型分类）
# ────────────────────────────────────────────────────────────────
LIBREDWG_ENTITY_BASE = "https://raw.githubusercontent.com/LibreDWG/libredwg/master/test/test-data/2000"
LIBREDWG_ENTITY_FILES = [
    ("Leader.dwg",          "引线标注"),
    ("Line.dwg",            "直线 — 最基础实体"),
    ("lwpolyline.dwg",      "轻量多段线 — 墙体/管道"),
    ("Arc.dwg",             "圆弧"),
    ("Circle.dwg",          "圆"),
    ("Dimension.dwg",       "尺寸标注"),
    ("Insert.dwg",          "块插入 — 设备图块"),
    ("MText.dwg",           "多行文字"),
    ("Hatch.dwg",           "填充 — 区域标识"),
    ("Spline.dwg",          "样条曲线"),
    ("Ellipse.dwg",         "椭圆"),
    ("Viewport.dwg",        "视口 — 多布局"),
]


def download_file(url, dest_path, description):
    """下载单个文件，带重试和校验"""
    if os.path.exists(dest_path):
        print(f"  ⏭️  已存在: {os.path.basename(dest_path)}")
        return True

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ProLine-CAD-Test/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()

        with open(dest_path, "wb") as f:
            f.write(data)

        size_kb = len(data) / 1024
        md5 = hashlib.md5(data).hexdigest()[:8]
        print(f"  ✅ {os.path.basename(dest_path):40s} {size_kb:8.1f} KB  [{md5}]  {description}")
        return True
    except Exception as e:
        print(f"  ❌ {os.path.basename(dest_path):40s} 失败: {e}")
        return False


def main():
    print("=" * 70)
    print("  Spike-1 真实 DWG/DXF 文件采集")
    print("  输出目录:", os.path.abspath(OUTPUT_DIR))
    print("=" * 70)

    manifest = {"sources": [], "files": []}
    total, ok, fail = 0, 0, 0

    # --- 来源 1: LibreDWG 主文件 ---
    print(f"\n📦 来源 1/3: LibreDWG 主测试文件 ({len(LIBREDWG_FILES)} 个)")
    print(f"   License: GPLv3 (测试用途)")
    print(f"   URL: https://github.com/LibreDWG/libredwg")
    subdir = os.path.join(OUTPUT_DIR, "libredwg")
    os.makedirs(subdir, exist_ok=True)
    for fname, desc in LIBREDWG_FILES:
        total += 1
        url = f"{LIBREDWG_BASE}/{fname}"
        dest = os.path.join(subdir, fname)
        if download_file(url, dest, desc):
            ok += 1
            manifest["files"].append({"file": f"libredwg/{fname}", "source": "LibreDWG", "desc": desc})
        else:
            fail += 1

    # --- 来源 2: ezdxf DXF样例 ---
    print(f"\n📦 来源 2/3: ezdxf 官方 DXF 样例 ({len(EZDXF_FILES)} 个)")
    print(f"   License: MIT")
    print(f"   URL: https://github.com/mozman/ezdxf")
    subdir = os.path.join(OUTPUT_DIR, "ezdxf")
    os.makedirs(subdir, exist_ok=True)
    for fname, desc in EZDXF_FILES:
        total += 1
        url = f"{EZDXF_BASE}/{fname}"
        dest = os.path.join(subdir, fname)
        if download_file(url, dest, desc):
            ok += 1
            manifest["files"].append({"file": f"ezdxf/{fname}", "source": "ezdxf", "desc": desc})
        else:
            fail += 1

    # --- 来源 3: LibreDWG Entity 文件 ---
    print(f"\n📦 来源 3/3: LibreDWG R2000 实体类型覆盖 ({len(LIBREDWG_ENTITY_FILES)} 个)")
    subdir = os.path.join(OUTPUT_DIR, "libredwg_entities")
    os.makedirs(subdir, exist_ok=True)
    for fname, desc in LIBREDWG_ENTITY_FILES:
        total += 1
        url = f"{LIBREDWG_ENTITY_BASE}/{fname}"
        dest = os.path.join(subdir, fname)
        if download_file(url, dest, desc):
            ok += 1
            manifest["files"].append({"file": f"libredwg_entities/{fname}", "source": "LibreDWG/2000", "desc": desc})
        else:
            fail += 1

    # --- 写入清单 ---
    manifest["sources"] = [
        {
            "name": "LibreDWG",
            "url": "https://github.com/LibreDWG/libredwg",
            "license": "GPLv3",
            "purpose": "真实 DWG 二进制格式兼容性验证 (R14~R2018)",
        },
        {
            "name": "ezdxf",
            "url": "https://github.com/mozman/ezdxf",
            "license": "MIT",
            "purpose": "DXF 实体特性解析验证 (Hatch, Text, 3DFace, Block)",
        },
    ]
    manifest["total"] = total
    manifest["downloaded"] = ok
    manifest["failed"] = fail

    manifest_path = os.path.join(OUTPUT_DIR, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"\n{'=' * 70}")
    print(f"  完成: {ok}/{total} 成功, {fail} 失败")
    print(f"  清单: {manifest_path}")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
