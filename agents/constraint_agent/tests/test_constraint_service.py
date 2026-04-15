"""ConstraintAgent 单元测试。"""

import pytest
from agents.constraint_agent.service import ConstraintService, Z3Gateway


class TestConstraintService:
    """ConstraintAgent 核心功能测试。"""

    @pytest.fixture
    def service(self):
        return ConstraintService()

    @pytest.mark.unit
    def test_load_constraint_set(self, service):
        """S3-TC01: 约束集加载。"""
        with pytest.raises(NotImplementedError):
            service.load_constraint_set("CS-001")

    @pytest.mark.unit
    def test_z3_solve_sat(self, service):
        """S3-TC02: Z3 求解 — SAT 场景。"""
        with pytest.raises(NotImplementedError):
            service.solve(None)

    @pytest.mark.unit
    def test_unsat_core_extraction(self, service):
        """S3-TC03: UNSAT Core 提取 — 冲突约束识别。"""
        with pytest.raises(NotImplementedError):
            service.extract_unsat_core(None)

    @pytest.mark.unit
    def test_soft_score_calculation(self, service):
        """S3-TC04: 软约束评分计算。"""
        with pytest.raises(NotImplementedError):
            service.compute_soft_scores(None, None)

    @pytest.mark.unit
    def test_execute_full_pipeline(self, service):
        """S3-TC05: 完整管线执行 — 硬约束检出率 100%。"""
        with pytest.raises(NotImplementedError):
            service.execute("SM-001", "CS-001")


class TestZ3Gateway:
    """Z3 SolverInvoker 测试。"""

    @pytest.mark.unit
    def test_validate_basic(self):
        """S3-TC06: Z3 gateway 基础验证。"""
        gw = Z3Gateway()
        with pytest.raises(NotImplementedError):
            gw.validate("SM-001", ["C-001"])
