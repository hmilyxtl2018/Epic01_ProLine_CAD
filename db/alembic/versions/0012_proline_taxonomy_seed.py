"""0012 production-line taxonomy: extend AssetType enum + seed 200 gold terms.

Revision ID: 0012_proline_taxonomy_seed
Revises: 0011_audit_actor_backfill
Create Date: 2026-04-22

Why
---
Phase 1.1 of `docs/ROADMAP_3D_SIM.md`. Symptoms before this migration:

- `taxonomy_terms` had **1** gold row (`conveyor`); softmatch
  cosine-NN had nothing to match against → real DXFs reported
  "taxonomy match ratio 0.000% (0/1914)".
- `AssetType` enum only covered building/CAD-generic types; a press,
  a robot, an AGV all had to fall into `Equipment` or `Other`,
  defeating downstream 3D / S2 / S3 features that need to know
  "what kind of equipment".

Changes
-------
1.  Drop + recreate the two CHECK constraints (`asset_geometries`,
    `taxonomy_terms`, `quarantine_terms`) so the new 8 enum values are
    accepted: StampingPress, WeldingRobot, HandlingRobot, Agv, Buffer,
    OperatorStation, InspectionStation, RobotCell.
2.  Seed ~200 gold-source taxonomy_terms covering 中/英/德 surface forms
    for the six production-line domains (stamping / welding / handling
    / logistics / staffing / buffering) plus the original 14 building
    types. All inserts are `ON CONFLICT DO NOTHING` so re-running the
    migration is safe.

Operational notes
-----------------
- Idempotent: every DDL is gated on the constraint name; every INSERT
  is `ON CONFLICT DO NOTHING`.
- `shared/models.py::AssetType` is the single source of truth — keep it
  in lock-step with `_ALL_ASSET_TYPES` below.
- Downgrade re-narrows the CHECK back to the 14-value set. Any rows
  with the new types will block the downgrade by design (data loss
  prevention); operators must reclassify before reverting.
"""

from __future__ import annotations

from alembic import op


# Source of truth for the new (full) enum. Mirrors shared.models.AssetType.
_ALL_ASSET_TYPES: tuple[str, ...] = (
    # Building / CAD-generic (original 14, unchanged):
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
    # Production-line domain (new in 0012):
    "StampingPress",
    "WeldingRobot",
    "HandlingRobot",
    "Agv",
    "Buffer",
    "OperatorStation",
    "InspectionStation",
    "RobotCell",
)


def _check_clause() -> str:
    quoted = ",".join(f"'{v}'" for v in _ALL_ASSET_TYPES)
    return f"asset_type IN ({quoted})"


def _legacy_check_clause() -> str:
    """The 14-value CHECK that 0002/0004 originally created."""
    legacy = (
        "Equipment", "Conveyor", "LiftingPoint", "Zone", "Wall", "Door",
        "Pipe", "Column", "Window", "CncMachine", "ElectricalPanel",
        "StorageRack", "Annotation", "Other",
    )
    quoted = ",".join(f"'{v}'" for v in legacy)
    return f"asset_type IN ({quoted})"


# revision identifiers, used by Alembic.
revision = "0012_proline_taxonomy_seed"
down_revision = "0011_audit_actor_backfill"
branch_labels = None
depends_on = None


# ── Seed payload ────────────────────────────────────────────────────────
#
# Format: (term_normalized, term_display, asset_type)
# `term_normalized` MUST match the output of
# `app.services.enrichment.semantic.normalize_candidate(...).normalized`
# (lower-cased, underscores → spaces, no encoded suffixes). The softmatch
# step embeds these strings and compares to incoming candidates.
#
# We deliberately include 中/英/德 surface forms so that:
#   - English drawings hit `stamping_press`,
#   - German drawings hit `presse` / `pressmaschine`,
#   - 中文图纸 hits `冲压机` / `压力机`.
# After normalize_batch() runs, these all collapse to the same English
# normalized form, and gold rows below ensure the match.
#
# NOTE: keep this list manageable; the goal is *coverage*, not exhaustion.
# Cluster proposals (step D) will surface anything we missed.

