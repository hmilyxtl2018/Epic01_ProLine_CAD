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
from sqlalchemy.dialects.postgresql import JSONB, UUID
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


class ConstraintSet(Base):
    """约束集表 — ConstraintAgent 输出。"""

    __tablename__ = "constraint_sets"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()")
    )
    constraint_set_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    version: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'v1.0'"))
    hard_constraints: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    soft_constraints: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    meta: Mapped[dict] = mapped_column(
        "metadata", JSONB, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))
    schema_version: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("1"))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    mcp_context_id: Mapped[str | None] = mapped_column(
        String(100), ForeignKey("mcp_contexts.mcp_context_id")
    )

    __table_args__ = (
        Index(
            "idx_constraint_sets_deleted_at",
            "deleted_at",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("idx_constraint_sets_mcp_context_id", "mcp_context_id"),
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
    """Per-site_model 工艺约束 (Phase 2.2 / migration 0014).

    Four `kind`s share one row shape; per-kind payload schema lives in
    ``app/schemas/constraints.py`` and is validated at the API layer:

    - ``predecessor`` ``{"from": asset_id, "to": asset_id}`` — DAG edge
    - ``resource``    ``{"asset_ids": [...], "resource": str, "capacity": int}``
    - ``takt``        ``{"asset_id": str, "min_s": float, "max_s": float}``
    - ``exclusion``   ``{"asset_ids": [...], "reason": str}``
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
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    priority: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("50"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("TRUE"))
    created_by: Mapped[str | None] = mapped_column(String(100))
    mcp_context_id: Mapped[str | None] = mapped_column(
        String(100), ForeignKey("mcp_contexts.mcp_context_id")
    )
    schema_version: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("1"))
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
        Index(
            "idx_proc_constraints_site_kind",
            "site_model_id",
            "kind",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "idx_proc_constraints_payload_gin",
            "payload",
            postgresql_using="gin",
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
    "ASSET_TYPES",
]
