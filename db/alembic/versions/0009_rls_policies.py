"""0009 RLS policies on mcp_contexts + audit_log_actions (Phase E3).

Revision ID: 0009_rls_policies
Revises: 0008_rbac_pg_roles
Create Date: 2026-04-30

Threat model:
    M2 is single-tenant, so we are not yet partitioning by org. The remaining
    risks RLS guards against are:

    1. **Audit impersonation** -- an authenticated operator forges
       `audit_log_actions.actor` so a malicious action looks like it came
       from someone else. Mitigated by an INSERT WITH CHECK that pins
       `actor = current_setting('app.current_actor')`.

    2. **Audit leak across actors** -- a low-privilege caller reads another
       user's audit trail. Mitigated by a SELECT USING that lets non-admin
       roles see only rows where `actor` matches their session GUC. Admin
       has BYPASSRLS (set in 0008) so it sees everything.

    For mcp_contexts we keep policies permissive (all dashboard roles read
    everything) -- single-tenant means there is no row scope to enforce yet.
    Future tenant-scoping will add `WHERE org_id = current_setting('app.org_id')`.

How the GUC is set:
    `app.deps.get_db_with_role` runs `SET LOCAL "app.current_actor" = '<email>'`
    inside the request transaction. SET LOCAL is rolled back at COMMIT, so
    pooled connections do not leak identity across requests.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0009_rls_policies"
down_revision: str | None = "0008_rbac_pg_roles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── mcp_contexts ── permissive read for all dashboard roles ────────
    op.execute("ALTER TABLE mcp_contexts ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE mcp_contexts FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY mcp_contexts_read
            ON mcp_contexts
            FOR SELECT
            TO app_viewer, app_operator, app_reviewer
            USING (true)
        """
    )
    op.execute(
        """
        CREATE POLICY mcp_contexts_write
            ON mcp_contexts
            FOR ALL
            TO app_operator, app_reviewer
            USING (true)
            WITH CHECK (true)
        """
    )

    # ── audit_log_actions ── tight policies ────────────────────────────
    op.execute("ALTER TABLE audit_log_actions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE audit_log_actions FORCE ROW LEVEL SECURITY")

    # Read: only the authoring actor (admin BYPASSRLS sees all).
    op.execute(
        """
        CREATE POLICY audit_log_actions_read_own
            ON audit_log_actions
            FOR SELECT
            TO app_viewer, app_operator, app_reviewer
            USING (
                actor = current_setting('app.current_actor', true)
            )
        """
    )

    # Insert: forbid impersonation -- caller must match the GUC.
    op.execute(
        """
        CREATE POLICY audit_log_actions_insert_self
            ON audit_log_actions
            FOR INSERT
            TO app_operator, app_reviewer
            WITH CHECK (
                actor = current_setting('app.current_actor', true)
            )
        """
    )

    # No UPDATE / DELETE policy -- non-admins simply cannot modify audit rows.
    # admin (BYPASSRLS) keeps full control for forensic correction.


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS audit_log_actions_insert_self ON audit_log_actions")
    op.execute("DROP POLICY IF EXISTS audit_log_actions_read_own ON audit_log_actions")
    op.execute("ALTER TABLE audit_log_actions NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE audit_log_actions DISABLE ROW LEVEL SECURITY")

    op.execute("DROP POLICY IF EXISTS mcp_contexts_write ON mcp_contexts")
    op.execute("DROP POLICY IF EXISTS mcp_contexts_read ON mcp_contexts")
    op.execute("ALTER TABLE mcp_contexts NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE mcp_contexts DISABLE ROW LEVEL SECURITY")