_SEED: tuple[tuple[str, str, str], ...] = (
    # ── 1. Stamping / press shop ──────────────────────────────────────
    ("stamping press", "Stamping Press", "StampingPress"),
    ("hydraulic press", "Hydraulic Press", "StampingPress"),
    ("mechanical press", "Mechanical Press", "StampingPress"),
    ("servo press", "Servo Press", "StampingPress"),
    ("transfer press", "Transfer Press", "StampingPress"),
    ("tandem press line", "Tandem Press Line", "StampingPress"),
    ("press machine", "Press Machine", "StampingPress"),
    ("press brake", "Press Brake", "StampingPress"),
    ("punching machine", "Punching Machine", "StampingPress"),
    ("blanking press", "Blanking Press", "StampingPress"),
    ("die cushion", "Die Cushion", "StampingPress"),
    ("crank press", "Crank Press", "StampingPress"),
    ("冲压机", "冲压机", "StampingPress"),
    ("压力机", "压力机", "StampingPress"),
    ("液压机", "液压机", "StampingPress"),
    ("伺服压机", "伺服压机", "StampingPress"),
    ("折弯机", "折弯机", "StampingPress"),
    ("冲床", "冲床", "StampingPress"),
    ("presse", "Presse", "StampingPress"),
    ("pressmaschine", "Pressmaschine", "StampingPress"),
    ("hydraulische presse", "Hydraulische Presse", "StampingPress"),

    # ── 2. Welding ───────────────────────────────────────────────────
    ("welding robot", "Welding Robot", "WeldingRobot"),
    ("spot welding robot", "Spot Welding Robot", "WeldingRobot"),
    ("arc welding robot", "Arc Welding Robot", "WeldingRobot"),
    ("laser welding station", "Laser Welding Station", "WeldingRobot"),
    ("welding cell", "Welding Cell", "WeldingRobot"),
    ("welding fixture", "Welding Fixture", "WeldingRobot"),
    ("welding gun", "Welding Gun", "WeldingRobot"),
    ("seam welder", "Seam Welder", "WeldingRobot"),
    ("mig welder", "MIG Welder", "WeldingRobot"),
    ("tig welder", "TIG Welder", "WeldingRobot"),
    ("焊接机器人", "焊接机器人", "WeldingRobot"),
    ("点焊机器人", "点焊机器人", "WeldingRobot"),
    ("弧焊机器人", "弧焊机器人", "WeldingRobot"),
    ("焊接工位", "焊接工位", "WeldingRobot"),
    ("焊枪", "焊枪", "WeldingRobot"),
    ("schweißroboter", "Schweißroboter", "WeldingRobot"),
    ("punktschweißanlage", "Punktschweißanlage", "WeldingRobot"),

    # ── 3. Handling robots ───────────────────────────────────────────
    ("handling robot", "Handling Robot", "HandlingRobot"),
    ("loading robot", "Loading Robot", "HandlingRobot"),
    ("unloading robot", "Unloading Robot", "HandlingRobot"),
    ("pick and place robot", "Pick and Place Robot", "HandlingRobot"),
    ("palletizing robot", "Palletizing Robot", "HandlingRobot"),
    ("material handling robot", "Material Handling Robot", "HandlingRobot"),
    ("six axis robot", "6-Axis Robot", "HandlingRobot"),
    ("scara robot", "SCARA Robot", "HandlingRobot"),
    ("delta robot", "Delta Robot", "HandlingRobot"),
    ("collaborative robot", "Cobot", "HandlingRobot"),
    ("gantry robot", "Gantry Robot", "HandlingRobot"),
    ("搬运机器人", "搬运机器人", "HandlingRobot"),
    ("上下料机器人", "上下料机器人", "HandlingRobot"),
    ("码垛机器人", "码垛机器人", "HandlingRobot"),
    ("六轴机器人", "六轴机器人", "HandlingRobot"),
    ("协作机器人", "协作机器人", "HandlingRobot"),
    ("桁架机器人", "桁架机器人", "HandlingRobot"),
    ("handhabungsroboter", "Handhabungsroboter", "HandlingRobot"),
    ("palettierroboter", "Palettierroboter", "HandlingRobot"),

    # ── 4. AGV / Logistics ───────────────────────────────────────────
    ("agv", "AGV", "Agv"),
    ("automated guided vehicle", "Automated Guided Vehicle", "Agv"),
    ("forklift agv", "Forklift AGV", "Agv"),
    ("tugger agv", "Tugger AGV", "Agv"),
    ("amr", "AMR", "Agv"),
    ("autonomous mobile robot", "Autonomous Mobile Robot", "Agv"),
    ("self driving cart", "Self-Driving Cart", "Agv"),
    ("无人搬运车", "无人搬运车", "Agv"),
    ("自动导引车", "自动导引车", "Agv"),
    ("移动机器人", "移动机器人", "Agv"),
    ("叉车式agv", "叉车式 AGV", "Agv"),
    ("fts", "FTS", "Agv"),  # Fahrerloses Transportsystem
    ("fahrerloses transportsystem", "Fahrerloses Transportsystem", "Agv"),

    # ── 5. Conveyors ─────────────────────────────────────────────────
    ("conveyor", "Conveyor", "Conveyor"),
    ("belt conveyor", "Belt Conveyor", "Conveyor"),
    ("roller conveyor", "Roller Conveyor", "Conveyor"),
    ("chain conveyor", "Chain Conveyor", "Conveyor"),
    ("overhead conveyor", "Overhead Conveyor", "Conveyor"),
    ("skillet conveyor", "Skillet Conveyor", "Conveyor"),
    ("ehb", "EHB", "Conveyor"),  # Elektrohängebahn
    ("elektrohängebahn", "Elektrohängebahn", "Conveyor"),
    ("power and free conveyor", "Power & Free Conveyor", "Conveyor"),
    ("traverse car", "Traverse Car", "Conveyor"),
    ("transfer line", "Transfer Line", "Conveyor"),
    ("传送带", "传送带", "Conveyor"),
    ("辊道输送机", "辊道输送机", "Conveyor"),
    ("链式输送机", "链式输送机", "Conveyor"),
    ("悬挂输送机", "悬挂输送机", "Conveyor"),
    ("输送线", "输送线", "Conveyor"),
    ("rollenförderer", "Rollenförderer", "Conveyor"),
    ("kettenförderer", "Kettenförderer", "Conveyor"),
    ("bandförderer", "Bandförderer", "Conveyor"),

    # ── 6. Buffers / Storage ─────────────────────────────────────────
    ("buffer", "Buffer", "Buffer"),
    ("buffer zone", "Buffer Zone", "Buffer"),
    ("accumulation buffer", "Accumulation Buffer", "Buffer"),
    ("inline buffer", "Inline Buffer", "Buffer"),
    ("wip storage", "WIP Storage", "Buffer"),
    ("queue zone", "Queue Zone", "Buffer"),
    ("缓存区", "缓存区", "Buffer"),
    ("缓冲区", "缓冲区", "Buffer"),
    ("缓存料仓", "缓存料仓", "Buffer"),
    ("在制品库", "在制品库", "Buffer"),
    ("pufferzone", "Pufferzone", "Buffer"),
    ("zwischenpuffer", "Zwischenpuffer", "Buffer"),
    ("storage rack", "Storage Rack", "StorageRack"),
    ("pallet rack", "Pallet Rack", "StorageRack"),
    ("asrs", "ASRS", "StorageRack"),
    ("automated storage retrieval system", "Automated Storage & Retrieval System", "StorageRack"),
    ("立体库", "立体库", "StorageRack"),
    ("料架", "料架", "StorageRack"),
    ("货架", "货架", "StorageRack"),

    # ── 7. Operator / inspection stations ────────────────────────────
    ("operator station", "Operator Station", "OperatorStation"),
    ("workstation", "Workstation", "OperatorStation"),
    ("manual assembly station", "Manual Assembly Station", "OperatorStation"),
    ("rework station", "Rework Station", "OperatorStation"),
    ("teach pendant", "Teach Pendant", "OperatorStation"),
    ("操作工位", "操作工位", "OperatorStation"),
    ("装配工位", "装配工位", "OperatorStation"),
    ("人工工位", "人工工位", "OperatorStation"),
    ("返修工位", "返修工位", "OperatorStation"),
    ("arbeitsplatz", "Arbeitsplatz", "OperatorStation"),
    ("montagearbeitsplatz", "Montagearbeitsplatz", "OperatorStation"),

    ("inspection station", "Inspection Station", "InspectionStation"),
    ("vision inspection", "Vision Inspection", "InspectionStation"),
    ("cmm", "CMM", "InspectionStation"),
    ("coordinate measuring machine", "Coordinate Measuring Machine", "InspectionStation"),
    ("leak test station", "Leak Test Station", "InspectionStation"),
    ("end of line tester", "End-of-Line Tester", "InspectionStation"),
    ("检测工位", "检测工位", "InspectionStation"),
    ("视觉检测", "视觉检测", "InspectionStation"),
    ("三坐标测量", "三坐标测量", "InspectionStation"),
    ("终检台", "终检台", "InspectionStation"),
    ("prüfstation", "Prüfstation", "InspectionStation"),
    ("messmaschine", "Messmaschine", "InspectionStation"),

    # ── 8. Robot cells (fenced enclosures) ───────────────────────────
    ("robot cell", "Robot Cell", "RobotCell"),
    ("welding cell enclosure", "Welding Cell Enclosure", "RobotCell"),
    ("safety fence", "Safety Fence", "RobotCell"),
    ("light curtain", "Light Curtain", "RobotCell"),
    ("safety zone", "Safety Zone", "RobotCell"),
    ("机器人单元", "机器人单元", "RobotCell"),
    ("围栏", "围栏", "RobotCell"),
    ("安全围栏", "安全围栏", "RobotCell"),
    ("安全光栅", "安全光栅", "RobotCell"),
    ("schutzzaun", "Schutzzaun", "RobotCell"),
    ("sicherheitszelle", "Sicherheitszelle", "RobotCell"),

    # ── 9. CNC + machine tools ───────────────────────────────────────
    ("cnc machine", "CNC Machine", "CncMachine"),
    ("cnc lathe", "CNC Lathe", "CncMachine"),
    ("cnc mill", "CNC Mill", "CncMachine"),
    ("machining center", "Machining Center", "CncMachine"),
    ("vertical machining center", "Vertical Machining Center", "CncMachine"),
    ("turning center", "Turning Center", "CncMachine"),
    ("grinding machine", "Grinding Machine", "CncMachine"),
    ("数控机床", "数控机床", "CncMachine"),
    ("加工中心", "加工中心", "CncMachine"),
    ("数控车床", "数控车床", "CncMachine"),
    ("磨床", "磨床", "CncMachine"),
    ("drehmaschine", "Drehmaschine", "CncMachine"),
    ("fräsmaschine", "Fräsmaschine", "CncMachine"),
    ("bearbeitungszentrum", "Bearbeitungszentrum", "CncMachine"),

    # ── 10. Generic equipment fallback (kept narrow) ─────────────────
    ("equipment", "Equipment", "Equipment"),
    ("machine", "Machine", "Equipment"),
    ("device", "Device", "Equipment"),
    ("设备", "设备", "Equipment"),
    ("机器", "机器", "Equipment"),
    ("anlage", "Anlage", "Equipment"),
    ("maschine", "Maschine", "Equipment"),

    # ── 11. Building (kept short, helps mixed-use plant drawings) ────
    ("wall", "Wall", "Wall"),
    ("墙", "墙", "Wall"),
    ("wand", "Wand", "Wall"),
    ("door", "Door", "Door"),
    ("门", "门", "Door"),
    ("tür", "Tür", "Door"),
    ("window", "Window", "Window"),
    ("窗", "窗", "Window"),
    ("fenster", "Fenster", "Window"),
    ("column", "Column", "Column"),
    ("柱", "柱", "Column"),
    ("stütze", "Stütze", "Column"),
    ("pipe", "Pipe", "Pipe"),
    ("管道", "管道", "Pipe"),
    ("rohr", "Rohr", "Pipe"),
    ("electrical panel", "Electrical Panel", "ElectricalPanel"),
    ("electrical cabinet", "Electrical Cabinet", "ElectricalPanel"),
    ("控制柜", "控制柜", "ElectricalPanel"),
    ("配电柜", "配电柜", "ElectricalPanel"),
    ("schaltschrank", "Schaltschrank", "ElectricalPanel"),
    ("zone", "Zone", "Zone"),
    ("区域", "区域", "Zone"),
    ("bereich", "Bereich", "Zone"),
    ("lifting point", "Lifting Point", "LiftingPoint"),
    ("吊点", "吊点", "LiftingPoint"),
    ("hebepunkt", "Hebepunkt", "LiftingPoint"),
    ("annotation", "Annotation", "Annotation"),
    ("dimension", "Dimension", "Annotation"),
    ("text", "Text", "Annotation"),
    ("标注", "标注", "Annotation"),
    ("尺寸", "尺寸", "Annotation"),
    ("bemaßung", "Bemaßung", "Annotation"),
    ("beschriftung", "Beschriftung", "Annotation"),
)


