"""PT-P0-05: 资产识别与置信度评分 — block_name 多信号分类 + 质量聚合。

TDD RED: 验证 classify_entity 的多信号置信度公式，以及 SiteModel 的质量聚合指标。
输入组: G-P0-BASE-01 (机加车间), G-VER-2000 (example_2000)
"""
import math

import pytest

from shared.models import AssetType

# ────────────────── 辅助 ──────────────────

pytestmark = [pytest.mark.p0]


# ══════════════════════════════════════════
# A. block_name 信号 — 单实体分类准确性
# ══════════════════════════════════════════


class TestBlockNameClassification:
    """验证 INSERT 实体的 block_name 能正确驱动资产类型。"""

    def test_conveyor_block(self, parse_service):
        """Conveyor_2m → CONVEYOR。"""
        entity = {"type": "INSERT", "layer": "STEP_1", "handle": "A1",
                  "block_name": "Conveyor_2m",
                  "coords": {"x": 100.0, "y": 200.0, "z": 0.0}}
        assets = parse_service.classify_entity([entity], "AeroOntology-v1.0")
        assert len(assets) == 1
        assert assets[0].type == AssetType.CONVEYOR

    def test_cnc_block(self, parse_service):
        """CNC → EQUIPMENT。"""
        entity = {"type": "INSERT", "layer": "0", "handle": "A2",
                  "block_name": "CNC",
                  "coords": {"x": 0.0, "y": 0.0, "z": 0.0}}
        assets = parse_service.classify_entity([entity], "AeroOntology-v1.0")
        assert assets[0].type == AssetType.EQUIPMENT

    def test_hoist_block(self, parse_service):
        """Hoist 4x5m → LIFTING_POINT。"""
        entity = {"type": "INSERT", "layer": "0", "handle": "A3",
                  "block_name": "Hoist 4x5m",
                  "coords": {"x": 0.0, "y": 0.0, "z": 0.0}}
        assets = parse_service.classify_entity([entity], "AeroOntology-v1.0")
        assert assets[0].type == AssetType.LIFTING_POINT

    def test_chinese_equipment_block(self, parse_service):
        """珩磨机 → EQUIPMENT (中文设备名)。"""
        entity = {"type": "INSERT", "layer": "0", "handle": "A4",
                  "block_name": "珩磨机",
                  "coords": {"x": 0.0, "y": 0.0, "z": 0.0}}
        assets = parse_service.classify_entity([entity], "AeroOntology-v1.0")
        assert assets[0].type == AssetType.EQUIPMENT

    def test_cleaning_machine_block(self, parse_service):
        """工艺缸盖清洗机 → EQUIPMENT。"""
        entity = {"type": "INSERT", "layer": "0", "handle": "A5",
                  "block_name": "工艺缸盖清洗机",
                  "coords": {"x": 0.0, "y": 0.0, "z": 0.0}}
        assets = parse_service.classify_entity([entity], "AeroOntology-v1.0")
        assert assets[0].type == AssetType.EQUIPMENT

    def test_assembly_block(self, parse_service):
        """缸盖罩装配 → EQUIPMENT (装配工位)。"""
        entity = {"type": "INSERT", "layer": "0", "handle": "A6",
                  "block_name": "缸盖罩装配",
                  "coords": {"x": 0.0, "y": 0.0, "z": 0.0}}
        assets = parse_service.classify_entity([entity], "AeroOntology-v1.0")
        assert assets[0].type == AssetType.EQUIPMENT

    def test_roller_conveyor_chinese(self, parse_service):
        """辊道-1米 → CONVEYOR。"""
        entity = {"type": "INSERT", "layer": "0", "handle": "A7",
                  "block_name": "辊道-1米",
                  "coords": {"x": 0.0, "y": 0.0, "z": 0.0}}
        assets = parse_service.classify_entity([entity], "AeroOntology-v1.0")
        assert assets[0].type == AssetType.CONVEYOR

    def test_anonymous_block_stays_other(self, parse_service):
        """A$C74181755 (匿名块) → OTHER。"""
        entity = {"type": "INSERT", "layer": "0", "handle": "A8",
                  "block_name": "A$C74181755",
                  "coords": {"x": 0.0, "y": 0.0, "z": 0.0}}
        assets = parse_service.classify_entity([entity], "AeroOntology-v1.0")
        assert assets[0].type == AssetType.OTHER

    def test_pallet_block(self, parse_service):
        """托盘 → EQUIPMENT (物料载体)。"""
        entity = {"type": "INSERT", "layer": "0", "handle": "A9",
                  "block_name": "托盘",
                  "coords": {"x": 0.0, "y": 0.0, "z": 0.0}}
        assets = parse_service.classify_entity([entity], "AeroOntology-v1.0")
        assert assets[0].type == AssetType.EQUIPMENT


