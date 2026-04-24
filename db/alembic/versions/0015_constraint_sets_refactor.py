"""0015 constraint_sets refactor → aggregate root + row-level membership.

Revision ID: 0015_constraint_sets_refactor
Revises: 0014_process_constraints
Create Date: 2026-04-24

Why
---
Per ADR-0005 (`docs/adr/0005-constraint-set-schema.md`), the legacy
`constraint_sets` table used two JSONB blobs (`hard_constraints` /
`soft_constraints`) and was decoupled from the 4-kind `process_constraints`
rows created in 0014. This made:

- Row-level querying impossible ("all hard takt constraints for site X")
- Versioning/publishing meaningless (no FK from members to set)
- The structural `kind` ∈ {predecessor, resource, takt, exclusion}
  vs. semantic `class` ∈ {hard, soft, preference} axes conflated

This migration:

1. Drops the two JSONB columns and adds aggregate-root fields:
   `project_id`, `site_model_id`, `status`, `description`, `tags`,
   `published_at`, `published_by`, `deleted_at`.
2. Enforces **at most one** `status='active'` set per site_model
   via a partial unique index.
3. Upgrades `process_constraints` with `constraint_set_id` FK + the
   orthogonal dimensions `class`, `severity`, plus `weight`,
   `rule_expression`, `rationale`, `confidence`, `source_document_id`,
   `source_span`, `tags`.
4. Adds invariant `hard ⇒ weight = 1.0` (ck_hard_full_weight).
5. Creates `process_graphs` materialized DAG cache (node/edge counts,
   cycle detection, longest-path) keyed 1:1 to a constraint_set.
6. Adds a `BEFORE` trigger that freezes member rows when the parent
   set has `published_at IS NOT NULL`.

Backfill is out of scope (see `scripts/backfill_0015.py` next PR).
This migration is **data-destructive** for the legacy
`hard_constraints / soft_constraints` JSONB columns — in P2.2 these
were placeholder arrays and no prod data depends on them. Any dev env
that populated them must export first.

Downgrade restores the two JSONB columns empty and drops all new
artifacts — citations (0016) depend on `process_graphs`/`constraint_sets`
FKs but that is a separate revision.
"""

from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision = "0015_constraint_sets_refactor"
down_revision = "0014_process_constraints"
branch_labels = None
depends_on = None


# ── ENUM names kept as module constants for easy reuse in 0016 ──
ENUM_CLASS = "constraint_class"
ENUM_SEVERITY = "constraint_severity"
ENUM_SET_STATUS = "constraint_set_status"


