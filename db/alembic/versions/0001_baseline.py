"""baseline — represents pre-Alembic state captured by db/migrations/001_initial.sql.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-04-20

This revision is intentionally a no-op. Existing databases provisioned with the
legacy SQL must be marked at this revision via:

    alembic stamp 0001_baseline

Greenfield databases run `alembic upgrade head`, which executes this no-op then
proceeds to 0001b and beyond. The actual baseline DDL lives in
`db/migrations/001_initial.sql` and `shared/db_schemas.py`; both are kept in
lockstep so autogenerate produces no diff against a stamped database.

See `docs/adr/003_alembic_takeover.md`.
"""
from __future__ import annotations

from collections.abc import Sequence

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """No-op: baseline is provisioned by db/migrations/001_initial.sql."""


def downgrade() -> None:
    """No-op: cannot downgrade past baseline."""