# ══════════════════════════════════════════
# B. 置信度连续性与区分度
# ══════════════════════════════════════════


class TestConfidenceDistribution:
    """验证多信号公式产生有区分度的置信度（不再只有 3 个离散值）。"""

    def test_named_block_higher_than_anonymous(self, parse_service):
        """命名 INSERT 的置信度 > 匿名 INSERT。"""
        named = {"type": "INSERT", "layer": "0", "handle": "B1",
                 "block_name": "CNC", "coords": {"x": 0, "y": 0, "z": 0}}
        anon = {"type": "INSERT", "layer": "0", "handle": "B2",
                "block_name": "A$C74181755", "coords": {"x": 0, "y": 0, "z": 0}}
        r = parse_service.classify_entity([named, anon], "AeroOntology-v1.0")
        assert r[0].confidence > r[1].confidence

    def test_insert_with_coords_higher_than_without(self, parse_service):
        """有坐标的实体置信度 > 无坐标的。"""
        with_coords = {"type": "INSERT", "layer": "0", "handle": "B3",
                       "block_name": "CNC", "coords": {"x": 10, "y": 20, "z": 0}}
        without = {"type": "LINE", "layer": "0", "handle": "B4"}
        r = parse_service.classify_entity([with_coords, without], "AeroOntology-v1.0")
        assert r[0].confidence > r[1].confidence

    def test_confidence_has_more_than_3_distinct_values(self, parse_service):
        """多信号组合应产出 > 3 个不同置信度值。"""
        entities = [
            {"type": "INSERT", "layer": "EQUIPMENT", "handle": "C1",
             "block_name": "CNC", "coords": {"x": 0, "y": 0, "z": 0}},
            {"type": "INSERT", "layer": "0", "handle": "C2",
             "block_name": "A$C123", "coords": {"x": 0, "y": 0, "z": 0}},
            {"type": "LINE", "layer": "0", "handle": "C3",
             "coords": {"x": 0, "y": 0, "z": 0}},
            {"type": "LWPOLYLINE", "layer": "ZONE", "handle": "C4",
             "is_closed": True, "vertex_count": 20,
             "coords": {"x": 0, "y": 0, "z": 0}},
            {"type": "MTEXT", "layer": "0", "handle": "C5"},
        ]
        r = parse_service.classify_entity(entities, "AeroOntology-v1.0")
        distinct = len({a.confidence for a in r})
        assert distinct > 3, f"只有 {distinct} 个不同置信度值，期望 > 3"


# ══════════════════════════════════════════
# C. 几何模式信号 — 闭合 polyline
# ══════════════════════════════════════════


class TestGeometryPatternSignal:
    """验证 is_closed + vertex_count 对分类的影响。"""

    def test_closed_polyline_with_many_vertices_is_zone(self, parse_service):
        """闭合多边形 (>= 4 顶点) → ZONE。"""
        entity = {"type": "LWPOLYLINE", "layer": "0", "handle": "D1",
                  "is_closed": True, "vertex_count": 8,
                  "coords": {"x": 0, "y": 0, "z": 0}}
        assets = parse_service.classify_entity([entity], "AeroOntology-v1.0")
        assert assets[0].type == AssetType.ZONE

    def test_open_polyline_not_zone(self, parse_service):
        """开放多边形 → 非 ZONE。"""
        entity = {"type": "LWPOLYLINE", "layer": "0", "handle": "D2",
                  "is_closed": False, "vertex_count": 5,
                  "coords": {"x": 0, "y": 0, "z": 0}}
        assets = parse_service.classify_entity([entity], "AeroOntology-v1.0")
        assert assets[0].type != AssetType.ZONE


# ══════════════════════════════════════════
# D. entity_extract 信号丰富度
# ══════════════════════════════════════════


