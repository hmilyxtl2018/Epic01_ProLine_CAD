"""LLM 工艺约束抽取 IO 契约（ADR-0010 / kg_execution_tasks_v1 T2）。

两阶段抽取流水线的边界数据结构：

- **Stage A（候选定位）**：把 chunk 拆成"可能含约束的 span 候选"。
  入：``DocumentChunk``；出：``ExtractCandidate``。
- **Stage B（结构化）**：把候选 span 抽成完整的 ``ExtractedConstraint``。
  入：``ExtractCandidate`` + chunk 上下文；出：``ExtractedConstraint``。

写入数据库的语义见 ADR-0010 §2.2：
- ``ExtractedConstraint`` → ``process_constraints`` 一行
  （``parse_method='LLM_INFERENCE'`` / ``review_status='draft'`` / ``is_active=False``）
- ``ExtractedConstraint.span_text`` 等字段 → ``constraint_extractions`` 一行
  （``extractor_kind='llm'`` / ``span_hash=sha256(span_text)``）

所有模型为 Pydantic v2，遵循仓库规约：
- ``model_config = ConfigDict(...)``，禁止 ``class Config:``；
- 跨边界字段全部带类型与边界校验；
- 每个模型有中文 docstring。
"""

from __future__ import annotations

import hashlib
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from shared.models import (
    ConstraintAuthority,
    ConstraintCategory,
    ConstraintClass,
    ConstraintConformance,
    ConstraintKind,
    ConstraintSeverity,
    LifecyclePhase,
)

# ── 字段长度上限（与 0028 / 0014 CHECK 一致） ──
_MAX_SPAN_TEXT_LEN = 1000      # constraint_extractions.ck_ce_span_text_len
_MAX_CHUNK_TEXT_LEN = 4000     # Stage A 输入 chunk 截断上限
_MAX_REASON_LEN = 200          # 候选 span 解释
_MAX_DOCUMENT_ID_LEN = 128
_MAX_CHUNK_ID_LEN = 64
_MAX_CONTEXT_ID_LEN = 100      # mcp_contexts.mcp_context_id


# ════════════════════════ Stage A — 切分输入 ════════════════════════


class DocumentChunk(BaseModel):
    """文档分块：Stage A 切分服务的最小输入单位。

    一个 chunk 来自一份文档的一段连续字符区间；``content_hash`` 为
    ``sha256(text)``，用于幂等性与去重。
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    document_id: str = Field(..., min_length=1, max_length=_MAX_DOCUMENT_ID_LEN)
    chunk_id: str = Field(..., min_length=1, max_length=_MAX_CHUNK_ID_LEN)
    page: int = Field(..., ge=0)
    char_start: int = Field(..., ge=0)
    char_end: int = Field(..., ge=0)
    text: str = Field(..., min_length=1, max_length=_MAX_CHUNK_TEXT_LEN)
    content_hash: str = Field(
        ..., pattern=r"^[0-9a-f]{64}$",
        description="sha256(text) 64-char lowercase hex.",
    )

    @model_validator(mode="after")
    def _char_window_consistent(self) -> DocumentChunk:
        if self.char_end <= self.char_start:
            raise ValueError("char_end must be greater than char_start")
        if self.content_hash != hashlib.sha256(self.text.encode("utf-8")).hexdigest():
            raise ValueError("content_hash does not match sha256(text)")
        return self


# ════════════════════════ Stage A — 候选输出 ════════════════════════


class ExtractCandidate(BaseModel):
    """Stage A 输出：一个潜在含约束的 span 候选。

    span 坐标基于 ``DocumentChunk.text`` 的局部偏移（**非**全文档坐标）；
    服务层在写库时换算为全文档坐标后存入 ``constraint_extractions``。
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    chunk_id: str = Field(..., min_length=1, max_length=_MAX_CHUNK_ID_LEN)
    span_start: int = Field(..., ge=0, description="chunk 局部 char offset")
    span_end: int = Field(..., ge=0)
    span_text: str = Field(..., min_length=1, max_length=_MAX_SPAN_TEXT_LEN)
    reason: str = Field(..., min_length=1, max_length=_MAX_REASON_LEN)

    @model_validator(mode="after")
    def _span_window(self) -> ExtractCandidate:
        if self.span_end <= self.span_start:
            raise ValueError("span_end must be greater than span_start")
        return self


# ════════════════════════ Stage B — 结构化产物 ════════════════════════


