"""0007 widen audit_log_actions.actor_role enum to include viewer + operator.

Revision ID: 0007_actor_role_widen
Revises: 0006_pgvector_reserve
Create Date: 2026-04-30

Background:
    The audit_log_actions table was created in 0005 with a CHECK constraint
    that allowed `('reviewer','admin','system','agent')`. The application's
    RBAC model (`app.deps.ROLES`) actually has 4 user roles
    (`viewer`, `operator`, `reviewer`, `admin`) plus the synthetic `system`
    and `agent` actors emitted by background workers and migrations.

    M2 RLS work (Phase 🅔) requires every user-facing role to be a valid
    `actor_role` so audit rows can be written with the caller's true role.
    We widen the CHECK constraint here.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0007_actor_role_widen"
down_revision: str | None = "0006_pgvector_reserve"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_NEW_ROLES = "('viewer','operator','reviewer','admin','system','agent')"
_OLD_ROLES = "('reviewer','admin','system','agent')"


def upgrade() -> None:
    op.drop_constraint(
        "ck_audit_log_actions_actor_role_enum",
        "audit_log_actions",
        type_="check",
    )
    op.create_check_constraint(
        "ck_audit_log_actions_actor_role_enum",
        "audit_log_actions",
        f"actor_role IN {_NEW_ROLES}",
    )


def downgrade() -> None:
    # Defensive: rows with the new roles would violate the old constraint.
    # Coerce them to 'system' before re-narrowing.
    op.execute(
        "UPDATE audit_log_actions SET actor_role = 'system' "
        "WHERE actor_role IN ('viewer','operator')"
    )
    op.drop_constraint(
        "ck_audit_log_actions_actor_role_enum",
        "audit_log_actions",
        type_="check",
    )
    op.create_check_constraint(
        "ck_audit_log_actions_actor_role_enum",
        "audit_log_actions",
        f"actor_role IN {_OLD_ROLES}",
    )