class TestEntityExtractEnrichment:
    """验证 entity_extract 输出包含 block_name / is_closed / vertex_count。"""

    def test_insert_has_block_name(self, parse_service, g_ver_2000):
        """INSERT 实体必须携带 block_name 字段。"""
        content = g_ver_2000.read_bytes()
        fmt = parse_service.format_detect(content, g_ver_2000.name)
        entities = parse_service.entity_extract(content, fmt)
        inserts = [e for e in entities if e["type"] == "INSERT"]
        assert len(inserts) > 0, "应有 INSERT 实体"
        for ins in inserts:
            assert "block_name" in ins, f"INSERT 实体 {ins.get('handle')} 缺少 block_name"

    def test_polyline_has_is_closed(self, parse_service, g_ver_2000):
        """LWPOLYLINE 实体必须携带 is_closed 字段。"""
        content = g_ver_2000.read_bytes()
        fmt = parse_service.format_detect(content, g_ver_2000.name)
        entities = parse_service.entity_extract(content, fmt)
        polys = [e for e in entities if e["type"] in ("LWPOLYLINE", "POLYLINE")]
        assert len(polys) > 0, "应有 polyline 实体"
        for p in polys:
            assert "is_closed" in p, f"Polyline {p.get('handle')} 缺少 is_closed"

    def test_polyline_has_vertex_count(self, parse_service, g_ver_2000):
        """LWPOLYLINE 实体必须携带 vertex_count 字段。"""
        content = g_ver_2000.read_bytes()
        fmt = parse_service.format_detect(content, g_ver_2000.name)
        entities = parse_service.entity_extract(content, fmt)
        polys = [e for e in entities if e["type"] in ("LWPOLYLINE", "POLYLINE")]
        for p in polys:
            assert "vertex_count" in p, f"Polyline {p.get('handle')} 缺少 vertex_count"
            assert isinstance(p["vertex_count"], int)


# ══════════════════════════════════════════
# E. QualityVerdict + 聚合指标
# ══════════════════════════════════════════


class TestQualityVerdict:
    """验证 SiteModel 包含质量聚合指标和 QualityVerdict。"""

    def test_statistics_has_quality_block(self, parse_service, g_ver_2000):
        """SiteModel.statistics 应包含 quality 子字典。"""
        content = g_ver_2000.read_bytes()
        sm, ctx = parse_service.execute(content, g_ver_2000.name)
        assert "quality" in sm.statistics, "statistics 缺少 quality 字段"

    def test_quality_block_fields(self, parse_service, g_ver_2000):
        """quality 子字典包含必需聚合字段。"""
        content = g_ver_2000.read_bytes()
        sm, ctx = parse_service.execute(content, g_ver_2000.name)
        q = sm.statistics["quality"]
        for field in ("avg_confidence", "min_confidence", "max_confidence",
                      "stdev_confidence", "low_confidence_count",
                      "low_confidence_ratio", "classified_ratio", "verdict"):
            assert field in q, f"quality 缺少 {field}"

    def test_avg_confidence_in_range(self, parse_service, g_ver_2000):
        """avg_confidence 在 [0, 1]。"""
        content = g_ver_2000.read_bytes()
        sm, ctx = parse_service.execute(content, g_ver_2000.name)
        avg = sm.statistics["quality"]["avg_confidence"]
        assert 0.0 <= avg <= 1.0

    def test_classified_ratio_positive(self, parse_service, g_ver_2000):
        """至少有部分资产被分为非 Other 类型。"""
        content = g_ver_2000.read_bytes()
        sm, ctx = parse_service.execute(content, g_ver_2000.name)
        ratio = sm.statistics["quality"]["classified_ratio"]
        assert ratio > 0.0, "classified_ratio = 0 表示所有资产仍为 Other"

    def test_verdict_is_valid_enum(self, parse_service, g_ver_2000):
        """verdict 是合法的 QualityVerdict 值。"""
        content = g_ver_2000.read_bytes()
        sm, ctx = parse_service.execute(content, g_ver_2000.name)
        verdict = sm.statistics["quality"]["verdict"]
        assert verdict in ("SUCCESS", "SUCCESS_WITH_WARNINGS", "DEGRADED", "FAILED")

    def test_mcp_context_reflects_verdict(self, parse_service, g_ver_2000):
        """当有质量警告时, mcp_context.status 应为 SUCCESS_WITH_WARNINGS。"""
        content = g_ver_2000.read_bytes()
        sm, ctx = parse_service.execute(content, g_ver_2000.name)
        verdict = sm.statistics["quality"]["verdict"]
        if verdict == "SUCCESS_WITH_WARNINGS":
            assert ctx.status.value == "SUCCESS_WITH_WARNINGS"