# ── Migration body ──────────────────────────────────────────────────────


def _replace_check(table: str, constraint: str, new_clause: str) -> None:
    """DROP IF EXISTS + ADD; idempotent across reruns."""
    op.execute(f'ALTER TABLE "{table}" DROP CONSTRAINT IF EXISTS "{constraint}"')
    op.execute(f'ALTER TABLE "{table}" ADD CONSTRAINT "{constraint}" CHECK ({new_clause})')


def upgrade() -> None:
    new_clause = _check_clause()
    _replace_check("asset_geometries", "ck_asset_geom_asset_type_enum", new_clause)
    _replace_check("taxonomy_terms", "ck_taxonomy_terms_asset_type_enum", new_clause)
    _replace_check("quarantine_terms", "ck_quarantine_terms_asset_type_enum", new_clause)

    # Bulk insert via VALUES list. ON CONFLICT respects the partial unique
    # index `uq_taxonomy_terms_term_type_alive` (term_normalized, asset_type)
    # WHERE deleted_at IS NULL.
    rows = ",".join(
        f"('{n.replace(chr(39), chr(39)*2)}', '{d.replace(chr(39), chr(39)*2)}', '{t}', 'gold')"
        for n, d, t in _SEED
    )
    op.execute(
        f"""
        INSERT INTO taxonomy_terms (term_normalized, term_display, asset_type, source)
        VALUES {rows}
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    # Refuse if any row uses the new types — protects against silent data
    # loss on rollback.
    op.execute(
        """
        DO $$
        DECLARE
            offending integer := 0;
        BEGIN
            SELECT COUNT(*) INTO offending FROM taxonomy_terms
             WHERE asset_type IN (
                'StampingPress','WeldingRobot','HandlingRobot','Agv',
                'Buffer','OperatorStation','InspectionStation','RobotCell'
             );
            IF offending > 0 THEN
                RAISE EXCEPTION '0012 downgrade blocked: % taxonomy_terms rows use new asset_type values; reclassify or hard-delete first', offending;
            END IF;
        END
        $$;
        """
    )
    legacy = _legacy_check_clause()
    _replace_check("asset_geometries", "ck_asset_geom_asset_type_enum", legacy)
    _replace_check("taxonomy_terms", "ck_taxonomy_terms_asset_type_enum", legacy)
    _replace_check("quarantine_terms", "ck_quarantine_terms_asset_type_enum", legacy)
