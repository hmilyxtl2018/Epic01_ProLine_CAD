"""PT-P0-02: 多实体与多图层实体提取
====================================
功能测试计划 §7.4 测试卡 — ParseAgent 能力 P-02

测试目标: 验证 ParseAgent 能从真实工业图中提取稳定实体集合
输入组:   G-P0-BASE-01 (机加车间), G-SEM-02 (冷轧)
前置条件: 实体提取链路已启用；允许输出实体统计信息

TDD 状态: RED — ParseService.entity_extract() 尚未实现,
          所有测试预期因 NotImplementedError 失败。
          实现 format_detect + entity_extract 后应全部变绿。
"""
import pytest
from pathlib import Path


@pytest.mark.p0
class TestPTP002_EntityExtract:
    """PT-P0-02: 多实体与多图层实体提取。

    执行步骤 (来自测试卡):
    1. 输入 20180109_机加车间平面布局图.dwg
    2. 输入 cold_rolled_steel_production.dwg
    3. 执行 entity extract
    4. 记录实体总数、图层分布、实体类型分布

    核心断言:
    1. total_entities_parsed > 0
    2. 至少存在多图层对象
    3. 输出结构可继续被坐标归一化和资产识别消费

    失败判定:
    无实体输出、输出结构不完整、后续步骤无法消费实体结果 → 任一即失败
    """

    # ── 断言 1: 实体数量 > 0 ──

    def test_base01_entities_nonempty(self, parse_service, g_p0_base_01: Path):
        """G-P0-BASE-01 (机加车间): 解析后实体数量 > 0。"""
        content = g_p0_base_01.read_bytes()
        fmt = parse_service.format_detect(content, g_p0_base_01.name)
        entities = parse_service.entity_extract(content, fmt)

        assert isinstance(entities, list), "entity_extract 应返回 list"
        assert len(entities) > 0, "机加车间图应包含至少 1 个实体"

    def test_sem02_entities_nonempty(self, parse_service, g_sem_02: Path):
        """G-SEM-02 (冷轧产线): 解析后实体数量 > 0。"""
        content = g_sem_02.read_bytes()
        fmt = parse_service.format_detect(content, g_sem_02.name)
        entities = parse_service.entity_extract(content, fmt)

        assert isinstance(entities, list), "entity_extract 应返回 list"
        assert len(entities) > 0, "冷轧产线图应包含至少 1 个实体"

    # ── 断言 2: 多图层对象存在 ──

    def test_base01_multiple_layers(self, parse_service, g_p0_base_01: Path):
        """G-P0-BASE-01: 实体应分布在多个图层上。"""
        content = g_p0_base_01.read_bytes()
        fmt = parse_service.format_detect(content, g_p0_base_01.name)
        entities = parse_service.entity_extract(content, fmt)

        layers = {e.get("layer", "") for e in entities if isinstance(e, dict)}
        assert len(layers) >= 2, (
            f"机加车间图应包含至少 2 个图层, 实际: {layers}"
        )

    def test_sem02_multiple_layers(self, parse_service, g_sem_02: Path):
        """G-SEM-02: 冷轧产线也应包含多图层。"""
        content = g_sem_02.read_bytes()
        fmt = parse_service.format_detect(content, g_sem_02.name)
        entities = parse_service.entity_extract(content, fmt)

        layers = {e.get("layer", "") for e in entities if isinstance(e, dict)}
        assert len(layers) >= 2, (
            f"冷轧产线图应包含至少 2 个图层, 实际: {layers}"
        )

    # ── 断言 2 扩展: 多种实体类型 ──

    def test_base01_multiple_entity_types(self, parse_service, g_p0_base_01: Path):
        """G-P0-BASE-01: 应包含多种实体类型 (LINE, ARC, TEXT 等)。"""
        content = g_p0_base_01.read_bytes()
        fmt = parse_service.format_detect(content, g_p0_base_01.name)
        entities = parse_service.entity_extract(content, fmt)

        types = {e.get("type", "") for e in entities if isinstance(e, dict)}
        assert len(types) >= 2, (
            f"机加车间图应包含至少 2 种实体类型, 实际: {types}"
        )

    # ── 断言 3: 输出结构完整、可消费 ──

    def test_entity_structure_has_required_fields(self, parse_service, g_p0_base_01: Path):
        """每个实体 dict 应包含下游可消费的最小字段集。"""
        content = g_p0_base_01.read_bytes()
        fmt = parse_service.format_detect(content, g_p0_base_01.name)
        entities = parse_service.entity_extract(content, fmt)

        assert len(entities) > 0, "无实体输出"

        # 至少第一个实体应包含 layer 和 type 字段
        sample = entities[0]
        assert isinstance(sample, dict), f"实体应为 dict, 实际: {type(sample)}"
        assert "layer" in sample, "实体缺少 'layer' 字段"
        assert "type" in sample, "实体缺少 'type' 字段"

    def test_entity_extract_idempotent(self, parse_service, g_p0_base_01: Path):
        """同一文件提取两次, 实体数量应一致 (确定性)。"""
        content = g_p0_base_01.read_bytes()
        fmt = parse_service.format_detect(content, g_p0_base_01.name)

        entities_1 = parse_service.entity_extract(content, fmt)
        entities_2 = parse_service.entity_extract(content, fmt)

        assert len(entities_1) == len(entities_2), (
            f"两次提取实体数量不一致: {len(entities_1)} vs {len(entities_2)}"
        )