class SourceSpan(BaseModel):
    """指向源文档的字符区间，写入 ``constraint_extractions``。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    page: int = Field(..., ge=0)
    char_start: int = Field(..., ge=0)
    char_end: int = Field(..., ge=0)

    @model_validator(mode="after")
    def _window_ok(self) -> SourceSpan:
        if self.char_end <= self.char_start:
            raise ValueError("char_end must be greater than char_start")
        return self


class ExtractedScope(BaseModel):
    """LLM 提议的约束作用域候选（未绑定状态）。

    都是"候选"列表 —— 真正的绑定由 M2 BindAgent 写入
    ``constraint_scopes`` / ``constraint_asset_scopes``。
    """

    model_config = ConfigDict(extra="forbid")

    node_rds_candidates: list[str] = Field(
        default_factory=list, max_length=32,
        description="HierarchyNode RDS 编码候选（IEC 81346）。",
    )
    asset_guid_candidates: list[str] = Field(
        default_factory=list, max_length=32,
    )
    product_id: str | None = Field(default=None, max_length=64)


class ExtractedConstraint(BaseModel):
    """Stage B 输出：一条结构化的工艺约束（draft，未审）。

    写库时分裂为：
    - 一行 ``process_constraints``（``review_status='draft'`` /
      ``parse_method='LLM_INFERENCE'`` / ``is_active=False``）
    - 一行 ``constraint_extractions``（``extractor_kind='llm'`` 等）

    业务语义校验：
    - ``ConstraintAuthority`` ↔ ``ConstraintClass`` 联动遵循
      ``ck_authority_class_coherence``（statutory|industry ⇒ hard；
      preference ⇒ 非 hard）。
    - ``valid_to`` 必须晚于 ``valid_from``（与 ``ck_pc_valid_window`` 一致）。
    - ``kind=predecessor`` 时 ``scope.node_rds_candidates`` 至少 2 个，
      用于尽早暴露"前驱关系无双方"型幻觉。
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    kind: ConstraintKind
    category: ConstraintCategory
    cls: ConstraintClass = Field(alias="class")
    severity: ConstraintSeverity
    authority: ConstraintAuthority
    conformance: ConstraintConformance

    rule_expression: str = Field(..., min_length=1, max_length=500)
    rationale: str = Field(..., min_length=1, max_length=1000)

    applicable_phases: list[LifecyclePhase] = Field(..., min_length=1, max_length=8)
    valid_from: datetime | None = None
    valid_to: datetime | None = None

    scope: ExtractedScope

    source_document_id: str = Field(..., min_length=1, max_length=_MAX_DOCUMENT_ID_LEN)
    source_span: SourceSpan
    span_text: str = Field(..., min_length=1, max_length=_MAX_SPAN_TEXT_LEN)

    confidence: float = Field(..., ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _valid_window(self) -> ExtractedConstraint:
        if (
            self.valid_from is not None
            and self.valid_to is not None
            and self.valid_to <= self.valid_from
        ):
            raise ValueError("valid_to must be strictly later than valid_from")
        return self

    @model_validator(mode="after")
    def _authority_class_coherence(self) -> ExtractedConstraint:
        # Mirror DDL ck_authority_class_coherence (ADR-0006 §2.1) so the
        # 422 fires before the row hits Postgres.
        hard_required = {ConstraintAuthority.STATUTORY, ConstraintAuthority.INDUSTRY}
        if self.authority in hard_required and self.cls is not ConstraintClass.HARD:
            raise ValueError(
                "authority statutory|industry requires class=hard "
                "(ck_authority_class_coherence)"
            )
        if (
            self.authority is ConstraintAuthority.PREFERENCE
            and self.cls is ConstraintClass.HARD
        ):
            raise ValueError(
                "authority=preference cannot pair with class=hard "
                "(ck_authority_class_coherence)"
            )
        return self

    @model_validator(mode="after")
    def _predecessor_needs_two_nodes(self) -> ExtractedConstraint:
        if (
            self.kind is ConstraintKind.PREDECESSOR
            and len(self.scope.node_rds_candidates) < 2
        ):
            raise ValueError(
                "kind=predecessor requires >=2 node_rds_candidates "
                "(both ends of the precedence edge)"
            )
        return self

    def span_hash(self) -> str:
        """Deterministic sha256 used in ``constraint_extractions.span_hash``."""
        return hashlib.sha256(self.span_text.encode("utf-8")).hexdigest()


# ════════════════════════ Service-level envelopes ════════════════════════


class ExtractRequest(BaseModel):
    """抽取服务入口请求。

    ``mcp_context_id`` 为整次抽取的根上下文；服务为每个产物挂同一
    ``mcp_context_id`` FK，满足 ADR-0010 §2.2 第 3 条（链路同根）。
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    site_model_id: str = Field(..., min_length=1, max_length=64)
    document_id: str = Field(..., min_length=1, max_length=_MAX_DOCUMENT_ID_LEN)
    chunks: list[DocumentChunk] = Field(..., min_length=1, max_length=50)
    mcp_context_id: str = Field(..., min_length=1, max_length=_MAX_CONTEXT_ID_LEN)


class ExtractResponse(BaseModel):
    """抽取服务出口响应。

    ``warnings`` 用于非致命问题：例如 LLM 输出的 ``span_text`` 在原文
    chunk 中未命中（被服务层丢弃）、置信度低于阈值、超出 ``max_chunks``
    的截断等。客户端可据此提示用户复核。
    """

    model_config = ConfigDict(extra="forbid")

    mcp_context_id: str = Field(..., min_length=1, max_length=_MAX_CONTEXT_ID_LEN)
    candidates_count: int = Field(..., ge=0)
    extracted_count: int = Field(..., ge=0)
    drafts_written: int = Field(..., ge=0)
    evidence_written: int = Field(..., ge=0)
    warnings: list[str] = Field(default_factory=list, max_length=64)


# ── re-exports ─────────────────────────────────────────────────────────


def chunk_content_hash(text: str) -> str:
    """Helper: sha256(text) — used by callers building ``DocumentChunk``."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


__all__: list[str] = [
    "DocumentChunk",
    "ExtractCandidate",
    "ExtractedConstraint",
    "ExtractedScope",
    "ExtractRequest",
    "ExtractResponse",
    "SourceSpan",
    "chunk_content_hash",
]
