"""Orchestrator 单元测试。"""

import pytest
from agents.orchestrator.workflow import WorkflowStateMachine
from shared.models import WorkflowState


class TestWorkflowStateMachine:
    """工作流状态机测试。"""

    @pytest.fixture
    def workflow(self):
        return WorkflowStateMachine()

    @pytest.mark.unit
    def test_initial_state_is_pending(self, workflow):
        """工作流初始状态为 PENDING。"""
        assert workflow.state == WorkflowState.PENDING

    @pytest.mark.unit
    def test_trigger_parse(self, workflow):
        """触发 ParseAgent。"""
        with pytest.raises(NotImplementedError):
            workflow.trigger_parse(b"", "test.dwg")

    @pytest.mark.unit
    def test_full_pipeline(self, workflow):
        """端到端闭环执行。"""
        with pytest.raises(NotImplementedError):
            workflow.execute_full_pipeline(b"", "test.dwg")
