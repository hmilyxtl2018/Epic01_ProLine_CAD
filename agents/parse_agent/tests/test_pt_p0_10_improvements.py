"""PT-P0-10: 改进计划 IMP-01 ~ IMP-05 验证
================================================
验证 ParseAgent_改进计划.md 中 Phase 1 ~ Phase 2 的所有改进项。

IMP-01: AssetType 枚举扩展 (5→13)
IMP-02: 多语言图层名字典 (意/俄/波兰)
IMP-03: 坐标异常过滤 (原点 + 离群点)
IMP-04: 英文图层名扩展映射
IMP-05: Zone 分类精细化 (图层覆盖几何 + 原点降级)
"""
import pytest

from shared.models import AssetType, Asset, Coords

pytestmark = [pytest.mark.p0]


# ══════════════════════════════════════════
# IMP-01: AssetType 枚举扩展
# ══════════════════════════════════════════


class TestIMP01_AssetTypeExpansion:
    """验证 AssetType 包含 13 种类型。"""

    @pytest.mark.parametrize("member", [
        "WALL", "DOOR", "PIPE", "COLUMN", "WINDOW",
        "CNC_MACHINE", "ELECTRICAL_PANEL", "STORAGE_RACK",
    ])
    def test_new_asset_type_exists(self, member):
        """新增 8 种 AssetType 均存在。"""
        assert hasattr(AssetType, member), f"AssetType 缺少 {member}"

    def test_total_asset_types_is_13(self):
        """AssetType 枚举共 13 种。"""
        assert len(AssetType) == 13, f"AssetType 数量 = {len(AssetType)}, 期望 13"

    def test_new_types_are_str_enum(self):
        """新增类型的 .value 为非空字符串。"""
        for t in [AssetType.WALL, AssetType.DOOR, AssetType.PIPE,
                  AssetType.COLUMN, AssetType.WINDOW, AssetType.CNC_MACHINE,
                  AssetType.ELECTRICAL_PANEL, AssetType.STORAGE_RACK]:
            assert isinstance(t.value, str) and len(t.value) > 0

    def test_classify_wall_block_returns_wall(self, parse_service):
        """block_name 含 'wall' → WALL。"""
        entity = {"type": "INSERT", "layer": "0", "handle": "W1",
                  "block_name": "exterior_wall_200",
                  "coords": {"x": 100.0, "y": 200.0, "z": 0.0}}
        assets = parse_service.classify_entity([entity], "AeroOntology-v1.0")
        assert assets[0].type == AssetType.WALL

    def test_classify_door_block_returns_door(self, parse_service):
        """block_name 含 'door' → DOOR。"""
        entity = {"type": "INSERT", "layer": "0", "handle": "D1",
                  "block_name": "door_900mm",
                  "coords": {"x": 50.0, "y": 50.0, "z": 0.0}}
        assets = parse_service.classify_entity([entity], "AeroOntology-v1.0")
        assert assets[0].type == AssetType.DOOR

    def test_classify_pipe_block_returns_pipe(self, parse_service):
        """block_name 含 'pipe' → PIPE。"""
        entity = {"type": "INSERT", "layer": "0", "handle": "P1",
                  "block_name": "pipe_DN50",
                  "coords": {"x": 10.0, "y": 20.0, "z": 0.0}}
        assets = parse_service.classify_entity([entity], "AeroOntology-v1.0")
        assert assets[0].type == AssetType.PIPE

    def test_classify_column_block_returns_column(self, parse_service):
        """block_name 含 'column' → COLUMN。"""
        entity = {"type": "INSERT", "layer": "0", "handle": "C1",
                  "block_name": "column_400x400",
                  "coords": {"x": 30.0, "y": 30.0, "z": 0.0}}
        assets = parse_service.classify_entity([entity], "AeroOntology-v1.0")
        assert assets[0].type == AssetType.COLUMN

    def test_new_types_not_break_existing_quality_stats(self, parse_service):
        """新类型不破坏 _compute_quality_stats。"""
        assets = [
            Asset(type=AssetType.WALL, coords=Coords(x=1, y=2), confidence=0.6, layer="WALL"),
            Asset(type=AssetType.DOOR, coords=Coords(x=3, y=4), confidence=0.5, layer="DOOR"),
            Asset(type=AssetType.OTHER, coords=Coords(x=5, y=6), confidence=0.2, layer="0"),
        ]
        q = parse_service._compute_quality_stats(assets)
        assert 0.0 <= q["classified_ratio"] <= 1.0
        assert q["classified_ratio"] > 0.5  # 2/3 classified


# ══════════════════════════════════════════
# IMP-02: 多语言图层名字典
# ══════════════════════════════════════════


