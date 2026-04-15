"""
预览 STEP 几何体 — 生成多视角 PNG 预览图。

依赖环境：conda tigl_env (含 pythonocc-core + matplotlib)
用法：
    conda activate tigl_env
    python scripts/preview_step_geometry.py
"""

import sys
from pathlib import Path

import matplotlib
matplotlib.use('Agg')  # 无头模式，不需要显示器
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import numpy as np

# ════════════════ 路径定义 ════════════════
SCRIPT_DIR = Path(__file__).parent
SPIKE_DIR = SCRIPT_DIR.parent
STEP_FILE = SPIKE_DIR / "test_data" / "design_model" / "fuselage_full.stp"
PREVIEW_DIR = SPIKE_DIR / "test_data" / "previews"
PREVIEW_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_PNG = PREVIEW_DIR / "fuselage_preview.png"


def load_step_shape(step_path: str):
    """用 pythonocc 加载 STEP 文件，返回 compound shape。"""
    from OCC.Core.STEPControl import STEPControl_Reader
    from OCC.Core.IFSelect import IFSelect_RetDone

    reader = STEPControl_Reader()
    status = reader.ReadFile(step_path)
    if status != IFSelect_RetDone:
        print(f"[ERROR] 无法读取 STEP 文件: {step_path}")
        sys.exit(1)
    reader.TransferRoots()
    shape = reader.OneShape()
    print(f"[OK] STEP 加载完成: {step_path}")
    return shape


def tessellate_shape(shape, deflection=10.0):
    """对 shape 进行三角剖分，返回顶点数组和三角面列表。"""
    from OCC.Core.BRepMesh import BRepMesh_IncrementalMesh
    from OCC.Core.TopExp import TopExp_Explorer
    from OCC.Core.TopAbs import TopAbs_FACE
    from OCC.Core.BRep import BRep_Tool
    from OCC.Core.TopLoc import TopLoc_Location

    print(f"[INFO] 正在三角化 (deflection={deflection})，请稍候...")
    mesh = BRepMesh_IncrementalMesh(shape, deflection)
    mesh.Perform()

    triangles = []
    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    face_count = 0

    while explorer.More():
        face = explorer.Current()
        location = TopLoc_Location()
        triangulation = BRep_Tool.Triangulation(face, location)

        if triangulation is not None:
            trsf = location.IsIdentity()
            mat = location.IsIdentity()

            node_count = triangulation.NbNodes()
            tri_count = triangulation.NbTriangles()

            nodes = np.array([
                [triangulation.Node(i + 1).X(),
                 triangulation.Node(i + 1).Y(),
                 triangulation.Node(i + 1).Z()]
                for i in range(node_count)
            ])

            # 应用位置变换
            if not location.IsIdentity():
                trsf = location.IsIdentity()

            for j in range(1, tri_count + 1):
                tri = triangulation.Triangle(j)
                n1, n2, n3 = tri.Get()
                triangles.append([nodes[n1 - 1], nodes[n2 - 1], nodes[n3 - 1]])

            face_count += 1

        explorer.Next()

    print(f"[INFO] 三角化完成: {face_count} 个面，{len(triangles)} 个三角片")
    return triangles


def render_preview(triangles, output_path: Path):
    """渲染多视角预览图并保存为 PNG。"""
    if not triangles:
        print("[ERROR] 没有可渲染的三角片！")
        return

    # 降采样加速渲染（最多取 15000 个三角面）
    max_tris = 15000
    if len(triangles) > max_tris:
        step = len(triangles) // max_tris
        triangles = triangles[::step]
        print(f"[INFO] 降采样至 {len(triangles)} 个三角面用于渲染")

    poly = Poly3DCollection(triangles, alpha=0.4, linewidths=0,
                            facecolor='#5599cc', edgecolor='none')

    # 计算包围盒
    all_pts = np.vstack([np.array(t) for t in triangles])
    x_range = [all_pts[:, 0].min(), all_pts[:, 0].max()]
    y_range = [all_pts[:, 1].min(), all_pts[:, 1].max()]
    z_range = [all_pts[:, 2].min(), all_pts[:, 2].max()]
    center = [(x_range[0]+x_range[1])/2,
              (y_range[0]+y_range[1])/2,
              (z_range[0]+z_range[1])/2]
    span = max(x_range[1]-x_range[0],
               y_range[1]-y_range[0],
               z_range[1]-z_range[0]) * 0.6

    print(f"[INFO] 几何包围盒: X={x_range}, Y={y_range}, Z={z_range}")
    print(f"[INFO] 大约尺寸: {x_range[1]-x_range[0]:.1f} x "
          f"{y_range[1]-y_range[0]:.1f} x {z_range[1]-z_range[0]:.1f} m")

    # 3视角布局
    fig = plt.figure(figsize=(18, 6), facecolor='#f8f9fa')
    fig.suptitle('D150 飞机几何体预览 — STEP 模型 (fuselage_full.stp)',
                 fontsize=14, fontweight='bold', color='#1a1a2e')

    views = [
        ('侧视图 (XZ)', 0, 0),
        ('俯视图 (XY)', 90, 0),
        ('透视图', 25, -60),
    ]

    for idx, (title, elev, azim) in enumerate(views):
        ax = fig.add_subplot(1, 3, idx + 1, projection='3d')
        # 每个子图需要独立的 Poly3DCollection
        poly_i = Poly3DCollection(triangles, alpha=0.45, linewidths=0,
                                  facecolor='#4a90d9', edgecolor='none')
        ax.add_collection3d(poly_i)

        ax.set_xlim(center[0]-span, center[0]+span)
        ax.set_ylim(center[1]-span, center[1]+span)
        ax.set_zlim(center[2]-span, center[2]+span)
        ax.view_init(elev=elev, azim=azim)
        ax.set_title(title, fontsize=11, color='#2c3e50', pad=8)
        ax.set_xlabel('X (m)', fontsize=8)
        ax.set_ylabel('Y (m)', fontsize=8)
        ax.set_zlabel('Z (m)', fontsize=8)
        ax.tick_params(labelsize=7)
        ax.set_facecolor('#eef2f7')
        ax.xaxis.pane.fill = False
        ax.yaxis.pane.fill = False
        ax.zaxis.pane.fill = False
        ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(str(output_path), dpi=150, bbox_inches='tight')
    plt.close()
    print(f"[OK] 预览图已保存: {output_path}  ({output_path.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    if not STEP_FILE.exists():
        print(f"[ERROR] 找不到 STEP 文件: {STEP_FILE}")
        print("        请先运行: python scripts/acquire_fuselage_step.py")
        sys.exit(1)

    print(f"[开始] 预览 STEP 文件: {STEP_FILE.name} ({STEP_FILE.stat().st_size / 1024:.1f} KB)")
    shape = load_step_shape(str(STEP_FILE))
    triangles = tessellate_shape(shape, deflection=50.0)  # 较大 deflection = 粗糙但快
    render_preview(triangles, OUTPUT_PNG)
    print(f"\n[完成] 预览图保存在: {OUTPUT_PNG}")
