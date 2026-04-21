"""0004 taxonomy_terms + quarantine_terms tables.

Revision ID: 0004_taxonomy_quarantine
Revises: 0003_timescale_mcp
Create Date: 2026-04-20

ExcPlan plan r2 §3.4.2 / RAG_TAXONOMY: persist the gold/promoted taxonomy and
the LLM-proposed quarantine queue inside Postgres so review tooling and the
ParseAgent classifier can share a single source of truth.

Design notes:
- Both tables enforce `asset_type` against the AssetType enum via a CHECK
  identical to the one in 0002 (single source = `_ASSET_TYPES` tuple).
- `term_normalized` is the NFKC-casefold-stripped form used for de-dup; UI
  layers display `term_display`. Soft-deletion respected via partial UNIQUE.
- `quarantine_terms.decision` is NULL until reviewed; allowed values then are
  pending / approve / reject / merge. `merge_target_id` only set when
  decision='merge'.
- One-way FK only: quarantine.merge_target -> taxonomy. The reverse link
  (taxonomy.promoted_from_quarantine) is captured in the `evidence` JSONB to
  avoid a circular FK that complicates the migration.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_taxonomy_quarantine"
down_revision: str | None = "0003_timescale_mcp"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Mirror of shared.models.AssetType / shared.db_schemas.ASSET_TYPES.
_ASSET_TYPES: tuple[str, ...] = (
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


def _asset_type_check_clause() -> str:
    quoted = ",".join(f"'{v}'" for v in _ASSET_TYPES)
    return f"asset_type IN ({quoted})"


def upgrade() -> None:
    # ── taxonomy_terms (gold / promoted master list) ──
    op.create_table(
        "taxonomy_terms",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("term_normalized", sa.String(200), nullable=False),
        sa.Column("term_display", sa.String(200), nullable=False),
        sa.Column("asset_type", sa.String(30), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column(
            "evidence",
            sa.dialects.postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("schema_version", sa.SmallInteger, nullable=False, server_default=sa.text("1")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "mcp_context_id",
            sa.String(100),
            sa.ForeignKey("mcp_contexts.mcp_context_id"),
            nullable=True,
        ),
        sa.CheckConstraint(_asset_type_check_clause(), name="ck_taxonomy_terms_asset_type_enum"),
        sa.CheckConstraint(
            "source IN ('gold','llm_promoted','manual')",
            name="ck_taxonomy_terms_source_enum",
        ),
    )
    # Soft-delete-aware uniqueness: a term may be re-created after a reject.
    op.create_index(
        "uq_taxonomy_terms_term_type_alive",
        "taxonomy_terms",
        ["term_normalized", "asset_type"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index("idx_taxonomy_terms_asset_type", "taxonomy_terms", ["asset_type"])
    op.create_index(
        "idx_taxonomy_terms_deleted_at",
        "taxonomy_terms",
        ["deleted_at"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # ── quarantine_terms (LLM-proposed, awaiting human review) ──
    op.create_table(
        "quarantine_terms",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("term_normalized", sa.String(200), nullable=False),
        sa.Column("term_display", sa.String(200), nullable=False),
        sa.Column("asset_type", sa.String(30), nullable=False),
        sa.Column("count", sa.Integer, nullable=False, server_default=sa.text("1")),
        sa.Column(
            "evidence",
            sa.dialects.postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decision", sa.String(20), nullable=True),
        sa.Column("reviewer", sa.String(200), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "merge_target_id",
            sa.dialects.postgresql.UUID(as_uuid=False),
            sa.ForeignKey("taxonomy_terms.id"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("schema_version", sa.SmallInteger, nullable=False, server_default=sa.text("1")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "mcp_context_id",
            sa.String(100),
            sa.ForeignKey("mcp_contexts.mcp_context_id"),
            nullable=True,
        ),
        sa.CheckConstraint(_asset_type_check_clause(), name="ck_quarantine_terms_asset_type_enum"),
        sa.CheckConstraint(
            "decision IS NULL OR decision IN ('pending','approve','reject','merge')",
            name="ck_quarantine_terms_decision_enum",
        ),
        sa.CheckConstraint(
            "(decision = 'merge') = (merge_target_id IS NOT NULL)",
            name="ck_quarantine_terms_merge_target_consistency",
        ),
    )
    op.create_index(
        "uq_quarantine_terms_term_type_alive",
        "quarantine_terms",
        ["term_normalized", "asset_type"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index("idx_quarantine_terms_decision", "quarantine_terms", ["decision"])
    op.create_index("idx_quarantine_terms_asset_type", "quarantine_terms", ["asset_type"])
    op.create_index(
        "idx_quarantine_terms_deleted_at",
        "quarantine_terms",
        ["deleted_at"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "idx_quarantine_terms_mcp_context_id", "quarantine_terms", ["mcp_context_id"]
    )


def downgrade() -> None:
    op.drop_index("idx_quarantine_terms_mcp_context_id", table_name="quarantine_terms")
    op.drop_index("idx_quarantine_terms_deleted_at", table_name="quarantine_terms")
    op.drop_index("idx_quarantine_terms_asset_type", table_name="quarantine_terms")
    op.drop_index("idx_quarantine_terms_decision", table_name="quarantine_terms")
    op.drop_index("uq_quarantine_terms_term_type_alive", table_name="quarantine_terms")
    op.drop_table("quarantine_terms")

    op.drop_index("idx_taxonomy_terms_deleted_at", table_name="taxonomy_terms")
    op.drop_index("idx_taxonomy_terms_asset_type", table_name="taxonomy_terms")
    op.drop_index("uq_taxonomy_terms_term_type_alive", table_name="taxonomy_terms")
    op.drop_table("taxonomy_terms")
