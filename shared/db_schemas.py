"""SQLAlchemy 2.0 Declarative metadata — single source of truth for DDL.

Mirrors `db/migrations/001_initial.sql` exactly so Alembic autogenerate produces
no diff against a freshly-stamped baseline. Pydantic models in `shared/models.py`
remain the runtime source of truth; this module only models the storage shape.

Convention (CLAUDE.md §9, ExcPlan plan r2 §3.4.1.2):
- Every business table carries `schema_version` + `deleted_at` + `mcp_context_id`.
  Those columns are added in revision 0001b (A2), not here, so the baseline matches
  the legacy SQL byte-for-byte.
- All FKs to `mcp_contexts` go via `mcp_context_id` (VARCHAR(100)), not the UUID PK.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

try:
    from geoalchemy2 import Geometry
except ImportError:  # pragma: no cover - geoalchemy2 is required at runtime
    Geometry = None  # type: ignore[assignment]

# ════════════════════════════════════════════════════════════════════════════
# Declarative base
# ════════════════════════════════════════════════════════════════════════════


class Base(DeclarativeBase):
    """Single MetaData container for all ProLine CAD tables."""


# Re-export so Alembic env.py can import a stable name regardless of refactors.
metadata = Base.metadata


# ════════════════════════════════════════════════════════════════════════════
# Baseline tables (matches 001_initial.sql)
# ════════════════════════════════════════════════════════════════════════════


class McpContext(Base):
    """MCP 调用上下文表 — 全链路追溯的脊椎。"""

    __tablename__ = "mcp_contexts"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    mcp_context_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    agent: Mapped[str] = mapped_column(String(50), nullable=False)
    agent_version: Mapped[str | None] = mapped_column(String(20), server_default=text("'v1.0'"))
    parent_context_id: Mapped[str | None] = mapped_column(
        String(100),
        ForeignKey("mcp_contexts.mcp_context_id"),
    )
    input_payload: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    output_payload: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    latency_ms: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    provenance: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default=text("'SUCCESS'"))
    error_message: Mapped[str | None] = mapped_column(Text)
    step_breakdown: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("NOW()")
    )
    schema_version: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("1"))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index(
            "idx_mcp_contexts_deleted_at",
            "deleted_at",
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )


class SiteModel(Base):
    """SiteModel 解析结果表 — 工厂图纸的结构化镜像。"""

    __tablename__ = "site_models"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()")
    )
    site_model_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    cad_source: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    assets: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    links: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    geometry_integrity_score: Mapped[float] = mapped_column(Numeric(5, 4), server_default=text("0.0"))
    statistics: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    mcp_context_id: Mapped[str | None] = mapped_column(
        String(100), ForeignKey("mcp_contexts.mcp_context_id")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("NOW()")
    )
    schema_version: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("1"))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    bbox: Mapped[object | None] = mapped_column(
        Geometry(geometry_type="POLYGON", srid=0, spatial_index=False)
        if Geometry else String  # type: ignore[arg-type]
    )

    __table_args__ = (
        Index(
            "idx_site_models_deleted_at",
            "deleted_at",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("idx_site_models_bbox", "bbox", postgresql_using="gist"),
    )


# ════════════════════════════════════════════════════════════════════════════
# Constraint domain — PG ENUM type references (created by migrations 0015..0020)
# ════════════════════════════════════════════════════════════════════════════
# `create_type=False` means SQLAlchemy will NOT issue CREATE TYPE — the types
# already exist in the database (created by Alembic revisions). We just bind the
# Python-side mapping. Mirrors `shared.models.Constraint*` enums one-to-one.

PG_CONSTRAINT_CLASS = PG_ENUM(
    "hard", "soft", "preference",
    name="constraint_class", create_type=False,
)
PG_CONSTRAINT_SEVERITY = PG_ENUM(
    "critical", "major", "minor",
    name="constraint_severity", create_type=False,
)
PG_CONSTRAINT_AUTHORITY = PG_ENUM(
    "statutory", "industry", "enterprise", "project", "heuristic", "preference",
    name="constraint_authority", create_type=False,
)
PG_CONSTRAINT_CONFORMANCE = PG_ENUM(
    "MUST", "SHOULD", "MAY",
    name="constraint_conformance", create_type=False,
)
PG_CONSTRAINT_CATEGORY = PG_ENUM(
    "SPATIAL", "SEQUENCE", "TORQUE", "SAFETY", "ENVIRONMENTAL",
    "REGULATORY", "QUALITY", "RESOURCE", "LOGISTICS", "OTHER",
    name="constraint_category", create_type=False,
)
PG_CONSTRAINT_REVIEW_STATUS = PG_ENUM(
    "draft", "under_review", "approved", "rejected", "superseded",
    name="constraint_review_status", create_type=False,
)
PG_CONSTRAINT_PARSE_METHOD = PG_ENUM(
    "MANUAL_UI", "EXCEL_IMPORT", "MBOM_IMPORT", "PMI_ENGINE", "LLM_INFERENCE",
    name="constraint_parse_method", create_type=False,
)
PG_CONSTRAINT_SET_STATUS = PG_ENUM(
    "draft", "active", "archived",
    name="constraint_set_status", create_type=False,
)


class ConstraintSet(Base):
    """约束集表（migration 0015 重构 / blueprint G0）。

    一个 site_model 可有多个 ConstraintSet（按版本/草稿/归档），但同一时间
    至多一个 ``status='active'`` —— 由部分唯一索引 ``uq_cset_active_per_site``
    保证。子约束行 (``process_constraints``) 通过 ``constraint_set_id`` FK
    挂在这里。
    """

    __tablename__ = "constraint_sets"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()")
    )
    constraint_set_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    version: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'v1.0'")
    )
    project_id: Mapped[str | None] = mapped_column(String(50))
    site_model_id: Mapped[str | None] = mapped_column(
        String(50), ForeignKey("site_models.site_model_id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(
        PG_CONSTRAINT_SET_STATUS,
        nullable=False,
        server_default=text("'draft'::constraint_set_status"),
    )
    description: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    meta: Mapped[dict] = mapped_column(
        "metadata", JSONB, server_default=text("'{}'::jsonb")
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_by: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("NOW()")
    )
    schema_version: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("2")
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    mcp_context_id: Mapped[str | None] = mapped_column(
        String(100), ForeignKey("mcp_contexts.mcp_context_id")
    )

    __table_args__ = (
        Index(
            "idx_cset_project",
            "project_id",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "idx_cset_site_status",
            "site_model_id", "status",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("idx_cset_tags", "tags", postgresql_using="gin"),
        Index(
            "uq_cset_active_per_site",
            "site_model_id",
            unique=True,
            postgresql_where=text(
                "status = 'active'::constraint_set_status AND deleted_at IS NULL"
            ),
        ),
    )


class LayoutCandidate(Base):
    """布局候选方案表 — LayoutAgent 输出。"""

    __tablename__ = "layout_candidates"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()")
    )
    site_model_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("site_models.site_model_id"), nullable=False
    )
    plan_id: Mapped[str] = mapped_column(String(10), nullable=False)
    score: Mapped[float] = mapped_column(Numeric(5, 4), server_default=text("0.0"))
    hard_pass: Mapped[bool] = mapped_column(Boolean, server_default=text("FALSE"))
    adjustments: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    reasoning: Mapped[str] = mapped_column(Text, server_default=text("''"))
    reasoning_chain: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    convergence_info: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    mcp_context_id: Mapped[str | None] = mapped_column(
        String(100), ForeignKey("mcp_contexts.mcp_context_id")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))
    schema_version: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("1"))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index(
            "idx_layout_candidates_deleted_at",
            "deleted_at",
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )


class AuditLog(Base):
    """审计记录表 — 决策签发归档。"""

    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()")
    )
    audit_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    decision: Mapped[str] = mapped_column(String(30), nullable=False)
    mcp_context_ids: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    approver: Mapped[str | None] = mapped_column(String(200))
    signature: Mapped[str | None] = mapped_column(Text)
    pdf_sha256: Mapped[str | None] = mapped_column(String(64))
    artifact_urls: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))
    schema_version: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("1"))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index(
            "idx_audit_logs_deleted_at",
            "deleted_at",
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )


class Workflow(Base):
    """工作流状态表 — Orchestrator 状态机。"""

    __tablename__ = "workflows"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()")
    )
    workflow_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    state: Mapped[str] = mapped_column(String(30), nullable=False, server_default=text("'PENDING'"))
    cad_filename: Mapped[str | None] = mapped_column(String(500))
    site_model_id: Mapped[str | None] = mapped_column(String(50))
    iteration: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    max_iterations: Mapped[int] = mapped_column(Integer, server_default=text("3"))
    context_chain: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))
    schema_version: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("1"))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    mcp_context_id: Mapped[str | None] = mapped_column(
        String(100), ForeignKey("mcp_contexts.mcp_context_id")
    )

    __table_args__ = (
        Index(
            "idx_workflows_deleted_at",
            "deleted_at",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("idx_workflows_mcp_context_id", "mcp_context_id"),
    )


# AssetType enum mirror -- must match shared.models.AssetType exactly.
# Drift is enforced by scripts/check_schema_drift.py (B4).
ASSET_TYPES: tuple[str, ...] = (
    "Equipment",
    "Conveyor",
    "LiftingPoint",
    "Zone",
    "Wall",
    "Door",
    "Pipe",
    "Column",
    "Window",
    "CncMachine",
    "ElectricalPanel",
    "StorageRack",
    "Annotation",
    "Other",
)
_ASSET_TYPE_CHECK = "asset_type IN (" + ",".join(f"'{v}'" for v in ASSET_TYPES) + ")"


class AssetGeometry(Base):
    """Per-asset geometry projection -- footprint + centroid + classifier metadata."""

    __tablename__ = "asset_geometries"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()")
    )
    site_model_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("site_models.site_model_id"), nullable=False
    )
    asset_guid: Mapped[str] = mapped_column(String(50), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(30), nullable=False)
    footprint: Mapped[object | None] = mapped_column(
        Geometry(geometry_type="POLYGON", srid=0, spatial_index=False)
        if Geometry else String  # type: ignore[arg-type]
    )
    centroid: Mapped[object | None] = mapped_column(
        Geometry(geometry_type="POINT", srid=0, spatial_index=False)
        if Geometry else String  # type: ignore[arg-type]
    )
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3))
    classifier_kind: Mapped[str | None] = mapped_column(String(40))
    schema_version: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("1"))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    mcp_context_id: Mapped[str | None] = mapped_column(
        String(100), ForeignKey("mcp_contexts.mcp_context_id")
    )

    __table_args__ = (
        UniqueConstraint("site_model_id", "asset_guid", name="uq_asset_geom_site_guid"),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_asset_geom_confidence_range",
        ),
        CheckConstraint(_ASSET_TYPE_CHECK, name="ck_asset_geom_asset_type_enum"),
        Index("idx_asset_geom_footprint", "footprint", postgresql_using="gist"),
        Index("idx_asset_geom_type", "asset_type"),
        Index(
            "idx_asset_geometries_deleted_at",
            "deleted_at",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("idx_asset_geometries_mcp_context_id", "mcp_context_id"),
    )


# ════════════════════════════════════════════════════════════════════════════
# Revision 0004: taxonomy_terms + quarantine_terms (RAG_TAXONOMY)
# ════════════════════════════════════════════════════════════════════════════


class TaxonomyTerm(Base):
    """Gold / promoted taxonomy master list. UI label = `term_display`."""

    __tablename__ = "taxonomy_terms"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()")
    )
    term_normalized: Mapped[str] = mapped_column(String(200), nullable=False)
    term_display: Mapped[str] = mapped_column(String(200), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(30), nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    evidence: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    schema_version: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("1"))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    mcp_context_id: Mapped[str | None] = mapped_column(
        String(100), ForeignKey("mcp_contexts.mcp_context_id")
    )

    __table_args__ = (
        CheckConstraint(_ASSET_TYPE_CHECK, name="ck_taxonomy_terms_asset_type_enum"),
        CheckConstraint(
            "source IN ('gold','llm_promoted','manual')",
            name="ck_taxonomy_terms_source_enum",
        ),
        Index(
            "uq_taxonomy_terms_term_type_alive",
            "term_normalized",
            "asset_type",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("idx_taxonomy_terms_asset_type", "asset_type"),
        Index(
            "idx_taxonomy_terms_deleted_at",
            "deleted_at",
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )


class QuarantineTerm(Base):
    """LLM-proposed terms awaiting human review."""

    __tablename__ = "quarantine_terms"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()")
    )
    term_normalized: Mapped[str] = mapped_column(String(200), nullable=False)
    term_display: Mapped[str] = mapped_column(String(200), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(30), nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    evidence: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decision: Mapped[str | None] = mapped_column(String(20))
    reviewer: Mapped[str | None] = mapped_column(String(200))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    merge_target_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("taxonomy_terms.id")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    schema_version: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("1"))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    mcp_context_id: Mapped[str | None] = mapped_column(
        String(100), ForeignKey("mcp_contexts.mcp_context_id")
    )

    __table_args__ = (
        CheckConstraint(_ASSET_TYPE_CHECK, name="ck_quarantine_terms_asset_type_enum"),
        CheckConstraint(
            "decision IS NULL OR decision IN ('pending','approve','reject','merge')",
            name="ck_quarantine_terms_decision_enum",
        ),
        CheckConstraint(
            "(decision = 'merge') = (merge_target_id IS NOT NULL)",
            name="ck_quarantine_terms_merge_target_consistency",
        ),
        Index(
            "uq_quarantine_terms_term_type_alive",
            "term_normalized",
            "asset_type",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("idx_quarantine_terms_decision", "decision"),
        Index("idx_quarantine_terms_asset_type", "asset_type"),
        Index(
            "idx_quarantine_terms_deleted_at",
            "deleted_at",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("idx_quarantine_terms_mcp_context_id", "mcp_context_id"),
    )


# ════════════════════════════════════════════════════════════════════════════
# Revision 0005: audit_log_actions (action-level audit trail)
# ════════════════════════════════════════════════════════════════════════════


class AuditLogAction(Base):
    """Append-only action audit -- distinct from decision-level AuditLog."""

    __tablename__ = "audit_log_actions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    actor: Mapped[str] = mapped_column(String(200), nullable=False)
    actor_role: Mapped[str] = mapped_column(String(20), nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    target_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_id: Mapped[str | None] = mapped_column(String(100))
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    mcp_context_id: Mapped[str | None] = mapped_column(
        String(100), ForeignKey("mcp_contexts.mcp_context_id")
    )
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    schema_version: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("1"))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "actor_role IN ('reviewer','admin','system','agent')",
            name="ck_audit_log_actions_actor_role_enum",
        ),
        Index("idx_audit_log_actions_ts", text("ts DESC")),
        Index("idx_audit_log_actions_actor_ts", "actor", text("ts DESC")),
        Index("idx_audit_log_actions_target", "target_type", "target_id"),
        Index("idx_audit_log_actions_mcp_context_id", "mcp_context_id"),
        Index(
            "idx_audit_log_actions_deleted_at",
            "deleted_at",
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )


class ProcessConstraint(Base):
    """Per-site_model 工艺约束行 (migrations 0014..0024).

    四种 ``kind`` 共享一行结构（payload 形状由 API 层 ``app/schemas/constraints.py``
    的 Pydantic 校验，不在 DDL 里强约束）：

    - ``predecessor`` ``{"from": asset_id, "to": asset_id}`` — DAG edge
    - ``resource``    ``{"asset_ids": [...], "resource": str, "capacity": int}``
    - ``takt``        ``{"asset_id": str, "min_s": float, "max_s": float}``
    - ``exclusion``   ``{"asset_ids": [...], "reason": str}``

    业务语义维度（migration 0015..0021 增量补齐）：

    - ``class``/``severity``/``authority``/``conformance`` — 硬软/严重度/权威/符合性
      （ADR-0006 / blueprint G3 §4.2）
    - ``category`` — 业务分类 (SAFETY/SEQUENCE/...)；与 ``kind`` 正交
    - ``review_status``/``parse_method``/``verified_*`` — 行级审核生命周期 (G2)
    - ``rationale``/``rule_expression``/``source_document_id``/``source_span``
      — 工程依据与可追溯证据
    - ``applicable_phases``/``valid_from``/``valid_to`` — 时空本体的时间维度
      (ADR-0009)
    """

    __tablename__ = "process_constraints"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()")
    )
    constraint_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    site_model_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("site_models.site_model_id", ondelete="CASCADE"),
        nullable=False,
    )
    constraint_set_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("constraint_sets.id", ondelete="CASCADE"),
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    priority: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("50")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("TRUE")
    )

    # ── migration 0015: hard/soft + severity + weight + provenance ──
    cls: Mapped[str] = mapped_column(
        "class",
        PG_CONSTRAINT_CLASS,
        nullable=False,
        server_default=text("'hard'::constraint_class"),
    )
    severity: Mapped[str] = mapped_column(
        PG_CONSTRAINT_SEVERITY,
        nullable=False,
        server_default=text("'major'::constraint_severity"),
    )
    weight: Mapped[float] = mapped_column(
        Numeric(4, 3), nullable=False, server_default=text("1.0")
    )
    rule_expression: Mapped[str | None] = mapped_column(Text)
    rationale: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Numeric(3, 2))
    source_document_id: Mapped[str | None] = mapped_column(String(100))
    source_span: Mapped[dict | None] = mapped_column(JSONB)
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )

    # ── migration 0016: authority / conformance / scope (evidence routing) ──
    authority: Mapped[str] = mapped_column(
        PG_CONSTRAINT_AUTHORITY,
        nullable=False,
        server_default=text("'heuristic'::constraint_authority"),
    )
    conformance: Mapped[str] = mapped_column(
        PG_CONSTRAINT_CONFORMANCE,
        nullable=False,
        server_default=text("'SHOULD'::constraint_conformance"),
    )
    scope: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )

    # ── migration 0019: business taxonomy (blueprint G1) ──
    category: Mapped[str] = mapped_column(
        PG_CONSTRAINT_CATEGORY,
        nullable=False,
        server_default=text("'OTHER'::constraint_category"),
    )

    # ── migration 0020: row-level review lifecycle (blueprint G2) ──
    review_status: Mapped[str] = mapped_column(
        PG_CONSTRAINT_REVIEW_STATUS,
        nullable=False,
        server_default=text("'draft'::constraint_review_status"),
    )
    parse_method: Mapped[str] = mapped_column(
        PG_CONSTRAINT_PARSE_METHOD,
        nullable=False,
        server_default=text("'MANUAL_UI'::constraint_parse_method"),
    )
    verified_by_user_id: Mapped[str | None] = mapped_column(String(100))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    needs_re_review: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("FALSE")
    )

    # ── migration 0024: temporal scope (ADR-0009) ──
    applicable_phases: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[\"DESIGN\",\"OPERATION\"]'::jsonb")
    )
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_by: Mapped[str | None] = mapped_column(String(100))
    mcp_context_id: Mapped[str | None] = mapped_column(
        String(100), ForeignKey("mcp_contexts.mcp_context_id")
    )
    schema_version: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("1")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "kind IN ('predecessor','resource','takt','exclusion')",
            name="ck_proc_constraints_kind",
        ),
        CheckConstraint(
            "jsonb_typeof(payload) = 'object'",
            name="ck_proc_constraints_payload_object",
        ),
        CheckConstraint(
            "priority >= 0 AND priority <= 100",
            name="ck_proc_constraints_priority_range",
        ),
        CheckConstraint(
            "weight >= 0 AND weight <= 1",
            name="ck_weight_range",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_confidence_range",
        ),
        CheckConstraint(
            "class <> 'hard'::constraint_class OR weight = 1.0",
            name="ck_hard_full_weight",
        ),
        CheckConstraint(
            "jsonb_typeof(scope) = 'object'",
            name="ck_scope_is_object",
        ),
        CheckConstraint(
            "review_status <> 'approved'::constraint_review_status"
            " OR (verified_by_user_id IS NOT NULL AND verified_at IS NOT NULL)",
            name="ck_pc_review_approved_verified",
        ),
        CheckConstraint(
            "valid_from IS NULL OR valid_to IS NULL OR valid_from < valid_to",
            name="ck_pc_valid_window",
        ),
        Index(
            "idx_proc_constraints_site_kind",
            "site_model_id", "kind",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "idx_proc_constraints_payload_gin",
            "payload",
            postgresql_using="gin",
        ),
        Index(
            "idx_pc_set_class",
            "constraint_set_id", "class",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "idx_pc_set_severity",
            "constraint_set_id", "severity",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "idx_pc_set_category",
            "constraint_set_id", "category",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "idx_pc_set_review",
            "constraint_set_id", "review_status",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "idx_pc_authority",
            "authority",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "idx_pc_needs_re_review",
            "constraint_set_id",
            postgresql_where=text("needs_re_review IS TRUE AND deleted_at IS NULL"),
        ),
        Index(
            "idx_pc_source_doc",
            "source_document_id",
            postgresql_where=text("source_document_id IS NOT NULL"),
        ),
        Index("idx_pc_tags", "tags", postgresql_using="gin"),
        Index("idx_pc_scope_gin", "scope", postgresql_using="gin"),
        Index(
            "idx_pc_applicable_phases_gin",
            "applicable_phases",
            postgresql_using="gin",
        ),
    )


class HierarchyNode(Base):
    """IEC 81346 / ISA-95 层级节点 (migration 0022 / ADR-0009).

    统一承载 Function/Product/Location 三视角下的 Enterprise..Equipment
    以及 Procedure / Document / AssetTypeTemplate 节点。``aspect`` 与
    ``node_kind`` 的合法组合由 INV-16 以 CHECK 约束在表层保护。
    """

    __tablename__ = "hierarchy_nodes"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()")
    )
    rds_code: Mapped[str] = mapped_column(String(64), nullable=False)
    aspect: Mapped[str] = mapped_column(String(16), nullable=False)
    node_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    parent_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("hierarchy_nodes.id", ondelete="RESTRICT")
    )
    asset_guid: Mapped[str | None] = mapped_column(String(50))
    process_step_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False))
    site_model_id: Mapped[str | None] = mapped_column(
        String(50), ForeignKey("site_models.site_model_id", ondelete="CASCADE")
    )
    name_zh: Mapped[str] = mapped_column(String(200), nullable=False)
    name_en: Mapped[str | None] = mapped_column(String(200))
    properties: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_by: Mapped[str | None] = mapped_column(String(100))
    mcp_context_id: Mapped[str | None] = mapped_column(
        String(100), ForeignKey("mcp_contexts.mcp_context_id")
    )
    schema_version: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("1")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "aspect IN ('FUNCTION','PRODUCT','LOCATION')",
            name="ck_hn_aspect_enum",
        ),
        CheckConstraint(
            "node_kind IN ('Enterprise','Site','Area','Line','WorkCenter','Station',"
            "'Equipment','Tool','Fixture','Material','AssetTypeTemplate',"
            "'Procedure','Document')",
            name="ck_hn_node_kind_enum",
        ),
        CheckConstraint(
            "jsonb_typeof(properties) = 'object'",
            name="ck_hn_properties_object",
        ),
        CheckConstraint(
            "parent_id IS NULL OR parent_id <> id",
            name="ck_hn_no_self_parent",
        ),
        CheckConstraint(
            "(aspect = 'FUNCTION' AND node_kind IN ('Procedure','Document'))"
            " OR (aspect = 'LOCATION' AND node_kind IN ('Enterprise','Site','Area','Line','WorkCenter','Station'))"
            " OR (aspect = 'PRODUCT'  AND node_kind IN ('Equipment','Tool','Fixture','Material','AssetTypeTemplate'))",
            name="ck_hn_aspect_kind_matrix",
        ),
        Index(
            "uq_hn_rds_code_live",
            "rds_code",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "idx_hn_parent",
            "parent_id",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "idx_hn_aspect_kind",
            "aspect",
            "node_kind",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "idx_hn_site_model",
            "site_model_id",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "idx_hn_asset_guid",
            "asset_guid",
            postgresql_where=text("asset_guid IS NOT NULL AND deleted_at IS NULL"),
        ),
        Index(
            "idx_hn_properties_gin",
            "properties",
            postgresql_using="gin",
        ),
    )


class ConstraintScope(Base):
    """Constraint ↔ HierarchyNode N:M 绑定 (migration 0023 / ADR-0009).

    携带绑定策略 S1–S4、允许后代继承、置信度与审核足迹。
    INV-17 由 CHECK ``ck_cscope_manual_verified`` 在表层保护。
    """

    __tablename__ = "constraint_scopes"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()")
    )
    constraint_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("process_constraints.id", ondelete="CASCADE"),
        nullable=False,
    )
    node_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("hierarchy_nodes.id", ondelete="RESTRICT"),
        nullable=False,
    )
    binding_strategy: Mapped[str] = mapped_column(String(20), nullable=False)
    inherit_to_descendants: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("FALSE")
    )
    confidence: Mapped[float] = mapped_column(
        Numeric(3, 2), nullable=False, server_default=text("1.00")
    )
    verified_by_user_id: Mapped[str | None] = mapped_column(String(100))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    binding_evidence: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_by: Mapped[str | None] = mapped_column(String(100))
    mcp_context_id: Mapped[str | None] = mapped_column(
        String(100), ForeignKey("mcp_contexts.mcp_context_id")
    )
    schema_version: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("1")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "binding_strategy IN ('explicit_id','asset_type','semantic','manual')",
            name="ck_cscope_strategy_enum",
        ),
        CheckConstraint(
            "confidence >= 0.00 AND confidence <= 1.00",
            name="ck_cscope_confidence_range",
        ),
        CheckConstraint(
            "jsonb_typeof(binding_evidence) = 'object'",
            name="ck_cscope_evidence_object",
        ),
        CheckConstraint(
            "binding_strategy <> 'manual'"
            " OR (verified_by_user_id IS NOT NULL AND verified_at IS NOT NULL)",
            name="ck_cscope_manual_verified",
        ),
        Index(
            "uq_cscope_constraint_node_live",
            "constraint_id",
            "node_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "idx_cscope_constraint",
            "constraint_id",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "idx_cscope_node",
            "node_id",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "idx_cscope_low_confidence",
            "confidence",
            postgresql_where=text("confidence < 0.80 AND deleted_at IS NULL"),
        ),
    )


class ConstraintExtraction(Base):
    """LLM/regex 抽取过程的原始 span 痕迹 (migration 0028 / ADR-0010).

    与 ``constraint_citations``（0016 已策展引用）分层：本表是"过程层"，
    一条约束可有 N 条原始抽取（多段共证）。LLM 抽取必带 ``llm_model`` +
    ``prompt_version``，保证可回放；``span_hash`` 防伪并支撑同约束 + 同 span
    的去重 (UNIQUE ``uq_ce_hash_per_constraint``)。
    """

    __tablename__ = "constraint_extractions"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()")
    )
    process_constraint_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("process_constraints.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_id: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_id: Mapped[str | None] = mapped_column(Text)
    page: Mapped[int | None] = mapped_column(Integer)
    char_start: Mapped[int | None] = mapped_column(Integer)
    char_end: Mapped[int | None] = mapped_column(Integer)
    span_text: Mapped[str] = mapped_column(Text, nullable=False)
    span_hash: Mapped[str] = mapped_column(Text, nullable=False)
    extractor_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    llm_model: Mapped[str | None] = mapped_column(String(60))
    prompt_version: Mapped[str | None] = mapped_column(String(40))
    extraction_run_id: Mapped[str | None] = mapped_column(Text)
    extraction_confidence: Mapped[float | None] = mapped_column(Numeric(3, 2))
    extraction_payload: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    extracted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    mcp_context_id: Mapped[str | None] = mapped_column(
        String(100), ForeignKey("mcp_contexts.mcp_context_id")
    )
    schema_version: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("1")
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "extractor_kind IN ('llm','regex','manual_ui','imported')",
            name="ck_ce_extractor_kind",
        ),
        CheckConstraint(
            "length(span_text) BETWEEN 1 AND 1000",
            name="ck_ce_span_text_len",
        ),
        CheckConstraint(
            "span_hash ~ '^[0-9a-f]{64}$'",
            name="ck_ce_span_hash_format",
        ),
        CheckConstraint("page IS NULL OR page >= 0", name="ck_ce_page_nonneg"),
        CheckConstraint(
            "char_start IS NULL OR char_start >= 0", name="ck_ce_char_range"
        ),
        CheckConstraint(
            "char_end IS NULL OR char_start IS NULL OR char_end > char_start",
            name="ck_ce_char_end_after_start",
        ),
        CheckConstraint(
            "extraction_confidence IS NULL"
            " OR (extraction_confidence >= 0 AND extraction_confidence <= 1)",
            name="ck_ce_confidence_range",
        ),
        CheckConstraint(
            "jsonb_typeof(extraction_payload) = 'object'",
            name="ck_ce_payload_object",
        ),
        CheckConstraint(
            "extractor_kind <> 'llm'"
            " OR (llm_model IS NOT NULL AND prompt_version IS NOT NULL)",
            name="ck_ce_llm_metadata",
        ),
        Index(
            "idx_ce_constraint",
            "process_constraint_id",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "idx_ce_document",
            "document_id",
            "page",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "idx_ce_run",
            "extraction_run_id",
            postgresql_where=text(
                "extraction_run_id IS NOT NULL AND deleted_at IS NULL"
            ),
        ),
        Index(
            "uq_ce_hash_per_constraint",
            "process_constraint_id",
            "span_hash",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )


__all__ = [
    "Base",
    "metadata",
    "McpContext",
    "SiteModel",
    "ConstraintSet",
    "LayoutCandidate",
    "AuditLog",
    "Workflow",
    "AssetGeometry",
    "TaxonomyTerm",
    "QuarantineTerm",
    "AuditLogAction",
    "ProcessConstraint",
    "HierarchyNode",
    "ConstraintScope",
    "ConstraintExtraction",
    "ASSET_TYPES",
]
