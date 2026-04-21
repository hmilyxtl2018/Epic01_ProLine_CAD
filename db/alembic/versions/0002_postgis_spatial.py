"""0002 PostGIS spatial extension + asset_geometries table.

Revision ID: 0002_postgis_spatial
Revises: 0001b_common_columns
Create Date: 2026-04-20

ExcPlan plan r2 §3.4.2: PostGIS for footprints and bbox queries. Introduces
the first table that uses the AssetType CHECK template and the confidence
[0,1] CHECK template.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry

revision: str = "0002_postgis_spatial"
down_revision: str | None = "0001b_common_columns"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Single source of truth for the AssetType CHECK constraint. Mirrors
# shared.models.AssetType exactly; B4 schema-drift CI will fail if they diverge.
_ASSET_TYPES: tuple[str, ...] = (
    "Equipment",
    "Conveyor",
    "LiftingPoint",
    "Zone",
    "Wall",
    "Door",
    "Pipe",
    "Column",
    "Window",
    "CncMachine",
    "ElectricalPanel",
    "StorageRack",
    "Annotation",
    "Other",
)


def _asset_type_check_clause() -> str:
    quoted = ",".join(f"'{v}'" for v in _ASSET_TYPES)
    return f"asset_type IN ({quoted})"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    # Site-level bounding box for fast spatial filter on the index page.
    # spatial_index=False: we create the GIST index explicitly below to keep
    # naming consistent with the rest of the schema (geoalchemy2's auto-name
    # would collide with our explicit `idx_site_models_bbox`).
    op.add_column(
        "site_models",
        sa.Column(
            "bbox",
            Geometry(geometry_type="POLYGON", srid=0, spatial_index=False),
            nullable=True,
        ),
    )
    op.create_index(
        "idx_site_models_bbox",
        "site_models",
        ["bbox"],
        postgresql_using="gist",
    )

    op.create_table(
        "asset_geometries",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "site_model_id",
            sa.String(50),
            sa.ForeignKey("site_models.site_model_id"),
            nullable=False,
        ),
        sa.Column("asset_guid", sa.String(50), nullable=False),
        sa.Column("asset_type", sa.String(30), nullable=False),
        sa.Column(
            "footprint",
            Geometry(geometry_type="POLYGON", srid=0, spatial_index=False),
            nullable=True,
        ),
        sa.Column(
            "centroid",
            Geometry(geometry_type="POINT", srid=0, spatial_index=False),
            nullable=True,
        ),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=True),
        sa.Column("classifier_kind", sa.String(40), nullable=True),
        sa.Column("schema_version", sa.SmallInteger, nullable=False, server_default=sa.text("1")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "mcp_context_id",
            sa.String(100),
            sa.ForeignKey("mcp_contexts.mcp_context_id"),
            nullable=True,
        ),
        sa.UniqueConstraint("site_model_id", "asset_guid", name="uq_asset_geom_site_guid"),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_asset_geom_confidence_range",
        ),
        sa.CheckConstraint(_asset_type_check_clause(), name="ck_asset_geom_asset_type_enum"),
    )
    op.create_index(
        "idx_asset_geom_footprint",
        "asset_geometries",
        ["footprint"],
        postgresql_using="gist",
    )
    op.create_index("idx_asset_geom_type", "asset_geometries", ["asset_type"])
    op.create_index(
        "idx_asset_geometries_deleted_at",
        "asset_geometries",
        ["deleted_at"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index("idx_asset_geometries_mcp_context_id", "asset_geometries", ["mcp_context_id"])


def downgrade() -> None:
    op.drop_index("idx_asset_geometries_mcp_context_id", table_name="asset_geometries")
    op.drop_index("idx_asset_geometries_deleted_at", table_name="asset_geometries")
    op.drop_index("idx_asset_geom_type", table_name="asset_geometries")
    op.drop_index("idx_asset_geom_footprint", table_name="asset_geometries")
    op.drop_table("asset_geometries")

    op.drop_index("idx_site_models_bbox", table_name="site_models")
    op.drop_column("site_models", "bbox")
    # Extension is intentionally left in place: dropping postgis would cascade
    # into other databases on the same server. Operators must drop manually.