def upgrade() -> None:
    # ───────────────────────────── 1. ENUMs ─────────────────────────────
    # Idempotent via DO blocks — safe on re-runs after partial failure.
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = '{ENUM_CLASS}') THEN
                CREATE TYPE {ENUM_CLASS} AS ENUM ('hard','soft','preference');
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = '{ENUM_SEVERITY}') THEN
                CREATE TYPE {ENUM_SEVERITY} AS ENUM ('critical','major','minor');
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = '{ENUM_SET_STATUS}') THEN
                CREATE TYPE {ENUM_SET_STATUS} AS ENUM ('draft','active','archived');
            END IF;
        END
        $$;
        """
    )

    # ──────────────────── 2. constraint_sets aggregate root ────────────────────
    # The legacy table lives in db/migrations/001_initial.sql (initdb script),
    # so it exists before alembic runs. We augment with new columns, drop
    # legacy JSONB arrays, add status/lifecycle/ownership fields.
    op.execute(
        f"""
        ALTER TABLE constraint_sets
            ADD COLUMN IF NOT EXISTS project_id       VARCHAR(50),
            ADD COLUMN IF NOT EXISTS site_model_id    VARCHAR(50),
            ADD COLUMN IF NOT EXISTS status           {ENUM_SET_STATUS}
                                                        NOT NULL DEFAULT 'draft',
            ADD COLUMN IF NOT EXISTS description      TEXT,
            ADD COLUMN IF NOT EXISTS tags             TEXT[] NOT NULL DEFAULT '{{}}',
            ADD COLUMN IF NOT EXISTS published_at     TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS published_by     VARCHAR(100),
            ADD COLUMN IF NOT EXISTS deleted_at       TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS mcp_context_id   VARCHAR(100),
            ADD COLUMN IF NOT EXISTS schema_version   SMALLINT NOT NULL DEFAULT 2;
        """
    )

    # FK to site_models business key (consistent with 0014 / asset_geometries).
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'fk_cset_site_model'
            ) THEN
                ALTER TABLE constraint_sets
                    ADD CONSTRAINT fk_cset_site_model
                    FOREIGN KEY (site_model_id)
                    REFERENCES site_models(site_model_id)
                    ON DELETE SET NULL;
            END IF;
        END
        $$;
        """
    )

    # mcp_context FK (same pattern as process_constraints)
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'fk_cset_mcp_context'
            ) THEN
                ALTER TABLE constraint_sets
                    ADD CONSTRAINT fk_cset_mcp_context
                    FOREIGN KEY (mcp_context_id)
                    REFERENCES mcp_contexts(mcp_context_id);
            END IF;
        END
        $$;
        """
    )

    # Drop legacy JSONB arrays (data-destructive — ok per module header).
    op.execute(
        """
        ALTER TABLE constraint_sets
            DROP COLUMN IF EXISTS hard_constraints,
            DROP COLUMN IF EXISTS soft_constraints;
        """
    )

    # At most one active set per site_model (partial unique).
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_cset_active_per_site
            ON constraint_sets (site_model_id)
            WHERE status = 'active' AND deleted_at IS NULL;
        """
    )

    # Helpful lookup indexes.
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_cset_site_status
            ON constraint_sets (site_model_id, status)
            WHERE deleted_at IS NULL;
        CREATE INDEX IF NOT EXISTS idx_cset_project
            ON constraint_sets (project_id)
            WHERE deleted_at IS NULL;
        CREATE INDEX IF NOT EXISTS idx_cset_tags
            ON constraint_sets USING gin (tags);
        """
    )

    # ─────────────── 3. process_constraints upgrade to members ───────────────
    op.execute(
        f"""
        ALTER TABLE process_constraints
            ADD COLUMN IF NOT EXISTS constraint_set_id   UUID,
            ADD COLUMN IF NOT EXISTS class               {ENUM_CLASS}
                                                            NOT NULL DEFAULT 'hard',
            ADD COLUMN IF NOT EXISTS severity            {ENUM_SEVERITY}
                                                            NOT NULL DEFAULT 'major',
            ADD COLUMN IF NOT EXISTS weight              NUMERIC(4,3)
                                                            NOT NULL DEFAULT 1.0,
            ADD COLUMN IF NOT EXISTS rule_expression     TEXT,
            ADD COLUMN IF NOT EXISTS rationale           TEXT,
            ADD COLUMN IF NOT EXISTS confidence          NUMERIC(3,2),
            ADD COLUMN IF NOT EXISTS source_document_id  VARCHAR(100),
            ADD COLUMN IF NOT EXISTS source_span         JSONB,
            ADD COLUMN IF NOT EXISTS tags                TEXT[] NOT NULL DEFAULT '{{}}';
        """
    )

    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'fk_pc_constraint_set'
            ) THEN
                ALTER TABLE process_constraints
                    ADD CONSTRAINT fk_pc_constraint_set
                    FOREIGN KEY (constraint_set_id)
                    REFERENCES constraint_sets(id)
                    ON DELETE CASCADE;
            END IF;

            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'ck_hard_full_weight'
            ) THEN
                ALTER TABLE process_constraints
                    ADD CONSTRAINT ck_hard_full_weight
                    CHECK (class <> 'hard' OR weight = 1.0);
            END IF;

            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'ck_confidence_range'
            ) THEN
                ALTER TABLE process_constraints
                    ADD CONSTRAINT ck_confidence_range
                    CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1));
            END IF;

            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'ck_weight_range'
            ) THEN
                ALTER TABLE process_constraints
                    ADD CONSTRAINT ck_weight_range
                    CHECK (weight >= 0 AND weight <= 1);
            END IF;
        END
        $$;
        """
    )

    # Indexes for set/class/severity slicing.
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_pc_set_class
            ON process_constraints (constraint_set_id, class)
            WHERE deleted_at IS NULL;
        CREATE INDEX IF NOT EXISTS idx_pc_set_severity
            ON process_constraints (constraint_set_id, severity)
            WHERE deleted_at IS NULL;
        CREATE INDEX IF NOT EXISTS idx_pc_source_doc
            ON process_constraints (source_document_id)
            WHERE source_document_id IS NOT NULL;
        CREATE INDEX IF NOT EXISTS idx_pc_tags
            ON process_constraints USING gin (tags);
        """
    )

    # ────────────────── 4. process_graphs materialized cache ──────────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS process_graphs (
            id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            constraint_set_id  UUID NOT NULL UNIQUE
                                    REFERENCES constraint_sets(id) ON DELETE CASCADE,
            dag_hash           CHAR(64) NOT NULL,
            node_count         INTEGER  NOT NULL,
            edge_count         INTEGER  NOT NULL,
            has_cycle          BOOLEAN  NOT NULL,
            cycle_asset_ids    TEXT[]   NOT NULL DEFAULT '{}',
            longest_path_s     NUMERIC,
            computed_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT ck_pg_counts_nonneg CHECK (node_count >= 0 AND edge_count >= 0)
        );
        CREATE INDEX IF NOT EXISTS idx_pg_dag_hash ON process_graphs (dag_hash);
        """
    )

    # ─────────────── 5. publish-freeze trigger on process_constraints ───────────────
    op.execute(
        """
        CREATE OR REPLACE FUNCTION tg_freeze_published_set()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            target_cs UUID;
        BEGIN
            -- TG_OP-aware: NEW for INS/UPD, OLD for DEL.
            IF TG_OP = 'DELETE' THEN
                target_cs := OLD.constraint_set_id;
            ELSE
                target_cs := NEW.constraint_set_id;
            END IF;

            IF target_cs IS NULL THEN
                RETURN COALESCE(NEW, OLD);
            END IF;

            IF EXISTS (
                SELECT 1 FROM constraint_sets cs
                WHERE cs.id = target_cs
                  AND cs.published_at IS NOT NULL
                  AND cs.status = 'archived' IS NOT TRUE  -- allow changes after archive? NO.
            ) THEN
                RAISE EXCEPTION 'constraint_set % is published and immutable; clone to edit',
                    target_cs USING ERRCODE = 'check_violation';
            END IF;

            RETURN COALESCE(NEW, OLD);
        END
        $$;

        DROP TRIGGER IF EXISTS tg_pc_freeze ON process_constraints;
        CREATE TRIGGER tg_pc_freeze
            BEFORE INSERT OR UPDATE OR DELETE ON process_constraints
            FOR EACH ROW EXECUTE FUNCTION tg_freeze_published_set();
        """
    )

    # ─────────── 6. bump schema_version marker on process_constraints ───────────
    # 0014 left it at 1; with new columns we're on v2.
    op.execute(
        """
        UPDATE process_constraints
        SET schema_version = 2
        WHERE schema_version < 2;
        """
    )


