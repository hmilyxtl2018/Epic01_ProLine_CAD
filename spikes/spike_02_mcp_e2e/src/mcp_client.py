"""MCP 客户端 — Stub"""
from dataclasses import dataclass, field


@dataclass
class ToolInfo:
    name: str = ""
    input_schema: dict = field(default_factory=dict)


@dataclass
class ToolResult:
    success: bool = False
    content: dict = field(default_factory=dict)
    mcp_context_id: str | None = None
    error_code: int | str | None = None
    error_message: str | None = None


class MCPStdioClient:
    def __init__(self, server=None, timeout_s: int = 30):
        raise NotImplementedError

    def list_tools(self) -> list[ToolInfo]:
        raise NotImplementedError

    def call_tool(self, name: str, arguments: dict) -> ToolResult:
        raise NotImplementedError

    def call_tools_concurrent(self, calls: list) -> list[ToolResult]:
        raise NotImplementedError


class MCPSSEClient:
    def __init__(self, endpoint: str = "", max_retries: int = 3, retry_delay_s: float = 1):
        raise NotImplementedError

    reconnect_count: int = 0

    def call_tool(self, name: str, arguments: dict) -> ToolResult:
        raise NotImplementedError

    def simulate_disconnect(self):
        raise NotImplementedError