class TestIMP02_MultiLangLayerDict:
    """验证多语言图层名能被正确分类。"""

    def test_italian_tavolo_classified_as_equipment(self, parse_service):
        """意大利语 Tavolo (桌子) → EQUIPMENT。"""
        entity = {"type": "INSERT", "layer": "Tavolo", "handle": "IT1",
                  "block_name": "", "coords": {"x": 10.0, "y": 10.0, "z": 0.0}}
        assets = parse_service.classify_entity([entity], "AeroOntology-v1.0")
        assert assets[0].type == AssetType.EQUIPMENT

    def test_italian_muro_classified_as_wall(self, parse_service):
        """意大利语 Muro (墙) → WALL。"""
        entity = {"type": "LWPOLYLINE", "layer": "Muro", "handle": "IT2",
                  "is_closed": True, "vertex_count": 4,
                  "coords": {"x": 10.0, "y": 10.0, "z": 0.0}}
        assets = parse_service.classify_entity([entity], "AeroOntology-v1.0")
        assert assets[0].type == AssetType.WALL

    def test_russian_layer_classified_correctly(self, parse_service):
        """俄语 СТЕНА (墙) → WALL。"""
        entity = {"type": "LINE", "layer": "СТЕНА", "handle": "RU1",
                  "coords": {"x": 10.0, "y": 10.0, "z": 0.0}}
        assets = parse_service.classify_entity([entity], "AeroOntology-v1.0")
        assert assets[0].type == AssetType.WALL

    def test_russian_crane_classified_as_lifting(self, parse_service):
        """俄语 КРАН (起重机) → LIFTING_POINT。"""
        entity = {"type": "INSERT", "layer": "КРАН", "handle": "RU2",
                  "block_name": "", "coords": {"x": 10.0, "y": 10.0, "z": 0.0}}
        assets = parse_service.classify_entity([entity], "AeroOntology-v1.0")
        assert assets[0].type == AssetType.LIFTING_POINT

    def test_polish_widoczne_classified_as_other(self, parse_service):
        """波兰语 Widoczne (可见) → OTHER (视口层)。"""
        entity = {"type": "LINE", "layer": "Widoczne", "handle": "PL1",
                  "coords": {"x": 10.0, "y": 10.0, "z": 0.0}}
        assets = parse_service.classify_entity([entity], "AeroOntology-v1.0")
        assert assets[0].type == AssetType.OTHER

    def test_polish_sciany_classified_as_wall(self, parse_service):
        """波兰语 SCIANY (墙) → WALL。"""
        entity = {"type": "LINE", "layer": "SCIANY_01", "handle": "PL2",
                  "coords": {"x": 10.0, "y": 10.0, "z": 0.0}}
        assets = parse_service.classify_entity([entity], "AeroOntology-v1.0")
        assert assets[0].type == AssetType.WALL

    def test_multilang_does_not_break_existing_english(self, parse_service):
        """原有英文映射仍然工作。"""
        entity = {"type": "INSERT", "layer": "EQUIPMENT", "handle": "EN1",
                  "block_name": "CNC", "coords": {"x": 10.0, "y": 10.0, "z": 0.0}}
        assets = parse_service.classify_entity([entity], "AeroOntology-v1.0")
        assert assets[0].type == AssetType.EQUIPMENT


# ══════════════════════════════════════════
# IMP-03: 坐标异常过滤
# ══════════════════════════════════════════


