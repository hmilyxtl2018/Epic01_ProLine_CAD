"""ProLine CAD — MCP (Model Context Protocol) 协议定义。

所有 Agent 间通信的上下文格式，支持全链路追溯。
每次 Agent 调用或 Tool 调用都生成唯一 mcp_context_id，
并通过 parent_context_id 关联上游上下文。

命名规则: ctx-<agent_prefix>-<hex_hash>
示例: ctx-parse-7f3a4e81, ctx-z3-0001, ctx-layout-a3b8f2e1
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from shared.models import AgentStatus


# ════════════════ MCP Context ════════════════


def generate_context_id(prefix: str = "ctx") -> str:
    """生成唯一的 mcp_context_id。

    格式: ctx-<prefix>-<8位hex>
    """
    hex_hash = uuid.uuid4().hex[:8]
    return f"{prefix}-{hex_hash}"


class Provenance(BaseModel):
    """来源信息 — 追踪数据来源和工具版本。"""
    source: str = ""
    sha256: str = ""
    tool_versions: dict[str, str] = Field(default_factory=dict)


class MCPContext(BaseModel):
    """MCP 上下文 — Agent / Tool 调用的完整记录。

    每次 Agent 执行或 Tool 调用都生成一条 MCPContext，
    通过 parent_context_id 链接形成完整的调用链路。
    """
    mcp_context_id: str = Field(default_factory=lambda: generate_context_id())
    agent: str = ""
    agent_version: str = "v1.0"
    parent_context_id: str | None = None
    input_payload: dict[str, Any] = Field(default_factory=dict)
    output_payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    latency_ms: int = 0
    provenance: Provenance = Field(default_factory=Provenance)
    status: AgentStatus = AgentStatus.SUCCESS
    error_message: str | None = None
    step_breakdown: list[dict[str, Any]] = Field(default_factory=list)


class MCPToolRequest(BaseModel):
    """MCP Tool 调用请求的通用格式。"""
    parent_mcp_context_id: str
    tool_name: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class MCPToolResponse(BaseModel):
    """MCP Tool 调用响应的通用格式。"""
    mcp_context_id: str = Field(default_factory=lambda: generate_context_id())
    tool_name: str = ""
    result: dict[str, Any] = Field(default_factory=dict)
    latency_ms: int = 0
    tool_version: str = ""


# ════════════════ 工具函数 ════════════════


def compute_file_sha256(file_content: bytes) -> str:
    """计算文件 SHA-256 哈希。"""
    return hashlib.sha256(file_content).hexdigest()


def link_contexts(parent: MCPContext, child: MCPContext) -> MCPContext:
    """将子上下文链接到父上下文。"""
    child.parent_context_id = parent.mcp_context_id
    return child
