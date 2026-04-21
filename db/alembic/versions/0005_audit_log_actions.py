"""0005 audit_log_actions table -- action-level audit trail.

Revision ID: 0005_audit_log_actions
Revises: 0004_taxonomy_quarantine
Create Date: 2026-04-20

ExcPlan plan r2 §3.4.2: distinct from `audit_logs` (decision-level archive).
This table records every reviewer / admin / agent action so taxonomy promotions,
quarantine decisions and classifier overrides are forensically queryable.

Volume estimate: ~10x decision count -> BIGSERIAL PK.
Retention: AUD category = 7 years (enforced by maintenance job, not a Timescale
policy, because audit data is regulatory).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_audit_log_actions"
down_revision: str | None = "0004_taxonomy_quarantine"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_log_actions",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("actor", sa.String(200), nullable=False),
        sa.Column("actor_role", sa.String(20), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("target_type", sa.String(50), nullable=False),
        sa.Column("target_id", sa.String(100), nullable=True),
        sa.Column(
            "payload",
            sa.dialects.postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "mcp_context_id",
            sa.String(100),
            sa.ForeignKey("mcp_contexts.mcp_context_id"),
            nullable=True,
        ),
        sa.Column(
            "ts",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("schema_version", sa.SmallInteger, nullable=False, server_default=sa.text("1")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "actor_role IN ('reviewer','admin','system','agent')",
            name="ck_audit_log_actions_actor_role_enum",
        ),
    )
    op.create_index(
        "idx_audit_log_actions_ts", "audit_log_actions", [sa.text("ts DESC")]
    )
    op.create_index(
        "idx_audit_log_actions_actor_ts",
        "audit_log_actions",
        ["actor", sa.text("ts DESC")],
    )
    op.create_index(
        "idx_audit_log_actions_target",
        "audit_log_actions",
        ["target_type", "target_id"],
    )
    op.create_index(
        "idx_audit_log_actions_mcp_context_id", "audit_log_actions", ["mcp_context_id"]
    )
    op.create_index(
        "idx_audit_log_actions_deleted_at",
        "audit_log_actions",
        ["deleted_at"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_audit_log_actions_deleted_at", table_name="audit_log_actions")
    op.drop_index("idx_audit_log_actions_mcp_context_id", table_name="audit_log_actions")
    op.drop_index("idx_audit_log_actions_target", table_name="audit_log_actions")
    op.drop_index("idx_audit_log_actions_actor_ts", table_name="audit_log_actions")
    op.drop_index("idx_audit_log_actions_ts", table_name="audit_log_actions")
    op.drop_table("audit_log_actions")
