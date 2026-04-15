"""ParseAgent 单元测试。"""

import pytest
from agents.parse_agent.service import ParseService


class TestParseService:
    """ParseAgent 核心功能测试。"""

    @pytest.fixture
    def service(self):
        return ParseService()

    @pytest.mark.unit
    def test_format_detect_dwg(self, service):
        """S1-TC01: DWG 格式检测。"""
        # TODO: 实现时填入测试数据
        with pytest.raises(NotImplementedError):
            service.format_detect(b"", "test.dwg")

    @pytest.mark.unit
    def test_entity_extract(self, service):
        """S1-TC02: CAD 实体提取。"""
        with pytest.raises(NotImplementedError):
            service.entity_extract(b"", "DWG")

    @pytest.mark.unit
    def test_classify_entity_confidence(self, service):
        """S1-TC03: 资产识别置信度评分 — avg_confidence >= 0.90。"""
        with pytest.raises(NotImplementedError):
            service.classify_entity([], "AeroOntology-v1.0")

    @pytest.mark.unit
    def test_execute_full_pipeline(self, service):
        """S1-TC04: 完整管线执行 — 输出 SiteModel。"""
        with pytest.raises(NotImplementedError):
            service.execute(b"", "test.dwg")
