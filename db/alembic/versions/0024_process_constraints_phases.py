"""0024 process_constraints temporal scope — applicable_phases + valid_from/to (ADR-0009).

Revision ID: 0024_process_constraints_phases
Revises: 0023_constraint_scopes
Create Date: 2026-05-07

Why
---
Per [ADR-0009 §2.1](../../../docs/adr/0009-spacetime-constraint-ontology.md),
each constraint must declare *when* it applies. Without this dimension a
"梁高 ≥ 4.5m" design-time check fires noisily during operation, and
modification-only rules are indistinguishable from steady-state ones.

Changes
-------
1. ``process_constraints`` adds:

   - ``applicable_phases`` ``JSONB`` NOT NULL DEFAULT ``'["DESIGN","OPERATION"]'``
     A JSON array of ``LifecyclePhase`` strings. Backfill default is the
     two most common phases for grandfathered rows; together with the
     ``needs_re_review=TRUE`` flip in step 4 this forces author re-review.
   - ``valid_from`` / ``valid_to`` ``TIMESTAMPTZ`` NULL — wall-clock
     temporal bounds, optional. M1.5 only stores; queries land in M2.

2. CHECK ``ck_pc_applicable_phases_array``: JSON array, len ≥ 1, each
   element ∈ the 8-value enum. Enforced as a type-guard plus subquery so
   we can adopt new phases without ``ALTER TYPE``-style migrations.

3. CHECK ``ck_pc_valid_window``: when both bounds present,
   ``valid_from < valid_to``.

4. INV-14 backfill: existing rows get the default phases AND get
   ``needs_re_review = TRUE`` so the workbench banner surfaces them.

5. Index ``idx_pc_applicable_phases_gin`` on the JSONB column for
   "list constraints active in phase X" queries.

Downgrade
---------
Drops index, constraints, columns. Idempotent.
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0024_process_constraints_phases"
down_revision = "0023_constraint_scopes"
branch_labels = None
depends_on = None


_PHASES = (
    "CONCEPT",
    "DESIGN",
    "CONSTRUCTION",
    "COMMISSIONING",
    "OPERATION",
    "MODIFICATION",
    "MAINTENANCE",
    "DECOMMISSION",
)


def upgrade() -> None:
    # Whitelist as a JSONB array literal so CHECK can use the JSONB containment
    # operator ``<@`` (subset). Postgres forbids subqueries in CHECK
    # expressions (FeatureNotSupported), so we cannot use
    # ``NOT EXISTS (SELECT FROM jsonb_array_elements_text ...)`` here.
    phases_jsonb = '[' + ",".join(f'"{p}"' for p in _PHASES) + ']'

    # ──────────────────────── 1. add columns ────────────────────────
    op.execute(
        """
        ALTER TABLE process_constraints
            ADD COLUMN IF NOT EXISTS applicable_phases JSONB
                NOT NULL DEFAULT '["DESIGN","OPERATION"]'::jsonb,
            ADD COLUMN IF NOT EXISTS valid_from TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS valid_to   TIMESTAMPTZ;
        """
    )

    # ──────────────── 2. backfill flag for grandfathered rows ────────────────
    # Existing rows pre-date the temporal dimension; force re-review so the
    # author either confirms the default or supplies a more specific subset.
    op.execute(
        """
        UPDATE process_constraints
           SET needs_re_review = TRUE
         WHERE deleted_at IS NULL
           AND review_status = 'approved'::constraint_review_status;
        """
    )

    # ──────────────────────── 3. CHECKs ────────────────────────
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'ck_pc_applicable_phases_array'
            ) THEN
                ALTER TABLE process_constraints
                    ADD CONSTRAINT ck_pc_applicable_phases_array CHECK (
                        jsonb_typeof(applicable_phases) = 'array'
                    AND jsonb_array_length(applicable_phases) >= 1
                    AND applicable_phases <@ '{phases_jsonb}'::jsonb
                    );
            END IF;

            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'ck_pc_valid_window'
            ) THEN
                ALTER TABLE process_constraints
                    ADD CONSTRAINT ck_pc_valid_window CHECK (
                        valid_from IS NULL
                     OR valid_to   IS NULL
                     OR valid_from < valid_to
                    );
            END IF;
        END
        $$;
        """
    )

    # ──────────────────────── 4. supporting index ────────────────────────
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_pc_applicable_phases_gin
            ON process_constraints USING gin (applicable_phases);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP INDEX IF EXISTS idx_pc_applicable_phases_gin;

        ALTER TABLE process_constraints
            DROP CONSTRAINT IF EXISTS ck_pc_valid_window;

        ALTER TABLE process_constraints
            DROP CONSTRAINT IF EXISTS ck_pc_applicable_phases_array;

        ALTER TABLE process_constraints
            DROP COLUMN IF EXISTS valid_to,
            DROP COLUMN IF EXISTS valid_from,
            DROP COLUMN IF EXISTS applicable_phases;
        """
    )