class TestIMP03_CoordAnomalyFilter:
    """验证坐标异常过滤规则。"""

    def _make_assets(self, coords_list, confidence=0.5, asset_type=AssetType.EQUIPMENT):
        """辅助: 根据坐标列表创建 Asset。"""
        return [
            Asset(type=asset_type, coords=Coords(x=x, y=y, z=z),
                  confidence=confidence, layer="TEST")
            for x, y, z in coords_list
        ]

    def test_origin_low_confidence_demoted(self, parse_service):
        """(0,0,0) + confidence < 0.3 → OTHER。"""
        assets = self._make_assets(
            [(0.0, 0.0, 0.0), (100.0, 200.0, 0.0), (300.0, 400.0, 0.0),
             (500.0, 600.0, 0.0), (700.0, 800.0, 0.0)],
            confidence=0.2, asset_type=AssetType.ZONE,
        )
        result = parse_service.filter_anomalous_coords(assets)
        assert result[0].type == AssetType.OTHER, "原点+低置信未降级 OTHER"

    def test_origin_high_confidence_kept(self, parse_service):
        """(0,0,0) + confidence >= 0.3 → 保持原类型。"""
        assets = self._make_assets(
            [(0.0, 0.0, 0.0), (100.0, 200.0, 0.0), (300.0, 400.0, 0.0),
             (500.0, 600.0, 0.0), (700.0, 800.0, 0.0)],
            confidence=0.5, asset_type=AssetType.ZONE,
        )
        result = parse_service.filter_anomalous_coords(assets)
        assert result[0].type == AssetType.ZONE, "原点+高置信不应降级"

    def test_outlier_coord_confidence_halved(self, parse_service):
        """超出 P5-P95 IQR 3x 的离群点 → confidence *= 0.5, type → OTHER。"""
        normal = [(float(i * 100), float(i * 100), 0.0) for i in range(1, 21)]
        outlier = [(9999999.0, 9999999.0, 0.0)]
        assets = self._make_assets(normal + outlier, confidence=0.6)
        result = parse_service.filter_anomalous_coords(assets)
        # 最后一个是离群点
        assert result[-1].type == AssetType.OTHER
        assert result[-1].confidence == pytest.approx(0.3, abs=0.01)

    def test_normal_entities_not_affected(self, parse_service):
        """正常范围实体不受影响。"""
        coords = [(100.0 + i * 50, 200.0 + i * 50, 0.0) for i in range(10)]
        assets = self._make_assets(coords, confidence=0.7)
        result = parse_service.filter_anomalous_coords(assets)
        for a in result:
            assert a.type == AssetType.EQUIPMENT
            assert a.confidence == 0.7

    def test_empty_assets_returns_empty(self, parse_service):
        """空列表不报错。"""
        result = parse_service.filter_anomalous_coords([])
        assert result == []


# ══════════════════════════════════════════
# IMP-04: 英文图层名扩展映射
# ══════════════════════════════════════════


class TestIMP04_EnglishLayerExpansion:
    """验证扩展的英文图层名映射。"""

    def test_furn_eq_classified_as_equipment(self, parse_service):
        """FURN_EQ → EQUIPMENT。"""
        entity = {"type": "INSERT", "layer": "FURN_EQ", "handle": "F1",
                  "block_name": "", "coords": {"x": 10.0, "y": 10.0, "z": 0.0}}
        assets = parse_service.classify_entity([entity], "AeroOntology-v1.0")
        assert assets[0].type == AssetType.EQUIPMENT

    def test_dim_layer_classified_as_other(self, parse_service):
        """DIM (标注层) → OTHER。"""
        entity = {"type": "LINE", "layer": "DIM1", "handle": "F2",
                  "coords": {"x": 10.0, "y": 10.0, "z": 0.0}}
        assets = parse_service.classify_entity([entity], "AeroOntology-v1.0")
        assert assets[0].type == AssetType.OTHER

    def test_wall_layer_classified_as_wall(self, parse_service):
        """WALL → WALL (非 ZONE)。"""
        entity = {"type": "LINE", "layer": "WALL", "handle": "F3",
                  "coords": {"x": 10.0, "y": 10.0, "z": 0.0}}
        assets = parse_service.classify_entity([entity], "AeroOntology-v1.0")
        assert assets[0].type == AssetType.WALL

    def test_door_layer_classified_as_door(self, parse_service):
        """DOOR → DOOR。"""
        entity = {"type": "LINE", "layer": "DOOR", "handle": "F4",
                  "coords": {"x": 10.0, "y": 10.0, "z": 0.0}}
        assets = parse_service.classify_entity([entity], "AeroOntology-v1.0")
        assert assets[0].type == AssetType.DOOR

    def test_rail_layer_classified_as_conveyor(self, parse_service):
        """RAIL → CONVEYOR。"""
        entity = {"type": "LINE", "layer": "RAIL", "handle": "F5",
                  "coords": {"x": 10.0, "y": 10.0, "z": 0.0}}
        assets = parse_service.classify_entity([entity], "AeroOntology-v1.0")
        assert assets[0].type == AssetType.CONVEYOR

    def test_floor_layer_classified_as_zone(self, parse_service):
        """FLOOR → ZONE。"""
        entity = {"type": "LINE", "layer": "FLOOR", "handle": "F6",
                  "coords": {"x": 10.0, "y": 10.0, "z": 0.0}}
        assets = parse_service.classify_entity([entity], "AeroOntology-v1.0")
        assert assets[0].type == AssetType.ZONE

    def test_hatch_layer_classified_as_other(self, parse_service):
        """HATCH → OTHER。"""
        entity = {"type": "LINE", "layer": "HATCH", "handle": "F7",
                  "coords": {"x": 10.0, "y": 10.0, "z": 0.0}}
        assets = parse_service.classify_entity([entity], "AeroOntology-v1.0")
        assert assets[0].type == AssetType.OTHER

    def test_hvac_layer_classified_as_pipe(self, parse_service):
        """HVAC → PIPE。"""
        entity = {"type": "LINE", "layer": "HVAC", "handle": "F8",
                  "coords": {"x": 10.0, "y": 10.0, "z": 0.0}}
        assets = parse_service.classify_entity([entity], "AeroOntology-v1.0")
        assert assets[0].type == AssetType.PIPE


