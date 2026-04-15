"""
Spike-2 测试用例：MCP 协议端到端通信
====================================
Test Case IDs: S2-TC01 ~ S2-TC08 (关键技术验证计划 §3.3)

Go/No-Go 必须标准:
  - stdio 100次调用成功率 = 100%
  - SSE 调用成功率 ≥ 99%
  - SSE P99延迟 ≤ 500ms
  - Context 传播链完整性 = 100%
  - 错误码传递正确性 = 100%
"""
import asyncio
import json
import time
import pytest
from conftest import SPIKE2_DATA, Thresholds

# ════════════════════════════════════════════════════════════════
# 待实现模块导入 — TDD RED phase
# ════════════════════════════════════════════════════════════════
from spike_02_mcp_e2e.src.mcp_client import MCPStdioClient, MCPSSEClient
from spike_02_mcp_e2e.src.mcp_server import MockMCPServer
from spike_02_mcp_e2e.src.context_store import ContextStore


@pytest.mark.p0
@pytest.mark.spike2
class TestContextPropagation:
    """S2-TC06: MCP Context 传播链验证"""

    def test_tc06_context_chain(self):
        """Agent_A → Agent_B, B 能读到 A 产出的 context"""
        store = ContextStore()

        # Agent A 产出 context
        ctx_a = store.create_context(
            source_agent="parse-agent",
            payload_type="SiteModel",
            payload_ref="s3://test/site_model_v1.json",
        )
        assert ctx_a.context_id is not None

        # Agent B 读取 parent context 并产出新 context
        ctx_b = store.create_context(
            source_agent="layout-agent",
            payload_type="LayoutCandidate",
            payload_ref="s3://test/layout_v1.json",
            parent_contexts=[ctx_a.context_id],
        )

        # 验证追溯链
        assert ctx_b.parent_contexts == [ctx_a.context_id]
        chain = store.trace_chain(ctx_b.context_id)
        assert len(chain) == 2
        assert chain[0].context_id == ctx_a.context_id
        assert chain[1].context_id == ctx_b.context_id

    def test_tc06_context_version_increment(self):
        """同一 Agent 多次产出应递增版本号"""
        store = ContextStore()

        ctx_v1 = store.create_context(
            source_agent="parse-agent",
            payload_type="SiteModel",
            payload_ref="s3://test/v1.json",
        )
        ctx_v2 = store.create_context(
            source_agent="parse-agent",
            payload_type="SiteModel",
            payload_ref="s3://test/v2.json",
            parent_contexts=[ctx_v1.context_id],
        )

        assert ctx_v2.version > ctx_v1.version

    def test_tc06_full_pipeline_context_chain(self, mock_agent_tools):
        """验证 mock_agent_tools.json 中定义的 5-Agent 传播链"""
        store = ContextStore()
        agents = mock_agent_tools["agents"]

        prev_ctx_id = None
        chain = []
        for agent_def in agents:
            parents = [prev_ctx_id] if prev_ctx_id else []
            ctx = store.create_context(
                source_agent=agent_def["agent_id"],
                payload_type=f"output_{agent_def['agent_id']}",
                payload_ref=f"s3://test/{agent_def['agent_id']}_result.json",
                parent_contexts=parents,
            )
            chain.append(ctx.context_id)
            prev_ctx_id = ctx.context_id

        # 验证完整链路
        full_chain = store.trace_chain(chain[-1])
        assert len(full_chain) == len(agents), (
            f"传播链长度 {len(full_chain)} != Agent数量 {len(agents)}"
        )
