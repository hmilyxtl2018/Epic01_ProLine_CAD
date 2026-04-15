"""ConstraintAgent — 核心业务逻辑。

实现约束检查的完整管线:
约束集加载 → Z3 编码 → SAT 求解 → UNSAT Core → 软约束评分 → 冲突报告

参考: ExcPlan/Agent Profile §2.3 Action Flow
"""

from __future__ import annotations

from shared.models import (
    ConstraintCheckResult,
    ConstraintSet,
    SiteModel,
    SoftScore,
    Violation,
)
from shared.mcp_protocol import MCPContext


class ConstraintService:
    """约束检查服务 — ConstraintAgent 的核心。"""

    def load_constraint_set(self, constraint_set_id: str) -> ConstraintSet:
        """步骤 1: 约束集加载 — 从数据库读取约束定义，分类 HARD/SOFT。"""
        raise NotImplementedError

    def encode_for_z3(self, site_model: SiteModel, constraint_set: ConstraintSet) -> object:
        """步骤 2: 约束编码为 Z3 表达式。

        注意: 避免 sqrt 非线性表达，优先使用平方距离比较或
        预计算几何事实提供给 Z3。参考修正版执行计划 §四.4。
        """
        raise NotImplementedError

    def solve(self, z3_problem: object, timeout_ms: int = 10000) -> str:
        """步骤 3: Z3 求解 — 返回 SAT/UNSAT。"""
        raise NotImplementedError

    def extract_unsat_core(self, z3_problem: object) -> list[str]:
        """步骤 4: UNSAT Core 提取 — 识别冲突约束子集。"""
        raise NotImplementedError

    def compute_soft_scores(
        self, site_model: SiteModel, constraint_set: ConstraintSet
    ) -> list[SoftScore]:
        """步骤 5: 软约束评分。

        score = 0.4×间距合规 + 0.3×物流效率 + 0.2×吊运安全 + 0.1×扩展性
        """
        raise NotImplementedError

    def generate_violation_report(
        self, unsat_core: list[str], constraint_set: ConstraintSet
    ) -> list[Violation]:
        """步骤 6: 硬约束冲突报告 + 改进建议。"""
        raise NotImplementedError

    def execute(
        self, site_model_id: str, constraint_set_id: str = "CS-001"
    ) -> tuple[ConstraintCheckResult, MCPContext]:
        """完整执行管线 — 串联步骤 1-6，输出约束检查结果 + MCP Context。"""
        raise NotImplementedError


class Z3Gateway:
    """Z3 Solver 封装层 — /mcp/tool/validate_with_z3 的实现。

    负责 Z3 solver 的生命周期管理、超时控制和 proof artifact 保存。
    """

    def validate(self, site_model_id: str, formal_constraints: list[str]) -> dict:
        """验证约束满足性。返回 {sat_result, unsat_core, proof_artifact_url}。"""
        raise NotImplementedError


class ConstraintTranslator:
    """LLM 辅助约束翻译器 — /mcp/tool/constraint_translate 的实现。

    将 SOP 自然语言段落翻译为结构化约束 JSON，
    强制经过 Z3 验证。LLM 仅作为翻译器，不作为权威来源。
    """

    def translate(
        self, sop_segments: list[str], scope_assets: list[str], ontology_version: str
    ) -> dict:
        """翻译 SOP 段落为形式化约束。"""
        raise NotImplementedError
