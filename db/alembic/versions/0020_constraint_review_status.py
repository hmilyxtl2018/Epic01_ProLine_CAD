"""0020 constraint review status — row-level review lifecycle on process_constraints.

Revision ID: 0020_constraint_review_status
Revises: 0019_constraint_category
Create Date: 2026-05-06

Why
---
Per [docs/constraint_subsystem_data_model.md](
../../../docs/constraint_subsystem_data_model.md) §5 Gap G2, the PRD-2
"审核队列" tab needs a per-row review state, distinct from the
*set-level* ``constraint_sets.status`` (draft / active / archived) that
ADR-0005 already shipped.

Today the only knob is ``is_active``, which conflates "soft-deleted",
"under-review", and "approved-but-paused".  This migration adds the
five-state lifecycle plus the fields needed to answer "who approved
this and when, and was the source still on its current version?".

Changes
-------
1. New ENUM ``constraint_review_status`` (5 values).
2. New ENUM ``constraint_parse_method`` (5 values) tracking how the
   row was created — manual UI / Excel batch / MBOM import / PMI
   engine / LLM inference. Drives the audit trail required by
   ADR-0006 §8.1 Q1.
3. ``process_constraints`` adds:

   - ``review_status``        ``constraint_review_status`` NOT NULL DEFAULT 'approved'
     (existing rows are grandfathered as approved so publish gates
     keep working; new rows default to 'draft' at the API layer.)
   - ``parse_method``         ``constraint_parse_method`` NOT NULL DEFAULT 'MANUAL_UI'
   - ``verified_by_user_id``  VARCHAR(100)  NULL
   - ``verified_at``          TIMESTAMPTZ   NULL
   - ``needs_re_review``      BOOLEAN       NOT NULL DEFAULT FALSE
     (set by the constraint_source version-bump trigger in M2.)

4. CHECK ``ck_pc_review_approved_verified``: when
   ``review_status='approved'``, ``verified_by_user_id`` AND
   ``verified_at`` MUST be non-null. This is INV-8 from the blueprint.

5. Indexes:

   - ``idx_pc_set_review`` ``(constraint_set_id, review_status)`` —
     the workbench review-queue main filter.
   - ``idx_pc_needs_re_review`` partial index for the dashboard banner.

Backfill
--------
- ``review_status``        = ``'approved'`` for all existing rows
  (they were authored before the gate existed, treat as grandfathered)
- ``parse_method``         = ``'MANUAL_UI'``
- ``verified_by_user_id``  = COALESCE(``created_by``, ``'system_backfill'``)
- ``verified_at``          = ``created_at``

Backfill order is critical: NOT NULL CHECK is added AFTER the UPDATE
populates ``verified_*``, so the migration is single-transaction safe.

Downgrade
---------
Drops constraint, indexes, columns, then types. Idempotent.
"""

from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision = "0020_constraint_review_status"
down_revision = "0019_constraint_category"
branch_labels = None
depends_on = None


ENUM_REVIEW = "constraint_review_status"
ENUM_PARSE = "constraint_parse_method"


def upgrade() -> None:
    # ─────────────────────────── 1. ENUMs ───────────────────────────
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_type WHERE typname = '{ENUM_REVIEW}'
            ) THEN
                CREATE TYPE {ENUM_REVIEW} AS ENUM (
                    'draft',
                    'under_review',
                    'approved',
                    'rejected',
                    'superseded'
                );
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM pg_type WHERE typname = '{ENUM_PARSE}'
            ) THEN
                CREATE TYPE {ENUM_PARSE} AS ENUM (
                    'MANUAL_UI',
                    'EXCEL_IMPORT',
                    'MBOM_IMPORT',
                    'PMI_ENGINE',
                    'LLM_INFERENCE'
                );
            END IF;
        END
        $$;
        """
    )

    # ──────────────────── 2. add columns (nullable first) ────────────────────
    op.execute(
        f"""
        ALTER TABLE process_constraints
            ADD COLUMN IF NOT EXISTS review_status        {ENUM_REVIEW}
                                                            NOT NULL
                                                            DEFAULT 'approved',
            ADD COLUMN IF NOT EXISTS parse_method         {ENUM_PARSE}
                                                            NOT NULL
                                                            DEFAULT 'MANUAL_UI',
            ADD COLUMN IF NOT EXISTS verified_by_user_id  VARCHAR(100),
            ADD COLUMN IF NOT EXISTS verified_at          TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS needs_re_review      BOOLEAN
                                                            NOT NULL
                                                            DEFAULT FALSE;
        """
    )

    # ──────────────── 3. backfill verified_* on grandfathered rows ────────────────
    op.execute(
        """
        UPDATE process_constraints
           SET verified_by_user_id = COALESCE(verified_by_user_id,
                                              created_by,
                                              'system_backfill'),
               verified_at         = COALESCE(verified_at, created_at)
         WHERE review_status = 'approved'::constraint_review_status
           AND verified_at IS NULL;
        """
    )

    # ──────────────── 4. INV-8: approved => verified_* NOT NULL ────────────────
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'ck_pc_review_approved_verified'
            ) THEN
                ALTER TABLE process_constraints
                    ADD CONSTRAINT ck_pc_review_approved_verified CHECK (
                        review_status <> 'approved'
                     OR (verified_by_user_id IS NOT NULL
                         AND verified_at IS NOT NULL)
                    );
            END IF;
        END
        $$;
        """
    )

    # ─── 4b. switch column default to 'draft' so new rows opt-in for approval ───
    # Existing rows were backfilled in step 3; default is no longer needed
    # for grandfathering, and 'draft' is the safer per-API contract.
    op.execute(
        """
        ALTER TABLE process_constraints
            ALTER COLUMN review_status SET DEFAULT 'draft';
        """
    )

    # ──────────────────── 5. indexes for workbench filters ────────────────────
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_pc_set_review
            ON process_constraints (constraint_set_id, review_status)
            WHERE deleted_at IS NULL;

        CREATE INDEX IF NOT EXISTS idx_pc_needs_re_review
            ON process_constraints (constraint_set_id)
            WHERE needs_re_review IS TRUE AND deleted_at IS NULL;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP INDEX IF EXISTS idx_pc_needs_re_review;
        DROP INDEX IF EXISTS idx_pc_set_review;

        ALTER TABLE process_constraints
            DROP CONSTRAINT IF EXISTS ck_pc_review_approved_verified;

        ALTER TABLE process_constraints
            DROP COLUMN IF EXISTS needs_re_review,
            DROP COLUMN IF EXISTS verified_at,
            DROP COLUMN IF EXISTS verified_by_user_id,
            DROP COLUMN IF EXISTS parse_method,
            DROP COLUMN IF EXISTS review_status;
        """
    )
    op.execute(f"DROP TYPE IF EXISTS {ENUM_PARSE};")
    op.execute(f"DROP TYPE IF EXISTS {ENUM_REVIEW};")
