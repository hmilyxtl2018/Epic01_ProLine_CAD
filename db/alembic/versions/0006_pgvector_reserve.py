"""0006 reserve pgvector extension + asset_geometries.embedding column.

Revision ID: 0006_pgvector_reserve
Revises: 0005_audit_log_actions
Create Date: 2026-04-20

ExcPlan plan r2 §3.4.2 / ADR-004: reserve infrastructure for the future
embedding-driven retrieval feature without paying the index cost yet.

Scope:
- CREATE EXTENSION vector
- ALTER TABLE asset_geometries ADD COLUMN embedding vector(384) NULL
- NO ivfflat / hnsw index yet -- created when the column is actually populated
  (otherwise the empty index just slows writes).

Rollback: DROP COLUMN, DROP EXTENSION (safe because no other table uses it).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0006_pgvector_reserve"
down_revision: str | None = "0005_audit_log_actions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    # Cannot use op.add_column with vector type directly without the pgvector
    # SQLAlchemy adapter; raw DDL avoids that runtime dependency.
    op.execute("ALTER TABLE asset_geometries ADD COLUMN embedding vector(384) NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE asset_geometries DROP COLUMN IF EXISTS embedding")
    op.execute("DROP EXTENSION IF EXISTS vector")
