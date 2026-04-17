"""PT-P0-08: SiteModel 完整生成
================================
功能测试计划 §7.4 测试卡 — ParseAgent 能力 P-07

测试目标: 验证完整解析流程能生成可被 ConstraintAgent 消费的 SiteModel
输入组:   G-P0-BASE-01 (机加车间平面布局图)
前置条件: ParseAgent 全流程启用；序列化和持久化接口可用

TDD 状态: RED — ParseService.execute() 尚未实现,
          所有测试预期因 NotImplementedError 失败。
          实现完整管线 (format_detect → entity_extract → coord_normalize
          → topology_repair → classify_entity → build_ontology_graph
          → build_site_model) 后应全部变绿。
"""
import json

import pytest
from pathlib import Path

from shared.models import SiteModel, Asset, OntologyLink, CADSource


@pytest.mark.p0
class TestPTP008_SiteModelGeneration:
    """PT-P0-08: SiteModel 完整生成。

    执行步骤 (来自测试卡):
    1. 输入 20180109_机加车间平面布局图.dwg
    2. 依次执行 format detect、entity extract、normalize、
       repair、classify、link、serialize
    3. 检查最终 SiteModel

    核心断言:
    1. 输出存在合法 site_model_id
    2. 包含 assets、links、geometry_integrity_score、statistics
    3. 输出对象能作为 ConstraintAgent 输入

    失败判定:
    SiteModel 缺关键字段、不能序列化、不能被下游消费 → 任一即失败
    """

    # ── 完整管线执行 ──

    def test_execute_returns_site_model(self, parse_service, g_p0_base_01: Path):
        """execute() 应返回 (SiteModel, MCPContext) 元组。"""
        content = g_p0_base_01.read_bytes()
        result = parse_service.execute(content, g_p0_base_01.name)

        assert isinstance(result, tuple), f"execute 应返回 tuple, 实际: {type(result)}"
        assert len(result) == 2, f"execute 应返回 2 元素, 实际: {len(result)}"

        site_model, mcp_ctx = result
        assert isinstance(site_model, SiteModel), (
            f"第一个返回值应为 SiteModel, 实际: {type(site_model)}"
        )

    # ── 断言 1: 合法 site_model_id ──

    def test_site_model_id_format(self, parse_service, g_p0_base_01: Path):
        """site_model_id 应以 'SM-' 开头。"""
        content = g_p0_base_01.read_bytes()
        site_model, _ = parse_service.execute(content, g_p0_base_01.name)

        assert site_model.site_model_id is not None, "site_model_id 为 None"
        assert site_model.site_model_id.startswith("SM-"), (
            f"site_model_id 格式错误: {site_model.site_model_id}"
        )

    # ── 断言 2: 关键字段完整 ──

    def test_has_assets(self, parse_service, g_p0_base_01: Path):
        """SiteModel 应包含非空 assets 列表。"""
        content = g_p0_base_01.read_bytes()
        site_model, _ = parse_service.execute(content, g_p0_base_01.name)

        assert isinstance(site_model.assets, list), "assets 不是 list"
        assert len(site_model.assets) > 0, "assets 为空 — 机加车间图应识别出资产"

    def test_assets_have_required_fields(self, parse_service, g_p0_base_01: Path):
        """每个 Asset 应有 guid、type、coords、confidence。"""
        content = g_p0_base_01.read_bytes()
        site_model, _ = parse_service.execute(content, g_p0_base_01.name)

        for asset in site_model.assets[:5]:  # 抽检前 5 个
            assert asset.asset_guid, f"asset 缺少 guid"
            assert asset.type is not None, f"asset {asset.asset_guid} 缺少 type"
            assert asset.coords is not None, f"asset {asset.asset_guid} 缺少 coords"
            assert 0.0 <= asset.confidence <= 1.0, (
                f"asset {asset.asset_guid} confidence 超范围: {asset.confidence}"
            )

    def test_has_links(self, parse_service, g_p0_base_01: Path):
        """SiteModel 应包含 links 列表 (可空但必须存在)。"""
        content = g_p0_base_01.read_bytes()
        site_model, _ = parse_service.execute(content, g_p0_base_01.name)

        assert isinstance(site_model.links, list), "links 不是 list"

    def test_has_geometry_integrity_score(self, parse_service, g_p0_base_01: Path):
        """SiteModel 应包含 geometry_integrity_score ∈ [0, 1]。"""
        content = g_p0_base_01.read_bytes()
        site_model, _ = parse_service.execute(content, g_p0_base_01.name)

        score = site_model.geometry_integrity_score
        assert 0.0 <= score <= 1.0, (
            f"geometry_integrity_score 超范围: {score}"
        )

    def test_has_statistics(self, parse_service, g_p0_base_01: Path):
        """SiteModel 应包含统计信息字典。"""
        content = g_p0_base_01.read_bytes()
        site_model, _ = parse_service.execute(content, g_p0_base_01.name)

        assert isinstance(site_model.statistics, dict), "statistics 不是 dict"

    def test_has_cad_source(self, parse_service, g_p0_base_01: Path):
        """SiteModel 应绑定来源 CAD 文件信息。"""
        content = g_p0_base_01.read_bytes()
        site_model, _ = parse_service.execute(content, g_p0_base_01.name)

        assert site_model.cad_source is not None, "cad_source 为 None"
        assert site_model.cad_source.filename != "", "cad_source.filename 为空"

    # ── 断言 3: 可序列化、可被下游消费 ──

    def test_serializable_to_json(self, parse_service, g_p0_base_01: Path):
        """SiteModel 应能序列化为 JSON (ConstraintAgent 消费格式)。"""
        content = g_p0_base_01.read_bytes()
        site_model, _ = parse_service.execute(content, g_p0_base_01.name)

        json_str = site_model.model_dump_json()
        assert len(json_str) > 0, "JSON 序列化结果为空"

        # 反序列化验证
        parsed = json.loads(json_str)
        assert "site_model_id" in parsed
        assert "assets" in parsed
        assert "links" in parsed
        assert "geometry_integrity_score" in parsed
        assert "statistics" in parsed

    def test_roundtrip_deserialization(self, parse_service, g_p0_base_01: Path):
        """JSON 序列化 → 反序列化后 SiteModel 字段一致。"""
        content = g_p0_base_01.read_bytes()
        site_model, _ = parse_service.execute(content, g_p0_base_01.name)

        json_str = site_model.model_dump_json()
        restored = SiteModel.model_validate_json(json_str)

        assert restored.site_model_id == site_model.site_model_id
        assert len(restored.assets) == len(site_model.assets)
        assert len(restored.links) == len(site_model.links)

    # ── MCP Context 链路追溯 ──

    def test_mcp_context_populated(self, parse_service, g_p0_base_01: Path):
        """execute 返回的 MCPContext 应包含有效的 context_id 和 agent 标识。"""
        content = g_p0_base_01.read_bytes()
        _, mcp_ctx = parse_service.execute(content, g_p0_base_01.name)

        assert mcp_ctx.mcp_context_id is not None, "mcp_context_id 为 None"
        assert len(mcp_ctx.mcp_context_id) > 0, "mcp_context_id 为空"
        assert mcp_ctx.agent != "", "MCPContext.agent 应标识 ParseAgent"
