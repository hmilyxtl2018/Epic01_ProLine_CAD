"""0014 process_constraints: per-site_model 工艺约束表 (Phase 2.2).

Revision ID: 0014_process_constraints
Revises: 0013_asset_catalog
Create Date: 2026-04-22

Why
---
Phase 2 of `docs/ROADMAP_3D_SIM.md`. Layout solver / DES need a place
to store the four classes of process constraints that come from
S2-ConstraintAgent or human-in-the-loop editing:

- `predecessor`  A must finish before B (DAG edges)
- `resource`     Two assets share a finite resource (worker, fixture)
- `takt`         Cycle-time bounds for an asset / line segment
- `exclusion`    A and B must never run simultaneously (safety)

Schema notes
------------
- FK on `site_model_id` references the **business key** column
  (`site_models.site_model_id`, varchar) — not the surrogate UUID PK —
  to stay consistent with `asset_geometries` and friends.
- `payload` is JSONB and pinned to `jsonb_typeof = 'object'`. Per-kind
  shape is validated at the API layer (`app/schemas/constraints.py`).
- `priority` 0-100 (smallint): scheduler picks higher priority first
  when conflicts exist.
- `is_active` boolean: supports temporary disable without losing
  history (e.g. operator toggles a SOFT constraint during what-if).
- Common operational columns: `mcp_context_id`, `schema_version`,
  `deleted_at` — same convention as the other tables.

Operational notes
-----------------
- Idempotent: `CREATE TABLE IF NOT EXISTS` + named CHECK / UNIQUE.
- Downgrade drops the table.
"""

from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision = "0014_process_constraints"
down_revision = "0013_asset_catalog"
branch_labels = None
depends_on = None


_KINDS = ("predecessor", "resource", "takt", "exclusion")


def upgrade() -> None:
    kinds_sql = ",".join(f"'{k}'" for k in _KINDS)

    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS process_constraints (
            id              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
            constraint_id   VARCHAR(64)  NOT NULL UNIQUE,
            site_model_id   VARCHAR(50)  NOT NULL
                                REFERENCES site_models(site_model_id)
                                ON DELETE CASCADE,
            kind            VARCHAR(20)  NOT NULL,
            payload         JSONB        NOT NULL,
            priority        SMALLINT     NOT NULL DEFAULT 50,
            is_active       BOOLEAN      NOT NULL DEFAULT TRUE,
            created_by      VARCHAR(100),
            mcp_context_id  VARCHAR(100)
                                REFERENCES mcp_contexts(mcp_context_id),
            schema_version  SMALLINT     NOT NULL DEFAULT 1,
            created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
            deleted_at      TIMESTAMPTZ,
            CONSTRAINT ck_proc_constraints_kind
                CHECK (kind IN ({kinds_sql})),
            CONSTRAINT ck_proc_constraints_payload_object
                CHECK (jsonb_typeof(payload) = 'object'),
            CONSTRAINT ck_proc_constraints_priority_range
                CHECK (priority >= 0 AND priority <= 100)
        );
        """
    )

    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_proc_constraints_site_kind "
        "ON process_constraints (site_model_id, kind) WHERE deleted_at IS NULL;"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_proc_constraints_payload_gin "
        "ON process_constraints USING gin (payload);"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS process_constraints;")
