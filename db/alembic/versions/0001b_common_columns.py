"""0001b add common columns: schema_version, deleted_at, mcp_context_id.

Revision ID: 0001b_common_columns
Revises: 0001_baseline
Create Date: 2026-04-20

CLAUDE.md / ExcPlan plan r2 §3.4.1.2: every business table carries
- schema_version SMALLINT NOT NULL DEFAULT 1
- deleted_at     TIMESTAMPTZ
- mcp_context_id VARCHAR(100) FK -> mcp_contexts(mcp_context_id)

Notes:
- mcp_contexts is the lineage spine; it gets schema_version + deleted_at but
  not a self-referencing mcp_context_id (parent_context_id already serves that).
- audit_logs already has mcp_context_ids JSONB (multi-context decision); we
  skip the singular FK here to avoid redundant data.
- CHECK constraints (confidence_range, asset_type_enum) are introduced in 0002
  / 0004 alongside the columns they target; this revision is column-only.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001b_common_columns"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Tables that receive all three columns (have natural mcp_context_id link).
_TABLES_WITH_FK: tuple[str, ...] = (
    "constraint_sets",
    "workflows",
)
# Tables that already declare mcp_context_id; receive only schema_version + deleted_at.
_TABLES_VERSION_ONLY: tuple[str, ...] = (
    "mcp_contexts",
    "site_models",
    "layout_candidates",
    "audit_logs",
)


def upgrade() -> None:
    for table in _TABLES_VERSION_ONLY + _TABLES_WITH_FK:
        op.add_column(
            table,
            sa.Column(
                "schema_version",
                sa.SmallInteger(),
                nullable=False,
                server_default=sa.text("1"),
            ),
        )
        op.add_column(
            table,
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index(
            f"idx_{table}_deleted_at",
            table,
            ["deleted_at"],
            postgresql_where=sa.text("deleted_at IS NULL"),
        )

    for table in _TABLES_WITH_FK:
        op.add_column(
            table,
            sa.Column(
                "mcp_context_id",
                sa.String(100),
                sa.ForeignKey("mcp_contexts.mcp_context_id"),
                nullable=True,
            ),
        )
        op.create_index(f"idx_{table}_mcp_context_id", table, ["mcp_context_id"])


def downgrade() -> None:
    for table in _TABLES_WITH_FK:
        op.drop_index(f"idx_{table}_mcp_context_id", table_name=table)
        op.drop_column(table, "mcp_context_id")

    for table in _TABLES_VERSION_ONLY + _TABLES_WITH_FK:
        op.drop_index(f"idx_{table}_deleted_at", table_name=table)
        op.drop_column(table, "deleted_at")
        op.drop_column(table, "schema_version")
