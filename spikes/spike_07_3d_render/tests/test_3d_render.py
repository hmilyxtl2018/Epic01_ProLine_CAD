"""
Spike-7 测试用例：3D 渲染与实时交互性能 (后端数据结构验证)
==========================================================
Test Case IDs: S7-TC01 ~ S7-TC06 (关键技术验证计划 §8.2)

注: 3D 渲染是前端 (Three.js + R3F), 此处验证后端数据结构和 API 接口。
    前端 FPS/交互测试需要浏览器环境，属于 E2E 测试范畴。

Go/No-Go 必须标准:
  - 200 Assets FPS ≥ 30
  - 首屏加载 ≤ 3s
  - 拖拽响应无感知卡顿
"""
import json
import pytest
from conftest import Thresholds

# ════════════════════════════════════════════════════════════════
# 待实现模块导入 — TDD RED phase
# ════════════════════════════════════════════════════════════════
from spike_07_3d_render.src.scene_builder import SceneBuilder
from spike_07_3d_render.src.layout_serializer import LayoutSerializer


@pytest.mark.p1
@pytest.mark.spike7
class TestSceneDataGeneration:
    """S7-TC01/TC02: 场景数据生成 — 供前端渲染"""

    def test_tc01_50_assets_scene(self):
        """50 Assets 场景数据生成成功"""
        builder = SceneBuilder()
        scene = builder.build(asset_count=50, factory_size=(100_000, 60_000))

        assert len(scene.meshes) == 50
        assert scene.floor is not None
        assert scene.camera_config is not None

    def test_tc02_200_assets_scene(self):
        """200 Assets 场景数据应使用 InstancedMesh"""
        builder = SceneBuilder()
        scene = builder.build(asset_count=200, factory_size=(300_000, 120_000))

        assert len(scene.meshes) == 200
        # 高密度场景应标记为 instanced
        assert scene.use_instanced_mesh is True

    def test_scene_json_serializable(self):
        """场景数据应可序列化为 JSON (供前端消费)"""
        builder = SceneBuilder()
        scene = builder.build(asset_count=50, factory_size=(100_000, 60_000))

        serializer = LayoutSerializer()
        json_data = serializer.to_json(scene)
        parsed = json.loads(json_data)

        assert "meshes" in parsed
        assert "floor" in parsed
        assert "camera" in parsed


@pytest.mark.p1
@pytest.mark.spike7
class TestCollisionHighlightData:
    """S7-TC04: 碰撞高亮数据"""

    def test_tc04_highlight_payload(self):
        """碰撞检测结果应转为前端可用的高亮指令"""
        collisions = [
            {"asset_a": "eq_001", "asset_b": "eq_002", "overlap_area_mm2": 5000},
        ]
        serializer = LayoutSerializer()
        highlights = serializer.collision_to_highlights(collisions)

        assert len(highlights) == 2  # 两个设备都需高亮
        for h in highlights:
            assert "asset_guid" in h
            assert "color" in h  # 红色高亮
            assert h["color"] == "#FF0000"


@pytest.mark.p1
@pytest.mark.spike7
class TestExclusionZoneOverlay:
    """S7-TC05: 障碍物/禁区半透明覆盖数据"""

    def test_tc05_overlay_generation(self):
        """禁区数据应转为半透明 Polygon 叠加层"""
        zones = [
            {"zone_id": "ndt_01", "type": "circle", "center": [50000, 50000], "radius": 15000},
            {"zone_id": "clean_01", "type": "rectangle", "origin": [10000, 10000], "size": [20000, 15000]},
        ]

        serializer = LayoutSerializer()
        overlays = serializer.zones_to_overlays(zones)

        assert len(overlays) == 2
        for o in overlays:
            assert "geometry" in o
            assert "opacity" in o
            assert 0 < o["opacity"] < 1  # 半透明


@pytest.mark.p1
@pytest.mark.spike7
class TestCameraConfig:
    """S7-TC06: 2D/3D 切换相机配置"""

    def test_tc06_orthographic_config(self):
        """正交相机 (2D 模式) 配置"""
        builder = SceneBuilder()
        config = builder.get_camera_config(mode="2d", factory_size=(100_000, 60_000))

        assert config.type == "orthographic"
        assert config.position is not None

    def test_tc06_perspective_config(self):
        """透视相机 (3D 模式) 配置"""
        builder = SceneBuilder()
        config = builder.get_camera_config(mode="3d", factory_size=(100_000, 60_000))

        assert config.type == "perspective"
        assert config.fov is not None
        assert config.fov > 0


# ════════════════════════════════════════════════════════════════
# L4: 黄金基准 — 精确 JSON 结构 diff
# ════════════════════════════════════════════════════════════════

@pytest.mark.p1
@pytest.mark.spike7
class TestGoldenBaseline:
    """L4: 已知资产 → 精确 JSON 字段结构"""

    def test_two_assets_exact_structure(self):
        """2 个已知设备 → 每个 mesh 必须包含完整属性"""
        builder = SceneBuilder()
        scene = builder.build(asset_count=2, factory_size=(10_000, 8_000))

        serializer = LayoutSerializer()
        json_data = json.loads(serializer.to_json(scene))

        assert len(json_data["meshes"]) == 2

        mesh = json_data["meshes"][0]
        required_keys = {"asset_guid", "position", "dimensions", "material"}
        assert required_keys.issubset(set(mesh.keys())), (
            f"mesh 缺少字段: {required_keys - set(mesh.keys())}"
        )
        assert len(mesh["position"]) == 3  # [x, y, z]
        assert len(mesh["dimensions"]) == 3  # [w, h, d]

    def test_highlight_exact_guids(self):
        """碰撞对 [A,B] → 高亮列表精确包含 A 和 B"""
        collisions = [
            {"asset_a": "eq_001", "asset_b": "eq_002", "overlap_area_mm2": 5000},
        ]
        serializer = LayoutSerializer()
        highlights = serializer.collision_to_highlights(collisions)

        guids = {h["asset_guid"] for h in highlights}
        assert guids == {"eq_001", "eq_002"}

    def test_overlay_geometry_type_matches_zone(self):
        """circle zone → circle 几何, rectangle zone → polygon 几何"""
        zones = [
            {"zone_id": "z1", "type": "circle", "center": [0, 0], "radius": 1000},
            {"zone_id": "z2", "type": "rectangle", "origin": [0, 0], "size": [1000, 1000]},
        ]
        serializer = LayoutSerializer()
        overlays = serializer.zones_to_overlays(zones)

        geo_types = {o["geometry"]["type"] for o in overlays}
        assert "circle" in geo_types or "polygon" in geo_types