# ══════════════════════════════════════════
# IMP-05: Zone 分类精细化
# ══════════════════════════════════════════


class TestIMP05_ZoneRefinement:
    """验证 Zone 二次验证逻辑。"""

    def test_closed_polyline_on_wall_layer_becomes_wall(self, parse_service):
        """闭合多段线在 WALLS 图层 → WALL (非 ZONE)。"""
        entity = {"type": "LWPOLYLINE", "layer": "WALLS", "handle": "Z1",
                  "is_closed": True, "vertex_count": 8,
                  "coords": {"x": 100.0, "y": 200.0, "z": 0.0}}
        assets = parse_service.classify_entity([entity], "AeroOntology-v1.0")
        assert assets[0].type == AssetType.WALL

    def test_closed_polyline_on_equipment_layer_not_zone(self, parse_service):
        """闭合多段线在 EQUIPMENT 图层 → EQUIPMENT (非 ZONE)。"""
        entity = {"type": "LWPOLYLINE", "layer": "EQUIPMENT", "handle": "Z2",
                  "is_closed": True, "vertex_count": 6,
                  "coords": {"x": 100.0, "y": 200.0, "z": 0.0}}
        assets = parse_service.classify_entity([entity], "AeroOntology-v1.0")
        assert assets[0].type == AssetType.EQUIPMENT

    def test_closed_polyline_on_door_layer_becomes_door(self, parse_service):
        """闭合多段线在 DOOR 图层 → DOOR (非 ZONE)。"""
        entity = {"type": "LWPOLYLINE", "layer": "DOOR", "handle": "Z3",
                  "is_closed": True, "vertex_count": 4,
                  "coords": {"x": 100.0, "y": 200.0, "z": 0.0}}
        assets = parse_service.classify_entity([entity], "AeroOntology-v1.0")
        assert assets[0].type == AssetType.DOOR

    def test_large_closed_polyline_on_unnamed_layer_stays_zone(self, parse_service):
        """闭合多段线在普通层 → 保持 ZONE。"""
        entity = {"type": "LWPOLYLINE", "layer": "0", "handle": "Z4",
                  "is_closed": True, "vertex_count": 20,
                  "coords": {"x": 100.0, "y": 200.0, "z": 0.0}}
        assets = parse_service.classify_entity([entity], "AeroOntology-v1.0")
        assert assets[0].type == AssetType.ZONE

    def test_zone_on_zone_layer_preserved(self, parse_service):
        """闭合多段线在 ZONE 图层 → 保持 ZONE。"""
        entity = {"type": "LWPOLYLINE", "layer": "ZONE", "handle": "Z5",
                  "is_closed": True, "vertex_count": 12,
                  "coords": {"x": 100.0, "y": 200.0, "z": 0.0}}
        assets = parse_service.classify_entity([entity], "AeroOntology-v1.0")
        assert assets[0].type == AssetType.ZONE

    def test_origin_zone_low_confidence_demoted(self, parse_service):
        """(0,0,0) 闭合多段线 低置信 → OTHER (非 ZONE)。"""
        entity = {"type": "LWPOLYLINE", "layer": "0", "handle": "Z6",
                  "is_closed": True, "vertex_count": 4,
                  "coords": {"x": 0.0, "y": 0.0, "z": 0.0}}
        assets = parse_service.classify_entity([entity], "AeroOntology-v1.0")
        # 无 block, 无 layer hit → confidence is geometric only + complexity + ref
        # confidence = 0.25*1.0 + 0.15*(4/20) + 0.10*1.0 = 0.25+0.03+0.10 = 0.38 < 0.4
        assert assets[0].type == AssetType.OTHER

    def test_closed_polyline_on_furn_eq_becomes_equipment(self, parse_service):
        """闭合多段线在 FURN_EQ 图层 → EQUIPMENT (非 ZONE)。"""
        entity = {"type": "LWPOLYLINE", "layer": "FURN_EQ", "handle": "Z7",
                  "is_closed": True, "vertex_count": 8,
                  "coords": {"x": 100.0, "y": 200.0, "z": 0.0}}
        assets = parse_service.classify_entity([entity], "AeroOntology-v1.0")
        assert assets[0].type == AssetType.EQUIPMENT
