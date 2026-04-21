"""0008 RBAC -- PostgreSQL roles + grants for SET LOCAL ROLE (Phase E2).

Revision ID: 0008_rbac_pg_roles
Revises: 0007_actor_role_widen
Create Date: 2026-04-30

Creates four NOLOGIN roles matching the application's RBAC:

    app_viewer     -- read everything (no writes anywhere)
    app_operator   -- viewer + INSERT/UPDATE on mcp_contexts + audit_log_actions
    app_reviewer   -- operator + UPDATE on quarantine_terms / taxonomy_terms
    app_admin      -- everything (BYPASSRLS so admin can audit raw tables)

The login user (whatever DSN connects as) is granted MEMBERSHIP of all four
roles so per-request `SET LOCAL ROLE app_<role>` works without a re-login.

Why per-session SET LOCAL ROLE instead of separate connection pools?
    A pool per role would multiply pool footprint by 4 and complicate
    transaction boundaries. SET LOCAL ROLE is scoped to the current
    transaction; combined with `BEGIN/COMMIT` per request (the SQLAlchemy
    session does this) it gives us correct RBAC + RLS scoping without
    pool segmentation.

Idempotency: each CREATE ROLE / GRANT is wrapped in a DO block so the
migration is safe to re-run on a partially-bootstrapped database.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0008_rbac_pg_roles"
down_revision: str | None = "0007_actor_role_widen"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_APP_ROLES = ("app_viewer", "app_operator", "app_reviewer", "app_admin")


def upgrade() -> None:
    # 1. Create the four NOLOGIN roles, idempotently.
    for role in _APP_ROLES:
        op.execute(
            f"""
            DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                    CREATE ROLE {role} NOLOGIN;
                END IF;
            END $$;
            """
        )

    # 2. Admin role bypasses RLS so admins can audit any tenant's data.
    op.execute("ALTER ROLE app_admin BYPASSRLS")

    # 3. Schema usage for all four.
    op.execute(
        f"GRANT USAGE ON SCHEMA public TO "
        f"{', '.join(_APP_ROLES)}"
    )

    # 4. Read everywhere (viewer is the floor; everyone inherits SELECT).
    op.execute(
        "GRANT SELECT ON ALL TABLES IN SCHEMA public TO "
        + ", ".join(_APP_ROLES)
    )
    op.execute(
        "GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO "
        + ", ".join(_APP_ROLES)
    )
    # Future tables / sequences default-grants.
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "GRANT SELECT ON TABLES TO " + ", ".join(_APP_ROLES)
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "GRANT SELECT ON SEQUENCES TO " + ", ".join(_APP_ROLES)
    )

    # 5. Operator: write the run/audit tables.
    op.execute(
        "GRANT INSERT, UPDATE ON mcp_contexts, audit_log_actions "
        "TO app_operator, app_reviewer, app_admin"
    )
    op.execute(
        "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public "
        "TO app_operator, app_reviewer, app_admin"
    )

    # 6. Reviewer: edit taxonomy + quarantine.
    op.execute(
        "GRANT INSERT, UPDATE, DELETE ON quarantine_terms, taxonomy_terms "
        "TO app_reviewer, app_admin"
    )

    # 7. Admin: catch-all writes (avoids whack-a-mole on future tables).
    op.execute(
        "GRANT INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_admin"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "GRANT INSERT, UPDATE, DELETE ON TABLES TO app_admin"
    )

    # 8. Grant MEMBERSHIP so the login user can SET ROLE app_*.
    op.execute(
        "GRANT " + ", ".join(_APP_ROLES) + " TO CURRENT_USER"
    )


def downgrade() -> None:
    # Revoke first, then drop. Reverse-order REVOKE keeps the dependency
    # graph consistent.
    op.execute(
        "REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM "
        + ", ".join(_APP_ROLES)
    )
    op.execute(
        "REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM "
        + ", ".join(_APP_ROLES)
    )
    op.execute(
        "REVOKE USAGE ON SCHEMA public FROM " + ", ".join(_APP_ROLES)
    )
    for role in _APP_ROLES:
        op.execute(
            f"""
            DO $$ BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                    DROP ROLE {role};
                END IF;
            END $$;
            """
        )
