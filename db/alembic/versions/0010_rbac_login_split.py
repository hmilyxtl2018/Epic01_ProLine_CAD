"""0010 RBAC -- parameterise login-role membership grants (Phase E2.1).

Revision ID: 0010_rbac_login_split
Revises: 0009_rls_policies
Create Date: 2026-04-21

Why this exists
---------------
Migration 0008 ends with::

    GRANT app_viewer, app_operator, app_reviewer, app_admin TO CURRENT_USER

In dev that is fine because the same login (`proline`) both runs alembic
*and* serves the application. In prod, alembic is invoked by a dedicated
DDL-privileged migrator account (e.g. `proline_migrator`), so 0008 grants
membership to the **migrator** rather than to the **runtime** login that
the FastAPI process actually connects as. Result: `SET LOCAL ROLE app_*`
inside the app raises ``permission denied to set role``.

This revision fixes that by granting membership to whatever login role
the operator names via ``DASHBOARD_APP_LOGIN_ROLE``. If the env var is
absent it falls back to ``proline`` so dev stays unchanged.

Operational notes (also see db/runbooks/rbac_rollout.md if/when written):

  * The login user must already exist; we do **not** CREATE ROLE here so
    we never have to manage a password from inside a migration.
  * Re-running is safe — ``GRANT ... TO <role>`` on already-granted
    membership is a no-op.
  * Downgrade revokes the parameterised grant only; it does not touch
    the ``CURRENT_USER`` grant 0008 already left in place.
"""

from __future__ import annotations

import os
import re
from collections.abc import Sequence

from alembic import op

revision: str = "0010_rbac_login_split"
down_revision: str | None = "0009_rls_policies"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_APP_ROLES = ("app_viewer", "app_operator", "app_reviewer", "app_admin")
_DEFAULT_LOGIN = "proline"
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")


def _resolve_login_role() -> str:
    raw = (os.environ.get("DASHBOARD_APP_LOGIN_ROLE") or _DEFAULT_LOGIN).strip()
    if not _IDENT_RE.match(raw):
        # Refuse to splice anything that isn't a plain identifier into raw SQL.
        raise RuntimeError(
            f"DASHBOARD_APP_LOGIN_ROLE={raw!r} is not a valid PostgreSQL "
            "identifier (letters, digits, underscore; must start with letter "
            "or underscore; <= 63 chars)."
        )
    return raw


def upgrade() -> None:
    login = _resolve_login_role()
    # Ensure the named login actually exists before we try to GRANT to it,
    # so prod operators get a clear error instead of a confusing one.
    op.execute(
        f"""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{login}') THEN
                RAISE EXCEPTION
                    'DASHBOARD_APP_LOGIN_ROLE=% does not exist; create the login (CREATE ROLE ... LOGIN PASSWORD ...) before running this migration.',
                    '{login}';
            END IF;
        END $$;
        """
    )
    op.execute(
        f"GRANT {', '.join(_APP_ROLES)} TO {login}"
    )


def downgrade() -> None:
    login = _resolve_login_role()
    op.execute(
        f"""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{login}') THEN
                EXECUTE 'REVOKE {', '.join(_APP_ROLES)} FROM {login}';
            END IF;
        END $$;
        """
    )
