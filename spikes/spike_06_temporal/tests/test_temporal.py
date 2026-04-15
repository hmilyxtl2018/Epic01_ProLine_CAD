"""
Spike-6 测试用例：Temporal 工作流编排可靠性
==========================================
Test Case IDs: S6-TC01 ~ S6-TC08 (关键技术验证计划 §7.2)

Go/No-Go 必须标准:
  - 全链路 Workflow 执行成功 = 100%
  - 重试机制 (3次内恢复) 正确触发
  - 条件分支 (瓶颈回写) 正确执行
  - Worker 重启后恢复, 无数据丢失
"""
import time
import pytest
from conftest import Thresholds

# ════════════════════════════════════════════════════════════════
# 待实现模块导入 — TDD RED phase
# ════════════════════════════════════════════════════════════════
from spike_06_temporal.src.workflows import FullPipelineWorkflow
from spike_06_temporal.src.activities import (
    ParseDWGActivity,
    GenerateLayoutActivity,
    RunDESActivity,
    GenerateReportActivity,
)
from spike_06_temporal.src.worker import WorkflowWorker
from spike_06_temporal.src.client import WorkflowClient
