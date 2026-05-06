"""0019 constraint_category — business taxonomy column on process_constraints.

Revision ID: 0019_constraint_category
Revises: 0018_run_evaluations
Create Date: 2026-05-06

Why
---
Per [docs/constraint_subsystem_data_model.md](
../../../docs/constraint_subsystem_data_model.md) §5 Gap G1, the
PRD-2 product prototype ships a ``类别`` (category) column with
SPATIAL / SEQUENCE / TORQUE / SAFETY / ... values.

Today ``process_constraints.kind`` carries only the *solver-shape*
discriminator (predecessor / resource / takt / exclusion); product
classification is missing.  Tag-based filtering does not work for the
fast-path UI badge / report grouping that the prototype demands.

Changes
-------
1. New ENUM ``constraint_category`` (10 values, closed set; new values
   require an ADR per [CLAUDE.md](../../../CLAUDE.md) §10).
2. ``process_constraints.category`` ``NOT NULL DEFAULT 'OTHER'``.
3. Backfill rule (deterministic, applied in the same transaction):

       kind=='exclusion'   -> SPATIAL
       kind=='predecessor' -> SEQUENCE
       kind=='resource'    -> RESOURCE
       kind=='takt'        -> QUALITY

   This matches the table in shared/db_schemas docstring; rows that do
   not match (defensive) keep ``OTHER``.
4. Composite index ``idx_pc_set_category`` for the workbench filter.

Downgrade
---------
Drops the index, the column, and the type. Idempotent.
"""

from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision = "0019_constraint_category"
down_revision = "0018_run_evaluations"
branch_labels = None
depends_on = None


ENUM_CATEGORY = "constraint_category"


def upgrade() -> None:
    # ─────────────────────────── 1. ENUM ───────────────────────────
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_type WHERE typname = '{ENUM_CATEGORY}'
            ) THEN
                CREATE TYPE {ENUM_CATEGORY} AS ENUM (
                    'SPATIAL',        -- 间距 / 净高 / 可达性
                    'SEQUENCE',       -- 工艺先后
                    'TORQUE',         -- 力矩 / 装配工艺参数
                    'SAFETY',         -- 双人作业 / 通风 / 防爆
                    'ENVIRONMENTAL',  -- 温湿度 / 洁净度 / ESD
                    'REGULATORY',     -- 适航 / CCAR / AS9100
                    'QUALITY',        -- 首件 / SPC / 节拍
                    'RESOURCE',       -- 人员 / 工装 / 能源
                    'LOGISTICS',      -- AGV 路径 / 缓存上限
                    'OTHER'           -- 兜底，触发审核
                );
            END IF;
        END
        $$;
        """
    )

    # ──────────────── 2. column with safe default ────────────────
    op.execute(
        f"""
        ALTER TABLE process_constraints
            ADD COLUMN IF NOT EXISTS category {ENUM_CATEGORY}
                                                NOT NULL
                                                DEFAULT 'OTHER';
        """
    )

    # ──────────────── 3. deterministic backfill ────────────────
    op.execute(
        """
        UPDATE process_constraints
           SET category = CASE kind
               WHEN 'exclusion'   THEN 'SPATIAL'::constraint_category
               WHEN 'predecessor' THEN 'SEQUENCE'::constraint_category
               WHEN 'resource'    THEN 'RESOURCE'::constraint_category
               WHEN 'takt'        THEN 'QUALITY'::constraint_category
               ELSE 'OTHER'::constraint_category
           END
         WHERE category = 'OTHER'::constraint_category;
        """
    )

    # ──────────────────── 4. composite index ────────────────────
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_pc_set_category
            ON process_constraints (constraint_set_id, category)
            WHERE deleted_at IS NULL;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP INDEX IF EXISTS idx_pc_set_category;
        ALTER TABLE process_constraints DROP COLUMN IF EXISTS category;
        """
    )
    op.execute(f"DROP TYPE IF EXISTS {ENUM_CATEGORY};")
