"""0022 hierarchy_nodes — IEC 81346 三视角 / ISA-95 层级实体表 (ADR-0009).

Revision ID: 0022_hierarchy_nodes
Revises: 0021_constraint_source_hash
Create Date: 2026-05-07

Why
---
Per [ADR-0009 时空约束本体](../../../docs/adr/0009-spacetime-constraint-ontology.md)
§2.1, the previous ``process_constraints.payload.asset_ids`` string array
provides no FK, no aspect (Function/Product/Location), no hierarchy and no
inheritance — Layout / Sim / scheduling cannot consume it correctly.

This migration introduces a *single* ``hierarchy_nodes`` table that holds
every grouping concept the constraint workbench needs:

- IEC/ISO 81346 ``aspect`` discriminator (FUNCTION ``=`` / PRODUCT ``-`` /
  LOCATION ``+``); same physical object may appear under multiple aspects
  via separate rows (cross-aspect alias kept in ``properties.aspect_alias``).
- ISA-95 / IEC 62264 ``node_kind`` discriminator (Enterprise → Site → Area
  → Line → WorkCenter → Station → Equipment), extended with Tool / Fixture
  / Material / Procedure / Document / AssetTypeTemplate.
- Self-referential ``parent_id`` to form the hierarchy tree per aspect.
- Optional soft pointers ``asset_guid`` and ``process_step_id`` (no DB-level
  FK — ``asset_geometries`` keys on the composite ``(site_model_id, asset_guid)``
  and ProcessStep table is reserved). Application layer enforces resolution.
  The node is a *handle* to the existing physical fact, never a copy.

Schema notes
------------
- ``rds_code`` is the IEC 81346 reference designation, e.g. ``+S03.A1-K1``.
  Globally unique among live rows (partial unique index).
- ``properties`` is JSONB with ``ck_hn_properties_object`` to keep it shaped
  like the rest of the codebase (see 0014 ``ck_proc_constraints_payload_object``).
- Common ops columns ``mcp_context_id``, ``schema_version``, ``deleted_at``
  follow the convention from ``shared/db_schemas.py`` header.
- INV-16 (aspect ↔ node_kind matrix) is enforced via CHECK
  ``ck_hn_aspect_kind_matrix``: FUNCTION must be Procedure / Document;
  LOCATION must be Enterprise / Site / Area / Line / WorkCenter / Station;
  PRODUCT must be Equipment / Tool / Fixture / Material / AssetTypeTemplate.

Downgrade
---------
Drops indexes, constraints, then table. Idempotent.
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0022_hierarchy_nodes"
down_revision = "0021_constraint_source_hash"
branch_labels = None
depends_on = None


_ASPECTS = ("FUNCTION", "PRODUCT", "LOCATION")

_NODE_KINDS = (
    # ISA-95 / LOCATION 主用
    "Enterprise",
    "Site",
    "Area",
    "Line",
    "WorkCenter",
    "Station",
    # PRODUCT 主用
    "Equipment",
    "Tool",
    "Fixture",
    "Material",
    "AssetTypeTemplate",
    # FUNCTION 主用
    "Procedure",
    "Document",
)

_FUNCTION_KINDS = ("Procedure", "Document")
_LOCATION_KINDS = ("Enterprise", "Site", "Area", "Line", "WorkCenter", "Station")
_PRODUCT_KINDS = ("Equipment", "Tool", "Fixture", "Material", "AssetTypeTemplate")


def _quote_list(values: tuple[str, ...]) -> str:
    return ",".join(f"'{v}'" for v in values)


def upgrade() -> None:
    aspects_sql = _quote_list(_ASPECTS)
    kinds_sql = _quote_list(_NODE_KINDS)
    function_sql = _quote_list(_FUNCTION_KINDS)
    location_sql = _quote_list(_LOCATION_KINDS)
    product_sql = _quote_list(_PRODUCT_KINDS)

    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS hierarchy_nodes (
            id               UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
            rds_code         VARCHAR(64)  NOT NULL,
            aspect           VARCHAR(16)  NOT NULL,
            node_kind        VARCHAR(32)  NOT NULL,
            parent_id        UUID         REFERENCES hierarchy_nodes(id) ON DELETE RESTRICT,
            asset_guid       VARCHAR(50),
            process_step_id  UUID,
            site_model_id    VARCHAR(50)  REFERENCES site_models(site_model_id) ON DELETE CASCADE,
            name_zh          VARCHAR(200) NOT NULL,
            name_en          VARCHAR(200),
            properties       JSONB        NOT NULL DEFAULT '{{}}'::jsonb,
            created_by       VARCHAR(100),
            mcp_context_id   VARCHAR(100) REFERENCES mcp_contexts(mcp_context_id),
            schema_version   SMALLINT     NOT NULL DEFAULT 1,
            created_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
            updated_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
            deleted_at       TIMESTAMPTZ,
            CONSTRAINT ck_hn_aspect_enum
                CHECK (aspect IN ({aspects_sql})),
            CONSTRAINT ck_hn_node_kind_enum
                CHECK (node_kind IN ({kinds_sql})),
            CONSTRAINT ck_hn_properties_object
                CHECK (jsonb_typeof(properties) = 'object'),
            CONSTRAINT ck_hn_no_self_parent
                CHECK (parent_id IS NULL OR parent_id <> id),
            CONSTRAINT ck_hn_aspect_kind_matrix CHECK (
                   (aspect = 'FUNCTION' AND node_kind IN ({function_sql}))
                OR (aspect = 'LOCATION' AND node_kind IN ({location_sql}))
                OR (aspect = 'PRODUCT'  AND node_kind IN ({product_sql}))
            )
        );
        """
    )

    # rds_code globally unique among live rows; reuse via DELETE+restore allowed.
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_hn_rds_code_live
            ON hierarchy_nodes (rds_code)
            WHERE deleted_at IS NULL;
        """
    )

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_hn_parent
            ON hierarchy_nodes (parent_id)
            WHERE deleted_at IS NULL;

        CREATE INDEX IF NOT EXISTS idx_hn_aspect_kind
            ON hierarchy_nodes (aspect, node_kind)
            WHERE deleted_at IS NULL;

        CREATE INDEX IF NOT EXISTS idx_hn_site_model
            ON hierarchy_nodes (site_model_id)
            WHERE deleted_at IS NULL;

        CREATE INDEX IF NOT EXISTS idx_hn_asset_guid
            ON hierarchy_nodes (asset_guid)
            WHERE asset_guid IS NOT NULL AND deleted_at IS NULL;

        CREATE INDEX IF NOT EXISTS idx_hn_properties_gin
            ON hierarchy_nodes USING gin (properties);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP INDEX IF EXISTS idx_hn_properties_gin;
        DROP INDEX IF EXISTS idx_hn_asset_guid;
        DROP INDEX IF EXISTS idx_hn_site_model;
        DROP INDEX IF EXISTS idx_hn_aspect_kind;
        DROP INDEX IF EXISTS idx_hn_parent;
        DROP INDEX IF EXISTS uq_hn_rds_code_live;
        DROP TABLE IF EXISTS hierarchy_nodes;
        """
    )
