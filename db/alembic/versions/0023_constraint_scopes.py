"""0023 constraint_scopes — N:M binding from process_constraints to hierarchy_nodes (ADR-0009).

Revision ID: 0023_constraint_scopes
Revises: 0022_hierarchy_nodes
Create Date: 2026-05-07

Why
---
Per [ADR-0009 §2.1 + §2.4](../../../docs/adr/0009-spacetime-constraint-ontology.md),
each row in ``process_constraints`` may bind to many ``hierarchy_nodes`` and
each node may carry many constraints. The link must record:

- ``binding_strategy`` — how the binding was produced (S1 explicit_id /
  S2 asset_type / S3 semantic / S4 manual). Drives audit and re-review.
- ``inherit_to_descendants`` — boolean; when TRUE the constraint applies to
  every descendant of ``node_id`` unless explicitly overridden by a more
  specific scope row. Resolution is computed in ``ScopeBindingService``.
- ``confidence`` — 0.00..1.00; auto-bindings below 0.80 enter the review
  queue, manual S4 rows are 1.00 by definition.
- ``verified_by_user_id`` / ``verified_at`` — paired audit fields; INV-17
  enforces "manual binding ⇒ verified_* NOT NULL", parallel to INV-8 on
  ``process_constraints.review_status='approved'``.

Schema notes
------------
- Composite uniqueness ``(constraint_id, node_id)`` among live rows. Same
  constraint may not bind twice to the same node; instead the strategy /
  confidence is updated in place.
- Cascade: deleting the parent ``process_constraints`` row hard-deletes the
  scope; deleting a ``hierarchy_nodes`` row is RESTRICT — caller must first
  detach scopes via the API to prevent silent orphaning.
- ``binding_evidence`` JSONB carries source citations, recall scores, etc.
  Shape validated at API layer; here only the type guard.

Downgrade
---------
Drops indexes, unique, then table. Idempotent.
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0023_constraint_scopes"
down_revision = "0022_hierarchy_nodes"
branch_labels = None
depends_on = None


_STRATEGIES = ("explicit_id", "asset_type", "semantic", "manual")


def upgrade() -> None:
    strategies_sql = ",".join(f"'{s}'" for s in _STRATEGIES)

    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS constraint_scopes (
            id                       UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
            constraint_id            UUID         NOT NULL
                                                    REFERENCES process_constraints(id)
                                                    ON DELETE CASCADE,
            node_id                  UUID         NOT NULL
                                                    REFERENCES hierarchy_nodes(id)
                                                    ON DELETE RESTRICT,
            binding_strategy         VARCHAR(20)  NOT NULL,
            inherit_to_descendants   BOOLEAN      NOT NULL DEFAULT FALSE,
            confidence               NUMERIC(3,2) NOT NULL DEFAULT 1.00,
            verified_by_user_id      VARCHAR(100),
            verified_at              TIMESTAMPTZ,
            binding_evidence         JSONB        NOT NULL DEFAULT '{{}}'::jsonb,
            created_by               VARCHAR(100),
            mcp_context_id           VARCHAR(100) REFERENCES mcp_contexts(mcp_context_id),
            schema_version           SMALLINT     NOT NULL DEFAULT 1,
            created_at               TIMESTAMPTZ  NOT NULL DEFAULT now(),
            updated_at               TIMESTAMPTZ  NOT NULL DEFAULT now(),
            deleted_at               TIMESTAMPTZ,
            CONSTRAINT ck_cscope_strategy_enum
                CHECK (binding_strategy IN ({strategies_sql})),
            CONSTRAINT ck_cscope_confidence_range
                CHECK (confidence >= 0.00 AND confidence <= 1.00),
            CONSTRAINT ck_cscope_evidence_object
                CHECK (jsonb_typeof(binding_evidence) = 'object'),
            CONSTRAINT ck_cscope_manual_verified CHECK (
                binding_strategy <> 'manual'
             OR (verified_by_user_id IS NOT NULL AND verified_at IS NOT NULL)
            )
        );
        """
    )

    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_cscope_constraint_node_live
            ON constraint_scopes (constraint_id, node_id)
            WHERE deleted_at IS NULL;

        CREATE INDEX IF NOT EXISTS idx_cscope_constraint
            ON constraint_scopes (constraint_id)
            WHERE deleted_at IS NULL;

        CREATE INDEX IF NOT EXISTS idx_cscope_node
            ON constraint_scopes (node_id)
            WHERE deleted_at IS NULL;

        CREATE INDEX IF NOT EXISTS idx_cscope_low_confidence
            ON constraint_scopes (confidence)
            WHERE confidence < 0.80 AND deleted_at IS NULL;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP INDEX IF EXISTS idx_cscope_low_confidence;
        DROP INDEX IF EXISTS idx_cscope_node;
        DROP INDEX IF EXISTS idx_cscope_constraint;
        DROP INDEX IF EXISTS uq_cscope_constraint_node_live;
        DROP TABLE IF EXISTS constraint_scopes;
        """
    )
