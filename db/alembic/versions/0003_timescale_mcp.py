"""0003 TimescaleDB hypertable + retention on mcp_contexts.

Revision ID: 0003_timescale_mcp
Revises: 0002_postgis_spatial
Create Date: 2026-04-20

ExcPlan plan r2 §3.2 + §3.4.2: turn mcp_contexts into a 7-day-chunk hypertable
with 30-day retention. Hot tier only -- cold (>30d) export is handled by
scripts/export_cold_mcp_to_parquet.py (Phase 5).

Notes:
- create_hypertable requires that the time column (`timestamp`) is part of any
  existing UNIQUE/PRIMARY KEY constraint. The baseline PK is `id` (UUID); we
  use `migrate_data => true` to copy existing rows into chunks.
- Re-running on an already-hypertabled table is a no-op thanks to
  `if_not_exists => true`.
- This revision has NO ORM mapping change: hypertables remain ordinary tables
  to SQLAlchemy. The behaviour lives entirely in extension metadata.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003_timescale_mcp"
down_revision: str | None = "0002_postgis_spatial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")
    op.execute(
        """
        SELECT create_hypertable(
            'mcp_contexts',
            'timestamp',
            chunk_time_interval => INTERVAL '7 days',
            if_not_exists => TRUE,
            migrate_data => TRUE
        )
        """
    )
    op.execute(
        """
        SELECT add_retention_policy(
            'mcp_contexts',
            INTERVAL '30 days',
            if_not_exists => TRUE
        )
        """
    )


def downgrade() -> None:
    # Best-effort: remove the retention policy. The hypertable itself cannot be
    # cleanly demoted back to a regular table without rewriting all chunks; we
    # leave it in place so the downgrade is reversible without data loss.
    # Guard against environments where the timescaledb extension was never
    # installed (e.g. PostGIS-only lite verification).
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
                PERFORM remove_retention_policy('mcp_contexts', if_exists => TRUE);
            END IF;
        END
        $$
        """
    )
