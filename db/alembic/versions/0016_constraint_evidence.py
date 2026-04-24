"""0016 constraint evidence — authority, conformance, scope, sources, citations.

Revision ID: 0016_constraint_evidence
Revises: 0015_constraint_sets_refactor
Create Date: 2026-04-24

Why
---
Per ADR-0006 (`docs/adr/0006-constraint-evidence-authority.md`), every
constraint must be able to answer: **"On what authority does it exist?
What clause? Within what scope?"** 0015 delivered the *container* and
*semantics* (class × severity); this migration delivers the
*epistemology* layer.

Changes
-------
1. ENUMs `constraint_authority` (6L) and `constraint_conformance` (3L).
2. `process_constraints`: `authority`, `conformance`, `scope`
   + CHECK `ck_authority_class_coherence` (R1/R2 from ADR-0006 §2.1).
3. `constraint_sources` — standards / SOPs / lessons as first-class
   managed resources (title, version, clause metadata, MinIO pointer).
4. `constraint_citations` — M:N link from a process_constraint row to
   ≥1 source clause, with `quote`, `confidence`, `derivation`, and
   `reviewed_at_version` (for ADR-0006 §8.1 Q3 upgrade notifications).
5. `constraint_source_version_events` — audit trail for version bumps.

Defaults on the 3 new `process_constraints` columns are chosen so that
existing rows satisfy `ck_authority_class_coherence` immediately:
`authority='heuristic'` with any `class` is allowed.

Downgrade removes everything added here; 0015 stays intact.
"""

from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision = "0016_constraint_evidence"
down_revision = "0015_constraint_sets_refactor"
branch_labels = None
depends_on = None


ENUM_AUTHORITY = "constraint_authority"
ENUM_CONFORMANCE = "constraint_conformance"


