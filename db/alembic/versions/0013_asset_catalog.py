"""0013 asset_catalog: default 3D dimensions / color / mobility per AssetType.

Revision ID: 0013_asset_catalog
Revises: 0012_proline_taxonomy_seed
Create Date: 2026-04-22

Why
---
Phase 1.3 of `docs/ROADMAP_3D_SIM.md`. Phase 3 (3D MVP) needs a
deterministic way to extrude a 2D footprint into a meaningful box:

- DXF only gives us a polygon; height is unknown.
- We must NOT ask the LLM for height per-asset (cost + latency + drift).
- A small per-AssetType lookup is sufficient for the MVP — operators
  can override per-instance later via `layout_3d_placements` (Phase 3).

Schema
------
One row per `AssetType` (22 rows total). Columns:

- `default_length_m`  / `default_width_m`  / `default_height_m`
    Realistic envelope in metres; sourced from typical industrial
    spec-sheets. Used as fallback when the parsed footprint is missing
    a dimension.
- `color_hex`        Visualisation tint for the 3D viewer (#RRGGBB).
- `category`         Coarse bucket: building / machine / robot /
                     logistics / station / annotation. Drives default
                     UI grouping and material picker.
- `mobility`         `static` (welded to floor) vs `dynamic` (AGV,
                     robots) — Phase 5 simulation needs to know which
                     assets can move.
- `default_clearance_m`   Safety margin for static collision (Phase 4).
- `notes`            Free text for human reviewers.

Operational notes
-----------------
- Idempotent: bulk INSERT with `ON CONFLICT (asset_type) DO NOTHING`.
- The CHECK constraint pins `asset_type` to the same enum used by
  `asset_geometries` / `taxonomy_terms` (extended in 0012).
- Downgrade drops the table.
"""

from __future__ import annotations

from alembic import op


# Mirror of shared.models.AssetType. Kept inline so the migration is
# self-contained (alembic should not import application code).
_ALL_ASSET_TYPES: tuple[str, ...] = (
    "Equipment", "Conveyor", "LiftingPoint", "Zone", "Wall", "Door",
    "Pipe", "Column", "Window", "CncMachine", "ElectricalPanel",
    "StorageRack", "Annotation", "Other",
    "StampingPress", "WeldingRobot", "HandlingRobot", "Agv", "Buffer",
    "OperatorStation", "InspectionStation", "RobotCell",
)


# (asset_type, length_m, width_m, height_m, color_hex, category, mobility, clearance_m, notes)
# Dimensions chosen from typical industrial envelopes; height = 0 means
# "decorative / no extrusion" (Annotation, Zone, LiftingPoint).
_CATALOG: tuple[tuple, ...] = (
    # ── Building / CAD-generic ──
    ("Wall",              0.20, 0.20, 3.000, "#9CA3AF", "building",   "static",  0.00, "Generic interior wall, 3 m clear height"),
    ("Door",              1.00, 0.20, 2.100, "#A78BFA", "building",   "static",  0.30, "Standard single-leaf door"),
    ("Window",            1.50, 0.20, 1.500, "#60A5FA", "building",   "static",  0.00, "Punched window opening"),
    ("Column",            0.50, 0.50, 4.000, "#6B7280", "building",   "static",  0.20, "Steel/RC column, ground to truss"),
    ("Pipe",              0.20, 0.20, 3.000, "#FBBF24", "building",   "static",  0.10, "Process pipe (cylindrical extrusion)"),
    ("Zone",              0.00, 0.00, 0.000, "#10B981", "annotation", "static",  0.00, "Logical area marker, no 3D body"),
    ("LiftingPoint",      0.30, 0.30, 0.100, "#F59E0B", "annotation", "static",  0.00, "Hoist/crane attachment marker"),
    ("Annotation",        0.00, 0.00, 0.000, "#94A3B8", "annotation", "static",  0.00, "Text/dimension, no 3D body"),
    # ── Generic / fallback ──
    ("Equipment",         2.00, 1.50, 1.800, "#64748B", "machine",    "static",  0.50, "Generic process equipment"),
    ("Other",             1.50, 1.50, 1.500, "#94A3B8", "machine",    "static",  0.30, "Catch-all unknown asset"),
    ("ElectricalPanel",   0.80, 0.60, 2.000, "#F87171", "machine",    "static",  0.80, "Wall/floor mounted control cabinet"),
    ("StorageRack",       2.00, 1.00, 2.500, "#A3E635", "logistics",  "static",  0.50, "Pallet rack, 2-3 levels"),
    # ── Production-line machines ──
    ("StampingPress",     4.00, 3.00, 4.500, "#DC2626", "machine",    "static",  1.50, "Tandem press / blanking press body"),
    ("CncMachine",        3.00, 2.50, 2.500, "#0EA5E9", "machine",    "static",  1.00, "Machining center / CNC lathe envelope"),
    ("Conveyor",          6.00, 0.80, 0.900, "#FACC15", "logistics",  "static",  0.30, "Roller/belt conveyor, single segment"),
    # ── Robots ──
    ("WeldingRobot",      1.50, 1.50, 2.500, "#FB923C", "robot",      "dynamic", 1.20, "6-axis arm with welding torch"),
    ("HandlingRobot",     1.50, 1.50, 2.500, "#F97316", "robot",      "dynamic", 1.20, "Pick-and-place / loading robot"),
    ("RobotCell",         5.00, 4.00, 3.000, "#7C3AED", "robot",      "static",  0.40, "Fenced enclosure containing robots"),
    # ── Logistics ──
    ("Agv",               1.20, 0.80, 0.400, "#22D3EE", "logistics",  "dynamic", 0.80, "Automated guided vehicle, low platform"),
    ("Buffer",            3.00, 2.00, 0.500, "#84CC16", "logistics",  "static",  0.20, "WIP buffer / accumulation zone"),
    # ── Operator / inspection stations ──
    ("OperatorStation",   1.50, 1.00, 2.000, "#3B82F6", "station",    "static",  0.50, "Manual workstation, ergonomic envelope"),
    ("InspectionStation", 2.00, 2.00, 2.500, "#8B5CF6", "station",    "static",  0.60, "CMM / vision inspection booth"),
)


