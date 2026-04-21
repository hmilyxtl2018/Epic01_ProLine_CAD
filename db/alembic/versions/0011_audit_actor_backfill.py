"""0011 audit_log_actions: backfill NULL actor before strict RLS (Phase E2.2).

Revision ID: 0011_audit_actor_backfill
Revises: 0010_rbac_login_split
Create Date: 2026-04-21

Why
---
Migration 0009 RLS policies on ``audit_log_actions`` filter rows by
``actor = current_setting('app.current_actor', true)``. Any pre-RLS rows
written before the policy went live may have ``actor IS NULL`` (when the
old code path forgot to set it). Such rows would become invisible to every
non-admin session after 0009 lands.

This migration is idempotent and safe on dev/staging where the column may
already be 100% non-NULL (the UPDATE simply touches 0 rows).

Behavior:
- Sets ``actor = 'system'`` for any row where ``actor IS NULL``.
- Reports the number of rows touched in the alembic log.
- Downgrade is a no-op (we cannot reliably reconstruct the original NULLs
  and there is no business reason to do so).
"""
from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0011_audit_actor_backfill"
down_revision = "0010_rbac_login_split"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent DO block: safe to run even if the table is absent
    # (e.g. the lite stack stamped past 0005).
    op.execute(
        """
        DO $$
        DECLARE
            touched integer := 0;
        BEGIN
            IF to_regclass('public.audit_log_actions') IS NULL THEN
                RAISE NOTICE '0011: audit_log_actions not present, skipping backfill';
                RETURN;
            END IF;

            UPDATE public.audit_log_actions
               SET actor = 'system'
             WHERE actor IS NULL;

            GET DIAGNOSTICS touched = ROW_COUNT;
            RAISE NOTICE '0011: backfilled % audit rows with actor=system', touched;
        END
        $$;
        """
    )


def downgrade() -> None:
    # Intentionally a no-op: we cannot distinguish backfilled rows from
    # legitimate actor='system' rows, and reverting would break RLS
    # visibility for any audit row written by background jobs.
    op.execute("SELECT 1 -- 0011 downgrade is a no-op")
