"""0018 run_evaluations — 5×4×4×加固清单 物化表 (per ParseAgent / Agent run).

Revision ID: 0018_run_evaluations
Revises: 0017_asset_provenance_extension
Create Date: 2026-04-27

Why
---
Per [ExcPlan/parse_agent_evaluation_dimensions.md](
../../../ExcPlan/parse_agent_evaluation_dimensions.md) the ParseAgent
output now has a formal **5 维 × 4 阶 × 4 闸 + 加固清单** evaluation
contract.  Today those values are buried inside
`mcp_contexts.output_payload->'llm_enrichment'->'sections'->'F_quality_breakdown'`
and friends, which means:

- `WHERE d2_semantic_score < 0.5` is impossible without `jsonb_path_ops`
  gymnastics, blocking simple "find me regressed runs" reports;
- there is no schema enforcement — a typo in `F_quality_breakdown.parse`
  silently propagates, and is only caught when a UI panel renders "—";
- there is no place to stamp the four GA gates (G1 schema / G2 gold /
  G3 LLM-judge / G4 consumer-E2E) which fire at *different times*
  (online run / per-PR CI / weekly cron / GA prep) — they all need to
  UPSERT the same row;
- there is no reasonable way to plot "D5 provenance coverage drift over
  the last 30 days for site_model X" for the dashboard banner.

This migration introduces a single materialised aggregate per agent
run, modelled as a 1-to-1 sidecar to `mcp_contexts`. The JSONB blob in
`mcp_contexts.output_payload` is **kept** as the source of truth; this
table is a *projection* that gets UPSERT-ed by the ParseAgent finalize
hook (online for D1/D2/D3/D4/D5 + G1 + H1–H4 + reinforcement) and by
later CI / cron jobs (G2/G3/G4).

Schema design
-------------
Pivots the 5 evaluation dimensions, 4 GA gates, 4 hardness counts and
the (open-ended) reinforcement-checklist into typed columns wherever a
binary or numeric pivot is stable, falling back to JSONB only for the
intentionally-extensible reinforcement payload and `block_reasons`:

```
┌─ 5 dimensions ─────────┐  ┌─ 4 gates ────────────┐  ┌─ 4 hardness ┐
│ d1_geometry_score      │  │ g1_schema_pass       │  │ h1_count    │
│ d2_semantic_score      │  │ g2_gold_score        │  │ h2_count    │
│ d3_topology_score (?)  │  │ g3_llm_judge_score   │  │ h3_count    │
│ d4_contract_pass       │  │ g4_e2e_pass          │  │ h4_count    │
│ d5_provenance_score    │  └──────────────────────┘  └─────────────┘
└────────────────────────┘
                      reinforcement: jsonb (4-key dict, extensible)
                      overall_score / should_block / block_reasons
```

Why a separate table and not extra columns on `mcp_contexts`:
1. `mcp_contexts` already has ~20 cols + a fat JSONB; adding 20 more
   would push the row off-page and slow `SELECT * FROM mcp_contexts`
   queries even on unrelated reads.
2. UPSERT semantics (G2/G3/G4 land **after** the row is created) are
   cleaner with a child table where ON CONFLICT (mcp_context_id) makes
   the intent obvious.
3. We may want to evaluate the same `mcp_context` from multiple angles
   in the future (e.g. R5 manual review override). Putting evaluation
   in a sidecar leaves room to relax the UNIQUE constraint to
   (mcp_context_id, evaluator_kind) without breaking `mcp_contexts`.

Cross-references
----------------
- `agents/parse_agent/finalize.py` — writes the 5 dim + G1 + H1-H4 +
  reinforcement block at the end of every parse run.
- `scripts/gold_eval.py` — UPSERTs G2 + d3_topology_score (link
  precision/recall) when invoked from CI.
- `scripts/llm_judge_weekly.py` — UPSERTs G3 from the weekly cron.
- `web/src/components/sites/EvaluationPanorama.tsx` — direct consumer
  of every column on this table; the column names map 1:1 to the
  banner's tiles.
- `agent_kind` is left wide (`varchar(40)`) so S2 ConstraintAgent /
  S3 LayoutAgent can reuse this table by changing the agent_kind
  discriminator and remapping the D-dimension semantics; the table
  shape is intentionally agent-agnostic.

Operational notes
-----------------
- `mcp_context_id` UNIQUE: at most one ParseAgent evaluation per run.
  When `evaluator_kind` is broadened later, drop UNIQUE and add a
  composite (`mcp_context_id`, `evaluator_kind`).
- Score columns use `NUMERIC(4,3)` (range 0.000–1.000) to match the
  gold-eval / LLM-judge precision; storing a float on the bus adds
  noise that breaks `=` checks across env.
- `chk_eval_scores` enforces the 0..1 range on every score column.
- `block_reasons` is JSONB array of strings; if `should_block=false`
  it should be `NULL` (CHECK enforces this to avoid stale truthy
  reasons confusing operators).
- We index `(site_model_id, run_at DESC)` for the time-series chart
  on the EvaluationPanorama, and add a partial index on
  `should_block=true` for the global "Quarantine" review queue.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "0018_run_evaluations"
down_revision = "0017_asset_provenance_extension"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS run_evaluations (
            id                       BIGSERIAL PRIMARY KEY,
            mcp_context_id           VARCHAR(100) NOT NULL UNIQUE
                                     REFERENCES mcp_contexts(mcp_context_id)
                                     ON DELETE CASCADE,
            site_model_id            VARCHAR(50)  NOT NULL
                                     REFERENCES site_models(site_model_id)
                                     ON DELETE CASCADE,
            agent_kind               VARCHAR(40)  NOT NULL DEFAULT 'parse_agent',
            evaluator_kind           VARCHAR(32)  NOT NULL DEFAULT 'auto',
                -- 'auto' | 'gold_ci' | 'llm_judge_cron' | 'r5_manual'
            run_at                   TIMESTAMPTZ  NOT NULL DEFAULT now(),

            -- ── 5 维评估（D1–D5） ─────────────────────────────────
            d1_geometry_score        NUMERIC(4,3) NOT NULL,
            d2_semantic_score        NUMERIC(4,3) NOT NULL,
            d3_topology_score        NUMERIC(4,3),
                -- NULL = agent does not produce relations (e.g. ParseAgent v1.0
                -- before link_precision lands; ConstraintAgent will fill it).
            d4_contract_pass         BOOLEAN      NOT NULL,
            d5_provenance_score      NUMERIC(4,3) NOT NULL,

            -- ── 4 GA 闸门 ────────────────────────────────────────
            -- All NULLABLE except G1 (which can be evaluated online).
            -- G2/G3/G4 are UPSERTed by external pipelines.
            g1_schema_pass           BOOLEAN      NOT NULL,
            g2_gold_score            NUMERIC(4,3),
            g3_llm_judge_score       NUMERIC(4,3),
            g4_e2e_pass              BOOLEAN,

            -- ── 4 阶硬度计数（H1 几何 / H2 字面量 / H3 消歧 / H4 LLM 兜底） ─
            -- Mirrors `Asset.classifier_kind` distribution after finalize.
            h1_count                 INTEGER      NOT NULL DEFAULT 0,
            h2_count                 INTEGER      NOT NULL DEFAULT 0,
            h3_count                 INTEGER      NOT NULL DEFAULT 0,
            h4_count                 INTEGER      NOT NULL DEFAULT 0,

            -- ── 加固清单 (§5) — 动态扩展，4 项启动状态 ─────────────
            -- 形如:
            -- {"sub_type_field":"ok",
            --  "link_precision":"fail",
            --  "stable_run_hash":"warn",
            --  "r5_quarantine_url":"fail"}
            reinforcement            JSONB        NOT NULL DEFAULT '{}'::jsonb,

            -- ── 综合判定 — 驱动顶部 banner 颜色与是否进入 Quarantine ─
            overall_score            NUMERIC(4,3) NOT NULL,
            should_block             BOOLEAN      NOT NULL DEFAULT false,
            block_reasons            JSONB,
                -- e.g. '["D2<0.85 (词典覆盖不足)","D5<0.5 (provenance 缺失)"]'

            -- ── 软删除 / 审计 ────────────────────────────────────
            created_at               TIMESTAMPTZ  NOT NULL DEFAULT now(),
            updated_at               TIMESTAMPTZ  NOT NULL DEFAULT now(),
            deleted_at               TIMESTAMPTZ,

            -- 0..1 range guard on every score column.
            CONSTRAINT chk_eval_scores CHECK (
                d1_geometry_score   BETWEEN 0 AND 1 AND
                d2_semantic_score   BETWEEN 0 AND 1 AND
                (d3_topology_score    IS NULL OR d3_topology_score    BETWEEN 0 AND 1) AND
                d5_provenance_score BETWEEN 0 AND 1 AND
                (g2_gold_score        IS NULL OR g2_gold_score        BETWEEN 0 AND 1) AND
                (g3_llm_judge_score   IS NULL OR g3_llm_judge_score   BETWEEN 0 AND 1) AND
                overall_score       BETWEEN 0 AND 1
            ),

            -- block_reasons MUST be present iff should_block=true, and
            -- must be a JSON array (not an object / string), to avoid
            -- the "I marked block=true but forgot to say why" failure
            -- mode that confused R5 reviewers in the corpus pilot.
            CONSTRAINT chk_block_reasons_shape CHECK (
                (should_block = false AND block_reasons IS NULL)
                OR
                (should_block = true
                 AND block_reasons IS NOT NULL
                 AND jsonb_typeof(block_reasons) = 'array'
                 AND jsonb_array_length(block_reasons) > 0)
            )
        );
        """
    )

    # Hot-path indexes:
    # 1. Time-series per site (banner renders sparkline).
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_run_eval_site_time
            ON run_evaluations (site_model_id, run_at DESC)
            WHERE deleted_at IS NULL;
        """
    )

    # 2. Quarantine review queue: "show me everything currently blocking".
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_run_eval_blocked
            ON run_evaluations (run_at DESC)
            WHERE should_block = true AND deleted_at IS NULL;
        """
    )

    # 3. Cross-corpus drift detector: "find runs whose D2 dropped below
    #    the GA threshold of 0.5". Partial index keeps it tiny.
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_run_eval_d2_low
            ON run_evaluations (d2_semantic_score, run_at DESC)
            WHERE d2_semantic_score < 0.5 AND deleted_at IS NULL;
        """
    )

    # 4. Forward-compat: future S2/S3 agents will share this table.
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_run_eval_agent_kind
            ON run_evaluations (agent_kind, run_at DESC)
            WHERE deleted_at IS NULL;
        """
    )

    # `updated_at` auto-refresh trigger so UPSERT from the gold-CI / cron
    # paths bumps the timestamp without the writer having to remember.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION trg_run_eval_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        DROP TRIGGER IF EXISTS run_eval_updated_at ON run_evaluations;
        CREATE TRIGGER run_eval_updated_at
            BEFORE UPDATE ON run_evaluations
            FOR EACH ROW
            EXECUTE FUNCTION trg_run_eval_updated_at();
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TRIGGER IF EXISTS run_eval_updated_at ON run_evaluations;
        DROP FUNCTION IF EXISTS trg_run_eval_updated_at();
        DROP INDEX IF EXISTS idx_run_eval_agent_kind;
        DROP INDEX IF EXISTS idx_run_eval_d2_low;
        DROP INDEX IF EXISTS idx_run_eval_blocked;
        DROP INDEX IF EXISTS idx_run_eval_site_time;
        DROP TABLE IF EXISTS run_evaluations;
        """
    )