def upgrade() -> None:
    # ─────────────────────────── 1. ENUMs ───────────────────────────
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = '{ENUM_AUTHORITY}') THEN
                CREATE TYPE {ENUM_AUTHORITY} AS ENUM (
                    'statutory',    -- L0 法规 / 适航
                    'industry',     -- L1 行业强标 / 军标
                    'enterprise',   -- L2 企业 / OEM
                    'project',      -- L3 项目工艺
                    'heuristic',    -- L4 经验
                    'preference'    -- L5 偏好
                );
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = '{ENUM_CONFORMANCE}') THEN
                CREATE TYPE {ENUM_CONFORMANCE} AS ENUM ('MUST','SHOULD','MAY');
            END IF;
        END
        $$;
        """
    )

    # ──────────── 2. process_constraints evidence columns ────────────
    op.execute(
        f"""
        ALTER TABLE process_constraints
            ADD COLUMN IF NOT EXISTS authority    {ENUM_AUTHORITY}
                                                    NOT NULL DEFAULT 'heuristic',
            ADD COLUMN IF NOT EXISTS conformance  {ENUM_CONFORMANCE}
                                                    NOT NULL DEFAULT 'SHOULD',
            ADD COLUMN IF NOT EXISTS scope        JSONB
                                                    NOT NULL DEFAULT '{{}}'::jsonb;
        """
    )

    # R1: authority ∈ {statutory, industry}  → class MUST be 'hard'
    # R2: authority = 'preference'           → class != 'hard'
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'ck_authority_class_coherence'
            ) THEN
                ALTER TABLE process_constraints
                    ADD CONSTRAINT ck_authority_class_coherence CHECK (
                        (authority IN ('statutory','industry')     AND class = 'hard')
                     OR (authority = 'preference'                   AND class <> 'hard')
                     OR (authority IN ('enterprise','project','heuristic'))
                    );
            END IF;

            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'ck_scope_is_object'
            ) THEN
                ALTER TABLE process_constraints
                    ADD CONSTRAINT ck_scope_is_object
                    CHECK (jsonb_typeof(scope) = 'object');
            END IF;
        END
        $$;
        """
    )

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_pc_authority
            ON process_constraints (authority)
            WHERE deleted_at IS NULL;
        CREATE INDEX IF NOT EXISTS idx_pc_scope_gin
            ON process_constraints USING gin (scope);
        """
    )

    # ──────────────────── 3. constraint_sources ────────────────────
    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS constraint_sources (
            source_id       VARCHAR(80) PRIMARY KEY,
            title           TEXT NOT NULL,
            authority       {ENUM_AUTHORITY} NOT NULL,
            issuing_body    TEXT,
            version         VARCHAR(40),
            clause          VARCHAR(80),
            clause_text     TEXT,
            effective_from  DATE,
            expires_at      DATE,
            tags            TEXT[] NOT NULL DEFAULT '{{}}',
            url_or_ref      TEXT,
            doc_object_key  TEXT,              -- s3://constraint-corpus/... (ADR-0007)
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            deleted_at      TIMESTAMPTZ,
            CONSTRAINT ck_source_id_format CHECK (source_id ~ '^src_[a-z0-9_]+$'),
            CONSTRAINT ck_clause_text_len  CHECK (
                clause_text IS NULL OR length(clause_text) <= 2048
            ),
            CONSTRAINT ck_source_dates CHECK (
                expires_at IS NULL OR effective_from IS NULL
                OR expires_at >= effective_from
            )
        );
        CREATE INDEX IF NOT EXISTS idx_cs_authority
            ON constraint_sources (authority) WHERE deleted_at IS NULL;
        CREATE INDEX IF NOT EXISTS idx_cs_tags
            ON constraint_sources USING gin (tags);
        CREATE INDEX IF NOT EXISTS idx_cs_version
            ON constraint_sources (source_id, version);
        """
    )

    # ──────────────────── 4. constraint_citations ────────────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS constraint_citations (
            id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            process_constraint_id  UUID NOT NULL
                                        REFERENCES process_constraints(id)
                                        ON DELETE CASCADE,
            source_id              VARCHAR(80) NOT NULL
                                        REFERENCES constraint_sources(source_id),
            clause                 VARCHAR(80),
            quote                  TEXT,
            confidence             NUMERIC(3,2),
            derivation             TEXT,
            cited_by               VARCHAR(100),
            cited_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            -- ADR-0006 §8.1 Q3: version pinning for stale-dep detection.
            reviewed_at_version    VARCHAR(40),
            reviewed_by            VARCHAR(100),
            reviewed_at            TIMESTAMPTZ,
            CONSTRAINT uq_citation_triplet UNIQUE (
                process_constraint_id, source_id, clause
            ),
            CONSTRAINT ck_citation_confidence_range CHECK (
                confidence IS NULL OR (confidence >= 0 AND confidence <= 1)
            ),
            CONSTRAINT ck_citation_quote_len CHECK (
                quote IS NULL OR length(quote) <= 1000
            )
        );
        CREATE INDEX IF NOT EXISTS idx_cite_source
            ON constraint_citations (source_id);
        CREATE INDEX IF NOT EXISTS idx_cite_pc
            ON constraint_citations (process_constraint_id);
        -- For "show me all stale citations" dashboard query:
        CREATE INDEX IF NOT EXISTS idx_cite_unreviewed
            ON constraint_citations (source_id, reviewed_at_version)
            WHERE reviewed_at_version IS NOT NULL;
        """
    )

    # ────────────── 5. constraint_source_version_events ──────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS constraint_source_version_events (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            source_id     VARCHAR(80) NOT NULL
                              REFERENCES constraint_sources(source_id)
                              ON DELETE CASCADE,
            old_version   VARCHAR(40),
            new_version   VARCHAR(40) NOT NULL,
            changed_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            changed_by    VARCHAR(100),
            release_notes TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_csve_source
            ON constraint_source_version_events (source_id, changed_at DESC);
        """
    )

    # ───── 6. AFTER UPDATE trigger: auto-log version bumps ─────
    op.execute(
        """
        CREATE OR REPLACE FUNCTION tg_log_source_version_bump()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF NEW.version IS DISTINCT FROM OLD.version THEN
                INSERT INTO constraint_source_version_events
                    (source_id, old_version, new_version, changed_at, release_notes)
                VALUES
                    (NEW.source_id, OLD.version, NEW.version, NOW(),
                     'auto-logged by tg_log_source_version_bump');
            END IF;
            RETURN NEW;
        END
        $$;

        DROP TRIGGER IF EXISTS tg_cs_version_bump ON constraint_sources;
        CREATE TRIGGER tg_cs_version_bump
            AFTER UPDATE OF version ON constraint_sources
            FOR EACH ROW EXECUTE FUNCTION tg_log_source_version_bump();
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TRIGGER IF EXISTS tg_cs_version_bump ON constraint_sources;
        DROP FUNCTION IF EXISTS tg_log_source_version_bump();

        DROP TABLE IF EXISTS constraint_source_version_events;
        DROP TABLE IF EXISTS constraint_citations;
        DROP TABLE IF EXISTS constraint_sources;
        """
    )

    op.execute(
        """
        DROP INDEX IF EXISTS idx_pc_authority;
        DROP INDEX IF EXISTS idx_pc_scope_gin;

        ALTER TABLE process_constraints
            DROP CONSTRAINT IF EXISTS ck_authority_class_coherence,
            DROP CONSTRAINT IF EXISTS ck_scope_is_object;

        ALTER TABLE process_constraints
            DROP COLUMN IF EXISTS authority,
            DROP COLUMN IF EXISTS conformance,
            DROP COLUMN IF EXISTS scope;
        """
    )

    op.execute(
        f"""
        DROP TYPE IF EXISTS {ENUM_CONFORMANCE};
        DROP TYPE IF EXISTS {ENUM_AUTHORITY};
        """
    )