def downgrade() -> None:
    # Reverse order. Triggers → cache → pc columns/constraints → cset columns → enums.

    op.execute(
        """
        DROP TRIGGER IF EXISTS tg_pc_freeze ON process_constraints;
        DROP FUNCTION IF EXISTS tg_freeze_published_set();
        DROP TABLE IF EXISTS process_graphs;
        """
    )

    op.execute(
        """
        ALTER TABLE process_constraints
            DROP CONSTRAINT IF EXISTS fk_pc_constraint_set,
            DROP CONSTRAINT IF EXISTS ck_hard_full_weight,
            DROP CONSTRAINT IF EXISTS ck_confidence_range,
            DROP CONSTRAINT IF EXISTS ck_weight_range;

        DROP INDEX IF EXISTS idx_pc_set_class;
        DROP INDEX IF EXISTS idx_pc_set_severity;
        DROP INDEX IF EXISTS idx_pc_source_doc;
        DROP INDEX IF EXISTS idx_pc_tags;

        ALTER TABLE process_constraints
            DROP COLUMN IF EXISTS constraint_set_id,
            DROP COLUMN IF EXISTS class,
            DROP COLUMN IF EXISTS severity,
            DROP COLUMN IF EXISTS weight,
            DROP COLUMN IF EXISTS rule_expression,
            DROP COLUMN IF EXISTS rationale,
            DROP COLUMN IF EXISTS confidence,
            DROP COLUMN IF EXISTS source_document_id,
            DROP COLUMN IF EXISTS source_span,
            DROP COLUMN IF EXISTS tags;
        """
    )

    op.execute(
        """
        DROP INDEX IF EXISTS uq_cset_active_per_site;
        DROP INDEX IF EXISTS idx_cset_site_status;
        DROP INDEX IF EXISTS idx_cset_project;
        DROP INDEX IF EXISTS idx_cset_tags;

        ALTER TABLE constraint_sets
            DROP CONSTRAINT IF EXISTS fk_cset_site_model,
            DROP CONSTRAINT IF EXISTS fk_cset_mcp_context;

        ALTER TABLE constraint_sets
            DROP COLUMN IF EXISTS project_id,
            DROP COLUMN IF EXISTS site_model_id,
            DROP COLUMN IF EXISTS status,
            DROP COLUMN IF EXISTS description,
            DROP COLUMN IF EXISTS tags,
            DROP COLUMN IF EXISTS published_at,
            DROP COLUMN IF EXISTS published_by,
            DROP COLUMN IF EXISTS deleted_at,
            DROP COLUMN IF EXISTS mcp_context_id,
            DROP COLUMN IF EXISTS schema_version;

        -- Restore legacy JSONB arrays (empty) for rollback compat.
        ALTER TABLE constraint_sets
            ADD COLUMN IF NOT EXISTS hard_constraints JSONB NOT NULL DEFAULT '[]',
            ADD COLUMN IF NOT EXISTS soft_constraints JSONB NOT NULL DEFAULT '[]';
        """
    )

    op.execute(
        f"""
        DROP TYPE IF EXISTS {ENUM_SET_STATUS};
        DROP TYPE IF EXISTS {ENUM_SEVERITY};
        DROP TYPE IF EXISTS {ENUM_CLASS};
        """
    )