# ══════════════════════════════════════════
# F. 真实数据回归 — 机加车间升级验证
# ══════════════════════════════════════════


class TestRealDataQualityUpgrade:
    """验证真实数据在多信号分类后的质量提升。"""

    def test_jijia_has_conveyors(self, parse_service, g_p0_base_01):
        """机加车间应检出 Conveyor 类型资产 (Conveyor_2m block)。"""
        content = g_p0_base_01.read_bytes()
        sm, _ = parse_service.execute(content, g_p0_base_01.name)
        conveyors = [a for a in sm.assets if a.type == AssetType.CONVEYOR]
        assert len(conveyors) >= 200, f"只检出 {len(conveyors)} 个 Conveyor, 期望 >= 200"

    def test_jijia_has_equipment(self, parse_service, g_p0_base_01):
        """机加车间应检出 Equipment 类型资产 (CNC, 珩磨机 etc)。"""
        content = g_p0_base_01.read_bytes()
        sm, _ = parse_service.execute(content, g_p0_base_01.name)
        equip = [a for a in sm.assets if a.type == AssetType.EQUIPMENT]
        assert len(equip) >= 20, f"只检出 {len(equip)} 个 Equipment, 期望 >= 20"

    def test_jijia_has_lifting_points(self, parse_service, g_p0_base_01):
        """机加车间应检出 LiftingPoint (Hoist 4x5m block)。"""
        content = g_p0_base_01.read_bytes()
        sm, _ = parse_service.execute(content, g_p0_base_01.name)
        hoists = [a for a in sm.assets if a.type == AssetType.LIFTING_POINT]
        assert len(hoists) >= 3, f"只检出 {len(hoists)} 个 LiftingPoint, 期望 >= 3"

    def test_jijia_classified_ratio_above_threshold(self, parse_service, g_p0_base_01):
        """机加车间 classified_ratio 应 >= 0.49 (IMP-03 坐标过滤后略降)。"""
        content = g_p0_base_01.read_bytes()
        sm, _ = parse_service.execute(content, g_p0_base_01.name)
        q = sm.statistics["quality"]
        assert q["classified_ratio"] >= 0.49, (
            f"classified_ratio = {q['classified_ratio']}, 期望 >= 0.49"
        )

    def test_jijia_has_links(self, parse_service, g_p0_base_01):
        """分类修复后，机加车间应能生成关系链接 (links > 0)。"""
        content = g_p0_base_01.read_bytes()
        sm, _ = parse_service.execute(content, g_p0_base_01.name)
        assert len(sm.links) > 0, "修复分类后应有非零关系链接"


# ══════════════════════════════════════════
# G. 低置信路由 (PT-P0-06 对齐)
# ══════════════════════════════════════════


class TestLowConfidenceRouting:
    """验证低置信资产被标记，不被静默放行。"""

    LOW_THRESHOLD = 0.4

    def test_low_confidence_items_in_context(self, parse_service, g_ver_2000):
        """mcp_context 包含 low_confidence_items 步骤摘要。"""
        content = g_ver_2000.read_bytes()
        sm, ctx = parse_service.execute(content, g_ver_2000.name)
        q = sm.statistics["quality"]
        # 低置信数量与实际资产一致
        low_assets = [a for a in sm.assets if a.confidence < self.LOW_THRESHOLD]
        assert q["low_confidence_count"] == len(low_assets)

    def test_low_confidence_ratio_consistent(self, parse_service, g_ver_2000):
        """low_confidence_ratio = low_confidence_count / total_assets。"""
        content = g_ver_2000.read_bytes()
        sm, ctx = parse_service.execute(content, g_ver_2000.name)
        q = sm.statistics["quality"]
        total = len(sm.assets)
        if total > 0:
            expected = q["low_confidence_count"] / total
            assert abs(q["low_confidence_ratio"] - expected) < 1e-3
