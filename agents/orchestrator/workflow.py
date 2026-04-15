"""Orchestrator — 工作流状态机。

实现 Agent 链路编排:
PENDING → PARSE_RUNNING → CONSTRAINT_CHECKING → LAYOUT_OPTIMIZING → [ITERATING] → COMPLETE

支持重试策略、超时控制和迭代循环管理。

参考: ExcPlan/执行计划 §5.1
"""

from __future__ import annotations

from shared.models import WorkflowState
from shared.mcp_protocol import MCPContext


class WorkflowStateMachine:
    """工作流状态机 — 管理 Agent 执行链路。"""

    def __init__(self):
        self.state: WorkflowState = WorkflowState.PENDING
        self.context_chain: list[MCPContext] = []
        self.iteration: int = 0
        self.max_iterations: int = 3

    def transition(self, new_state: WorkflowState) -> None:
        """状态转换 — 带合法转换校验。"""
        raise NotImplementedError

    def trigger_parse(self, cad_file_content: bytes, filename: str) -> MCPContext:
        """触发 ParseAgent (Agent1)。"""
        raise NotImplementedError

    def trigger_constraint_check(self, site_model_id: str) -> MCPContext:
        """触发 ConstraintAgent (Agent2)。"""
        raise NotImplementedError

    def trigger_layout_optimize(self, site_model_id: str, violations: list[str]) -> MCPContext:
        """触发 LayoutAgent (Agent3)。"""
        raise NotImplementedError

    def should_iterate(self, layout_result: dict) -> bool:
        """判断是否需要迭代回环（Agent3 → Agent2）。

        收敛条件: 满足度 >= 0.80 且无硬约束违规，或达 max_iterations。
        """
        raise NotImplementedError

    def execute_full_pipeline(self, cad_file: bytes, filename: str) -> dict:
        """执行完整闭环 — CAD → Agent1 → Agent2 → Agent3 → [loop] → COMPLETE。"""
        raise NotImplementedError
