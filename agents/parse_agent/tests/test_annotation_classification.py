"""S2-T3: ANNOTATION 类型分类单元测试。

验证 TEXT/MTEXT/DIMENSION/LEADER/ATTDEF 等实体被识别为 AssetType.ANNOTATION,
并且该规则胜过块名/几何/图层启发式以及系统图层黑名单。
"""
from __future__ import annotations

import pytest

from agents.parse_agent.service import ParseService, _ANNOTATION_ENTITY_TYPES
from shared.models import AssetType


@pytest.fixture
def svc() -> ParseService:
    return ParseService()


def _entity(etype: str, **kwargs) -> dict:
    base = {
        "type": etype,
        "layer": kwargs.pop("layer", "0"),
        "handle": kwargs.pop("handle", "ABC123"),
    }
    if "x" in kwargs:
        base["coords"] = {
            "x": kwargs.pop("x"), "y": kwargs.pop("y", 0.0), "z": kwargs.pop("z", 0.0),
        }
    base.update(kwargs)
    return base


# ════════════════ 基础: 各种注释实体类型 ════════════════

@pytest.mark.parametrize("etype", [
    "TEXT", "MTEXT", "DIMENSION",
    "LEADER", "MULTILEADER", "MLEADER",
    "ATTDEF", "ATTRIB", "TOLERANCE",
])
def test_annotation_entity_types_classified_as_annotation(svc, etype):
    assets = svc.classify_entity([_entity(etype, x=10.0, y=20.0)], "v1")
    assert len(assets) == 1
    assert assets[0].type == AssetType.ANNOTATION
    assert assets[0].confidence >= 0.85


def test_annotation_entity_types_constant_is_frozen():
    assert isinstance(_ANNOTATION_ENTITY_TYPES, frozenset)
    assert "TEXT" in _ANNOTATION_ENTITY_TYPES
    assert "MTEXT" in _ANNOTATION_ENTITY_TYPES
    assert "DIMENSION" in _ANNOTATION_ENTITY_TYPES


# ════════════════ 优先级: ANNOTATION 胜过块名/图层 ════════════════

def test_text_overrides_equipment_layer(svc):
    """TEXT 在 EQUIPMENT 图层上仍是 ANNOTATION。"""
    e = _entity("TEXT", layer="EQUIPMENT_LABEL", x=1.0, y=2.0)
    e["text_content"] = "Conveyor 2m"
    assets = svc.classify_entity([e], "v1")
    assert assets[0].type == AssetType.ANNOTATION


def test_mtext_overrides_conveyor_layer(svc):
    e = _entity("MTEXT", layer="CONVEYOR_TAGS", x=0.0, y=0.0)
    e["text_content"] = "STEP 1"
    assets = svc.classify_entity([e], "v1")
    assert assets[0].type == AssetType.ANNOTATION


def test_dimension_overrides_system_blacklist(svc):
    """DEFPOINTS 是系统层黑名单, 但 DIMENSION 应仍被识别为 ANNOTATION。"""
    e = _entity("DIMENSION", layer="DEFPOINTS", x=5.0, y=5.0)
    assets = svc.classify_entity([e], "v1")
    assert assets[0].type == AssetType.ANNOTATION
    assert assets[0].confidence >= 0.85


def test_text_on_adsk_system_layer_still_annotation(svc):
    e = _entity("TEXT", layer="ADSK_SYSTEM_VIEWPORT", x=0.0, y=0.0)
    e["text_content"] = "view 1"
    assets = svc.classify_entity([e], "v1")
    assert assets[0].type == AssetType.ANNOTATION


# ════════════════ 负面: 非注释实体不应被影响 ════════════════

def test_insert_block_not_annotation(svc):
    e = _entity("INSERT", layer="0", x=0.0, y=0.0, block_name="Conveyor_2m")
    assets = svc.classify_entity([e], "v1")
    assert assets[0].type == AssetType.CONVEYOR


def test_lwpolyline_zone_not_annotation(svc):
    e = _entity("LWPOLYLINE", layer="0", x=0.0, y=0.0,
                is_closed=True, vertex_count=8)
    assets = svc.classify_entity([e], "v1")
    assert assets[0].type == AssetType.ZONE


def test_circle_not_annotation(svc):
    e = _entity("CIRCLE", layer="0", x=0.0, y=0.0)
    assets = svc.classify_entity([e], "v1")
    assert assets[0].type != AssetType.ANNOTATION


# ════════════════ 图层映射: ANNOTATION 关键字 ════════════════

def test_layer_map_annotation_keyword_for_unknown_entity(svc):
    """对非 TEXT 实体, ANNOTATION 图层关键字也将其归为 ANNOTATION。
    例如: HATCH 在 'ANNOTATION_FILL' 图层 → ANNOTATION (via _LAYER_ASSET_MAP)。
    但 HATCH 几何信号 = ZONE, 故最终结果取决于优先级。
    本测试只验证 _LAYER_ASSET_MAP 已更新。
    """
    from agents.parse_agent.service import _LAYER_ASSET_MAP
    assert _LAYER_ASSET_MAP["DIM"] == AssetType.ANNOTATION
    assert _LAYER_ASSET_MAP["TXT"] == AssetType.ANNOTATION
    assert _LAYER_ASSET_MAP["ANNOTATION"] == AssetType.ANNOTATION


# ════════════════ 枚举完整性 ════════════════

def test_asset_type_annotation_enum_value():
    assert AssetType.ANNOTATION.value == "Annotation"


def test_annotation_distinct_from_other():
    assert AssetType.ANNOTATION != AssetType.OTHER
