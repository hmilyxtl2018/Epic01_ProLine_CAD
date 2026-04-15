"""LayoutAgent 单元测试。"""

import pytest
from agents.layout_agent.service import LayoutService


class TestLayoutService:
    """LayoutAgent 核心功能测试。"""

    @pytest.fixture
    def service(self):
        return LayoutService()

    @pytest.mark.unit
    def test_build_search_space(self, service):
        """S4-TC01: 搜索空间定义。"""
        with pytest.raises(NotImplementedError):
            service.build_search_space(None, [])

    @pytest.mark.unit
    def test_initialize_population(self, service):
        """S4-TC02: 种群初始化。"""
        with pytest.raises(NotImplementedError):
            service.initialize_population({}, 100)

    @pytest.mark.unit
    def test_ga_convergence(self, service):
        """S4-TC03: GA 收敛性测试。"""
        with pytest.raises(NotImplementedError):
            service.run_ga([], None)

    @pytest.mark.unit
    def test_collision_check(self, service):
        """S4-TC04: R-Tree 碰撞检测。"""
        with pytest.raises(NotImplementedError):
            service.collision_check({})

    @pytest.mark.unit
    def test_execute_produces_top3(self, service):
        """S4-TC05: 完整管线 — 输出 Top3 方案。"""
        with pytest.raises(NotImplementedError):
            service.execute("SM-001")