# revision identifiers, used by Alembic.
revision = "0013_asset_catalog"
down_revision = "0012_proline_taxonomy_seed"
branch_labels = None
depends_on = None


def _check_clause() -> str:
    quoted = ",".join(f"'{v}'" for v in _ALL_ASSET_TYPES)
    return f"asset_type IN ({quoted})"


def upgrade() -> None:
    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS asset_catalog (
            asset_type           VARCHAR(64)  PRIMARY KEY,
            default_length_m     NUMERIC(8,3) NOT NULL,
            default_width_m      NUMERIC(8,3) NOT NULL,
            default_height_m     NUMERIC(8,3) NOT NULL,
            color_hex            VARCHAR(7)   NOT NULL,
            category             VARCHAR(32)  NOT NULL,
            mobility             VARCHAR(16)  NOT NULL DEFAULT 'static',
            default_clearance_m  NUMERIC(6,3) NOT NULL DEFAULT 0.0,
            notes                TEXT,
            schema_version       SMALLINT     NOT NULL DEFAULT 1,
            created_at           TIMESTAMPTZ  NOT NULL DEFAULT now(),
            updated_at           TIMESTAMPTZ  NOT NULL DEFAULT now(),
            deleted_at           TIMESTAMPTZ,
            CONSTRAINT ck_asset_catalog_type CHECK ({_check_clause()}),
            CONSTRAINT ck_asset_catalog_mobility CHECK (mobility IN ('static','dynamic')),
            CONSTRAINT ck_asset_catalog_color CHECK (color_hex ~ '^#[0-9A-Fa-f]{{6}}$'),
            CONSTRAINT ck_asset_catalog_dims_nonneg CHECK (
                default_length_m >= 0 AND default_width_m >= 0 AND default_height_m >= 0
            )
        );
        """
    )

    # Bulk seed.
    values_sql = ",\n        ".join(
        "("
        f"'{at}', {l}, {w}, {h}, '{col}', '{cat}', '{mob}', {clr}, "
        f"{'NULL' if notes is None else repr(notes)}"
        ")"
        for (at, l, w, h, col, cat, mob, clr, notes) in _CATALOG
    )
    op.execute(
        f"""
        INSERT INTO asset_catalog
            (asset_type, default_length_m, default_width_m, default_height_m,
             color_hex, category, mobility, default_clearance_m, notes)
        VALUES
        {values_sql}
        ON CONFLICT (asset_type) DO NOTHING;
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS asset_catalog;")
