"""0017 asset provenance extension — D5 evaluation hooks on asset_geometries.

Revision ID: 0017_asset_provenance_extension
Revises: 0016_constraint_evidence
Create Date: 2026-04-27

Why
---
Per [ExcPlan/parse_agent_evaluation_dimensions.md §1 D5](
../../../ExcPlan/parse_agent_evaluation_dimensions.md#1-评估维度--5-维d1d5)
("可追溯 + 工程化") the auditor and downstream agents need to know,
**for every asset row**: (a) by what classifier kind it was produced
(rule_block / rule_layer / rule_geom / heuristic / llm_fallback),
(b) which DXF entity it came from (so R5 Domain Expert can reverse-lookup
in the drawing), and (c) for LLM-fallback rows, **what evidence words
the LLM cited** — those words MUST be ⊆ input_tokens, otherwise the
H5_response_validator hook (`agents/parse_agent/hooks.py`) rejects the
classification as a hallucination.

`asset_geometries.classifier_kind` already exists since 0002; this
migration adds the two missing D5 inputs:

| New column          | Why                                            |
|---------------------|------------------------------------------------|
| source_entity_id    | DXF handle / cluster_id, lets R5 jump back to  |
|                     | the geometry from a Quarantine review queue    |
| evidence_keywords   | JSONB `["extar","machining"]` — H5 anti-       |
|                     | hallucination check writes this in finalize()  |
| sub_type            | §5.1 "GA-必含 占位字段" (e.g. HoningMachine /   |
|                     | WashingMachine) — Phase 5 reasoning target,    |
|                     | the column exists now to avoid a migration     |
|                     | when business rules need it                    |

Operational notes
-----------------
- All three columns are NULLABLE — backfilling existing rows is the
  ParseAgent finalize hook's job (see `agents/parse_agent/finalize.py`),
  not this migration's. Old rows simply have NULL → in the dashboard
  they read as "unknown provenance" (yellow tag) which is the correct
  signal until they get re-parsed.
- A partial-index on `(site_model_id, classifier_kind)` is added to
  let the EvaluationPanorama compute the H1–H4 hardness counts
  (`SELECT classifier_kind, COUNT(*) … WHERE site_model_id=? GROUP BY 1`)
  in O(rows-per-site) instead of full-table scan once the corpus grows.
- The GIN index on `evidence_keywords` lets the future term-drift
  detector ask "which assets cited token 'extar' anywhere in the
  corpus?" without exploding the JSON.
- Downgrade drops the index + columns. ParseAgent finalize is
  idempotent so re-running on a downgraded DB silently no-ops the
  D5 portion.

Cross-references
----------------
- `shared/models.py::Asset` — Pydantic mirrors the new columns so the
  in-memory SiteModel and the persisted asset_geometries row stay 1:1.
- `db/alembic/versions/0018_run_evaluations.py` — derives the D5
  provenance score (`d5_provenance_score = filled_columns / total *
  required_columns`) from the very columns this migration adds.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "0017_asset_provenance_extension"
down_revision = "0016_constraint_evidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. Add the three D5 / §5.1 columns. NULL-allowed to keep
    #    backwards compat with rows persisted before ParseAgent's
    #    finalize() hook is wired up. ──────────────────────────────
    op.execute(
        """
        ALTER TABLE asset_geometries
            ADD COLUMN IF NOT EXISTS source_entity_id  VARCHAR(128),
            ADD COLUMN IF NOT EXISTS evidence_keywords JSONB,
            ADD COLUMN IF NOT EXISTS sub_type          VARCHAR(64);
        """
    )

    # ── 2. Composite (site_model_id, classifier_kind) index — directly
    #    serves EvaluationPanorama's H1–H4 hardness count query. The
    #    `WHERE deleted_at IS NULL` clause keeps the index narrow on
    #    soft-delete heavy datasets. ─────────────────────────────────
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_asset_geom_site_classifier
            ON asset_geometries (site_model_id, classifier_kind)
            WHERE deleted_at IS NULL;
        """
    )

    # ── 3. GIN index on evidence_keywords (the JSONB array of strings).
    #    Enables `WHERE evidence_keywords ? 'extar'` lookups for the
    #    drift / vocab analytics pipelines without a full sequential
    #    scan. Cheap because most rows will have ≤ 5 elements. ───────
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_asset_geom_evidence_keywords
            ON asset_geometries
            USING gin (evidence_keywords jsonb_path_ops)
            WHERE evidence_keywords IS NOT NULL;
        """
    )

    # ── 4. Lightweight check: classifier_kind enum-ish constraint.
    #    Not a hard ENUM type because `heuristic` is currently
    #    open-ended (sub-kinds like `heuristic.frequency` are allowed).
    #    A CHECK on the prefix keeps the bucket usable while letting
    #    Phase 5 introduce more granular tags. ─────────────────────────
    op.execute(
        """
        ALTER TABLE asset_geometries
            DROP CONSTRAINT IF EXISTS ck_asset_geom_classifier_kind_prefix;
        ALTER TABLE asset_geometries
            ADD CONSTRAINT ck_asset_geom_classifier_kind_prefix CHECK (
                classifier_kind IS NULL
                OR classifier_kind LIKE 'rule\\_%' ESCAPE '\\'
                OR classifier_kind = 'heuristic'
                OR classifier_kind LIKE 'heuristic.%'
                OR classifier_kind = 'llm_fallback'
            );
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE asset_geometries
            DROP CONSTRAINT IF EXISTS ck_asset_geom_classifier_kind_prefix;
        DROP INDEX IF EXISTS idx_asset_geom_evidence_keywords;
        DROP INDEX IF EXISTS idx_asset_geom_site_classifier;
        ALTER TABLE asset_geometries
            DROP COLUMN IF EXISTS sub_type,
            DROP COLUMN IF EXISTS evidence_keywords,
            DROP COLUMN IF EXISTS source_entity_id;
        """
    )
