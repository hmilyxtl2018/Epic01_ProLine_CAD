"""0021 constraint_sources hash + classification.

Revision ID: 0021_constraint_source_hash
Revises: 0020_constraint_review_status
Create Date: 2026-05-06

Why
---
Per [docs/constraint_subsystem_data_model.md](
../../../docs/constraint_subsystem_data_model.md) §5 Gap G4, the
multipart upload flow (M1) requires:

1. ``hash_sha256`` for content-addressed dedup. A second upload of the
   exact same PDF / Excel must return ``409 Conflict`` instead of
   silently creating a near-duplicate ``constraint_sources`` row that
   would split downstream citations.
2. ``classification`` so the LLM-routing decorator
   ``@require_local_llm_when_classified`` (PRD-2 §6.2) can refuse to
   send ``CONFIDENTIAL`` / ``SECRET`` content to public LLM endpoints.

Both columns are nullable on existing rows because the corpus already
contains hand-curated ``constraint_sources`` entries that pre-date this
flow; we cannot retroactively know their hash. The dedup invariant is
expressed via a *partial* unique index that only fires for non-NULL,
non-soft-deleted rows.

Changes
-------
1. ``constraint_sources`` adds:

   - ``hash_sha256``    ``CHAR(64)`` NULL  -- lowercase hex, 32-byte digest
   - ``classification`` ``VARCHAR(20)`` NULL -- PUBLIC / INTERNAL / CONFIDENTIAL / SECRET

2. CHECK ``ck_cs_hash_format``: when ``hash_sha256`` is non-NULL it
   must be 64 lowercase hex chars.

3. CHECK ``ck_cs_classification_enum``: when ``classification`` is
   non-NULL it must be one of the four values. We use a CHECK rather
   than a PG ENUM because the value set is a *security* decision that
   may grow (e.g. ``EXPORT_CONTROLLED``) and we do not want to gate
   that on a destructive ``ALTER TYPE`` migration.

4. Partial unique index ``uq_cs_hash_live`` on ``(hash_sha256)`` for
   ``hash_sha256 IS NOT NULL AND deleted_at IS NULL``.

5. Optional supporting index ``idx_cs_classification`` for the
   "list classified sources" admin view.

Downgrade
---------
Drops indexes, constraints, then columns. Idempotent.
"""

from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision = "0021_constraint_source_hash"
down_revision = "0020_constraint_review_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ──────────────────────── 1. add columns ────────────────────────
    op.execute(
        """
        ALTER TABLE constraint_sources
            ADD COLUMN IF NOT EXISTS hash_sha256    CHAR(64),
            ADD COLUMN IF NOT EXISTS classification VARCHAR(20);
        """
    )

    # ──────────────────── 2. format / enum CHECKs ────────────────────
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'ck_cs_hash_format'
            ) THEN
                ALTER TABLE constraint_sources
                    ADD CONSTRAINT ck_cs_hash_format CHECK (
                        hash_sha256 IS NULL
                     OR hash_sha256 ~ '^[0-9a-f]{64}$'
                    );
            END IF;

            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'ck_cs_classification_enum'
            ) THEN
                ALTER TABLE constraint_sources
                    ADD CONSTRAINT ck_cs_classification_enum CHECK (
                        classification IS NULL
                     OR classification IN
                        ('PUBLIC','INTERNAL','CONFIDENTIAL','SECRET')
                    );
            END IF;
        END
        $$;
        """
    )

    # ──────────────── 3. partial unique index for dedup ────────────────
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_cs_hash_live
            ON constraint_sources (hash_sha256)
            WHERE hash_sha256 IS NOT NULL AND deleted_at IS NULL;

        CREATE INDEX IF NOT EXISTS idx_cs_classification
            ON constraint_sources (classification)
            WHERE classification IS NOT NULL AND deleted_at IS NULL;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP INDEX IF EXISTS idx_cs_classification;
        DROP INDEX IF EXISTS uq_cs_hash_live;

        ALTER TABLE constraint_sources
            DROP CONSTRAINT IF EXISTS ck_cs_classification_enum,
            DROP CONSTRAINT IF EXISTS ck_cs_hash_format;

        ALTER TABLE constraint_sources
            DROP COLUMN IF EXISTS classification,
            DROP COLUMN IF EXISTS hash_sha256;
        """
    )
