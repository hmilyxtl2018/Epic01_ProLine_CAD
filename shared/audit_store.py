"""ProLine CAD — AuditStore 审计存储接口。

所有 Agent / Tool 的执行记录（mcp_context）和审批文档（PDF、proof artifacts）
的持久化存储与检索接口。支持 S3 + DB 双冗余。
"""

from __future__ import annotations

from shared.mcp_protocol import MCPContext
from shared.models import AuditRecord


class AuditStore:
    """审计存储服务 — 负责 mcp_context 和审批记录的持久化。

    生产实现将使用 PostgreSQL + S3/MinIO 双冗余存储。
    """

    def save_context(self, context: MCPContext) -> str:
        """保存 MCP 上下文到持久层，返回上下文 ID。"""
        raise NotImplementedError

    def get_context(self, mcp_context_id: str) -> MCPContext:
        """按 mcp_context_id 检索上下文。"""
        raise NotImplementedError

    def get_context_chain(self, mcp_context_id: str) -> list[MCPContext]:
        """获取从根到指定上下文的完整链路。"""
        raise NotImplementedError

    def save_audit_record(self, record: AuditRecord) -> str:
        """保存审计记录，返回 audit_id。"""
        raise NotImplementedError

    def get_audit_record(self, audit_id: str) -> AuditRecord:
        """按 audit_id 检索审计记录。"""
        raise NotImplementedError

    def save_artifact(self, artifact_key: str, content: bytes) -> str:
        """保存 proof artifact（SMT2 文件、PDF 等）到对象存储，返回 URL。"""
        raise NotImplementedError

    def get_artifact(self, artifact_url: str) -> bytes:
        """从对象存储检索 proof artifact。"""
        raise NotImplementedError
