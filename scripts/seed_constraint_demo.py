"""Demo seed for the spacetime constraint ontology (ADR-0009).

幂等地写入一份"小而全"的演示数据，覆盖：

* `hierarchy_nodes` — 三视角 (LOCATION 树 / PRODUCT 设备 / FUNCTION 工序)
* `process_constraints` — 四种 kind × applicable_phases × valid_from/to
* `constraint_scopes` — 四种 binding_strategy (含 manual 已审核)
* `constraint_sets` — 1 个集合包络
* `audit_log_actions` — 1 条 seed_load 审计

跑完输出验证摘要。重复执行不会报错也不会重复插入。

Usage::

    $env:POSTGRES_DSN = "postgresql+psycopg2://proline:proline_dev@localhost:5434/proline_cad"
    python scripts/seed_constraint_demo.py
    python scripts/seed_constraint_demo.py --site-model-id site_demo_001
    python scripts/seed_constraint_demo.py --purge          # 先清理再插入
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import Final

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

log = logging.getLogger("seed_constraint_demo")

DEFAULT_SITE_MODEL_ID: Final[str] = "site_demo_001"
DEFAULT_MCP_CTX: Final[str] = "mcp_demo_constraint_seed"
DEFAULT_CONSTRAINT_SET_ID: Final[str] = "CS-DEMO-001"
DEFAULT_ACTOR: Final[str] = "demo@local"


# ─────────────────────────── SQL 构件 ───────────────────────────

_SQL_BASE_FIXTURES = """
INSERT INTO mcp_contexts (mcp_context_id, agent, status)
VALUES (:ctx, 'constraint_agent', 'SUCCESS')
ON CONFLICT (mcp_context_id) DO NOTHING;

INSERT INTO site_models (site_model_id, cad_source, mcp_context_id, bbox)
VALUES (
    :site,
    '{"format":"DWG","filename":"demo.dwg","dwg_hash":"demoseed01"}'::jsonb,
    :ctx,
    ST_GeomFromText('POLYGON((0 0, 200 0, 200 120, 0 120, 0 0))', 0)
)
ON CONFLICT (site_model_id) DO NOTHING;

INSERT INTO asset_geometries (
    site_model_id, asset_guid, asset_type, footprint, centroid, confidence,
    classifier_kind, mcp_context_id
)
VALUES
    (:site, 'eq_press_01', 'Equipment',
     ST_GeomFromText('POLYGON((10 10, 30 10, 30 30, 10 30, 10 10))', 0),
     ST_GeomFromText('POINT(20 20)', 0),
     0.92, 'rule_classifier', :ctx),
    (:site, 'eq_weld_01', 'Equipment',
     ST_GeomFromText('POLYGON((50 10, 70 10, 70 30, 50 30, 50 10))', 0),
     ST_GeomFromText('POINT(60 20)', 0),
     0.90, 'rule_classifier', :ctx),
    (:site, 'eq_inspect_01', 'Equipment',
     ST_GeomFromText('POLYGON((90 10, 110 10, 110 30, 90 30, 90 10))', 0),
     ST_GeomFromText('POINT(100 20)', 0),
     0.88, 'rule_classifier', :ctx)
ON CONFLICT (site_model_id, asset_guid) DO NOTHING;

INSERT INTO constraint_sets (
    constraint_set_id, version, site_model_id, status, description,
    tags, mcp_context_id
)
VALUES (
    :set_id, 'v1.0', :site, 'draft'::constraint_set_status,
    'Demo seed for ADR-0009 spacetime constraint ontology',
    ARRAY['demo','adr-0009'], :ctx
)
ON CONFLICT (constraint_set_id) DO NOTHING;
"""

# 三视角层级树。RDS 编码遵循 IEC 81346 风格 (= function, + product, - location)
# 这里仅用作演示，真实工程编码以工艺方为准。
_HIERARCHY_NODES = [
    # ── LOCATION (-) tree: Enterprise → Site → Area → Line → Station ──
    dict(rds="-ENT.AC", aspect="LOCATION", kind="Enterprise",
         parent_rds=None, name_zh="某航空制造企业"),
    dict(rds="-ENT.AC.SH01", aspect="LOCATION", kind="Site",
         parent_rds="-ENT.AC", name_zh="上海总装基地"),
    dict(rds="-ENT.AC.SH01.A2", aspect="LOCATION", kind="Area",
         parent_rds="-ENT.AC.SH01", name_zh="A2 总装厂房"),
    dict(rds="-ENT.AC.SH01.A2.L1", aspect="LOCATION", kind="Line",
         parent_rds="-ENT.AC.SH01.A2", name_zh="脉动总装 L1 线"),
    dict(rds="-ENT.AC.SH01.A2.L1.S10", aspect="LOCATION", kind="Station",
         parent_rds="-ENT.AC.SH01.A2.L1", name_zh="工位 S10 — 冲压"),
    dict(rds="-ENT.AC.SH01.A2.L1.S20", aspect="LOCATION", kind="Station",
         parent_rds="-ENT.AC.SH01.A2.L1", name_zh="工位 S20 — 焊装"),
    dict(rds="-ENT.AC.SH01.A2.L1.S30", aspect="LOCATION", kind="Station",
         parent_rds="-ENT.AC.SH01.A2.L1", name_zh="工位 S30 — 检验"),
    # ── PRODUCT (+) leaves: Equipment 实例 + AssetTypeTemplate ──
    dict(rds="+EQ.PRESS.01", aspect="PRODUCT", kind="Equipment",
         parent_rds=None, name_zh="冲压机 #01", asset_guid="eq_press_01"),
    dict(rds="+EQ.WELD.01", aspect="PRODUCT", kind="Equipment",
         parent_rds=None, name_zh="焊装机 #01", asset_guid="eq_weld_01"),
    dict(rds="+EQ.INSPECT.01", aspect="PRODUCT", kind="Equipment",
         parent_rds=None, name_zh="检验台 #01", asset_guid="eq_inspect_01"),
    dict(rds="+TPL.WELDING_ROBOT", aspect="PRODUCT", kind="AssetTypeTemplate",
         parent_rds=None, name_zh="模板 — 焊接机器人"),
    # ── FUNCTION (=) procedures ──
    dict(rds="=PROC.TS-ASSY-01", aspect="FUNCTION", kind="Procedure",
         parent_rds=None, name_zh="工艺规程 — TS-ASSY-01 总装序列"),
    dict(rds="=DOC.SOP-WELD-001", aspect="FUNCTION", kind="Document",
         parent_rds=None, name_zh="SOP-WELD-001 焊接作业指导书"),
]

# 演示约束。每条约束含 rds_targets：演示后 INSERT 时通过 rds 反查 node id 写入 scopes。
_PROCESS_CONSTRAINTS = [
    dict(
        constraint_id="PC-DEMO-PRED-01",
        kind="predecessor",
        category="SEQUENCE",       # 工艺先后顺序
        cls="hard", severity="major", authority="enterprise",
        conformance="MUST", weight=1.0, confidence=0.95,
        rationale="冲压完成后方可进入焊装",
        priority=80,
        payload={"from": "eq_press_01", "to": "eq_weld_01"},
        applicable_phases=["DESIGN", "OPERATION"],
        review_status="approved",
        parse_method="MANUAL_UI",
        verified=True,
        scopes=[
            ("=PROC.TS-ASSY-01", "explicit_id", True),
            ("-ENT.AC.SH01.A2.L1.S10", "explicit_id", False),
            ("-ENT.AC.SH01.A2.L1.S20", "explicit_id", False),
        ],
    ),
    dict(
        constraint_id="PC-DEMO-RES-01",
        kind="resource",
        category="RESOURCE",
        cls="hard", severity="major", authority="enterprise",
        conformance="MUST", weight=1.0, confidence=0.90,
        rationale="压缩空气总管供给上限",
        priority=70,
        payload={"asset_ids": ["eq_press_01", "eq_weld_01", "eq_inspect_01"],
                 "resource": "compressed_air_kPa", "capacity": 600},
        applicable_phases=["OPERATION", "MAINTENANCE"],
        review_status="approved",
        parse_method="LLM_INFERENCE",
        verified=True,
        scopes=[
            ("-ENT.AC.SH01.A2.L1", "asset_type", True),
        ],
    ),
    dict(
        constraint_id="PC-DEMO-TAKT-01",
        kind="takt",
        category="SEQUENCE",       # 节拍归入工艺序时维度
        cls="soft", severity="minor", authority="project",
        conformance="SHOULD", weight=0.7, confidence=0.65,
        rationale="节拍窗口由 PMI 推断，待工艺方确认",
        priority=60,
        payload={"asset_id": "eq_weld_01", "min_s": 90, "max_s": 240,
                 "target_s": 180, "unit": "second"},
        applicable_phases=["DESIGN", "COMMISSIONING", "OPERATION"],
        review_status="draft",
        parse_method="LLM_INFERENCE",
        verified=False,
        scopes=[
            ("+EQ.WELD.01", "explicit_id", False),
            ("+TPL.WELDING_ROBOT", "asset_type", True),
        ],
    ),
    dict(
        constraint_id="PC-DEMO-EXCL-01",
        kind="exclusion",
        category="SAFETY",
        cls="hard", severity="critical", authority="statutory",
        conformance="MUST", weight=1.0, confidence=1.00,
        rationale="冲压震源不得与精密检验台同间布置",
        priority=95,
        payload={"asset_ids": ["eq_press_01", "eq_inspect_01"],
                 "reason": "震动隔离"},
        applicable_phases=["DESIGN"],
        review_status="approved",
        parse_method="MANUAL_UI",
        verified=True,
        scopes=[
            ("-ENT.AC.SH01.A2", "manual", True),
        ],
    ),
]


# ─────────────────────────── helpers ───────────────────────────

def _get_dsn() -> str:
    dsn = os.environ.get("POSTGRES_DSN")
    if not dsn:
        raise SystemExit(
            "POSTGRES_DSN not set. Example:\n"
            "  $env:POSTGRES_DSN = 'postgresql+psycopg2://proline:proline_dev@"
            "localhost:5434/proline_cad'"
        )
    return dsn


def _purge(engine: Engine, *, site: str, set_id: str, ctx: str) -> None:
    log.info("purging existing demo rows for %s / %s", site, set_id)
    with engine.begin() as conn:
        # 先删依赖侧
        conn.execute(text("""
            DELETE FROM constraint_scopes
             WHERE constraint_id IN (
                SELECT id FROM process_constraints WHERE constraint_id LIKE 'PC-DEMO-%'
             );
            DELETE FROM process_constraints WHERE constraint_id LIKE 'PC-DEMO-%';
            DELETE FROM hierarchy_nodes
             WHERE rds_code LIKE '-ENT.AC%'
                OR rds_code LIKE '+EQ.%'
                OR rds_code LIKE '+TPL.%'
                OR rds_code LIKE '=PROC.%'
                OR rds_code LIKE '=DOC.%';
            DELETE FROM constraint_sets WHERE constraint_set_id = :set_id;
            DELETE FROM asset_geometries WHERE site_model_id = :site;
            DELETE FROM site_models WHERE site_model_id = :site;
            DELETE FROM mcp_contexts WHERE mcp_context_id = :ctx;
        """), {"site": site, "set_id": set_id, "ctx": ctx})


def _insert_base(engine: Engine, *, site: str, set_id: str, ctx: str) -> None:
    with engine.begin() as conn:
        for stmt in _SQL_BASE_FIXTURES.strip().split(";\n\n"):
            if stmt.strip():
                conn.execute(text(stmt), {"site": site, "set_id": set_id, "ctx": ctx})


def _insert_hierarchy(engine: Engine, *, site: str, ctx: str) -> dict[str, str]:
    """Insert hierarchy nodes (parents first via topological order). Returns rds → uuid."""
    rds_to_id: dict[str, str] = {}
    with engine.begin() as conn:
        for node in _HIERARCHY_NODES:
            parent_id = rds_to_id.get(node["parent_rds"]) if node["parent_rds"] else None
            row = conn.execute(text("""
                INSERT INTO hierarchy_nodes (
                    rds_code, aspect, node_kind, parent_id, asset_guid,
                    site_model_id, name_zh, mcp_context_id, created_by
                )
                VALUES (
                    :rds, :aspect, :kind, :parent_id, :asset_guid,
                    :site, :name_zh, :ctx, :actor
                )
                ON CONFLICT (rds_code) WHERE deleted_at IS NULL DO UPDATE
                    SET name_zh = EXCLUDED.name_zh
                RETURNING id;
            """), {
                "rds": node["rds"],
                "aspect": node["aspect"],
                "kind": node["kind"],
                "parent_id": parent_id,
                "asset_guid": node.get("asset_guid"),
                "site": site if node["aspect"] in ("LOCATION", "PRODUCT") else None,
                "name_zh": node["name_zh"],
                "ctx": ctx,
                "actor": DEFAULT_ACTOR,
            }).first()
            rds_to_id[node["rds"]] = str(row[0])
    log.info("hierarchy_nodes upserted: %d", len(rds_to_id))
    return rds_to_id


def _insert_constraints(
    engine: Engine,
    *,
    site: str,
    set_id: str,
    ctx: str,
    rds_to_id: dict[str, str],
) -> int:
    inserted = 0
    with engine.begin() as conn:
        cs_uuid = conn.execute(text(
            "SELECT id FROM constraint_sets WHERE constraint_set_id = :s"
        ), {"s": set_id}).scalar_one()

        for c in _PROCESS_CONSTRAINTS:
            verified_at = "NOW()" if c["verified"] else "NULL"
            row = conn.execute(text(f"""
                INSERT INTO process_constraints (
                    constraint_id, site_model_id, constraint_set_id,
                    kind, payload, priority,
                    class, severity, authority, conformance,
                    weight, confidence, rationale,
                    category, review_status, parse_method,
                    verified_by_user_id, verified_at, needs_re_review,
                    applicable_phases, valid_from, valid_to,
                    created_by, mcp_context_id
                )
                VALUES (
                    :cid, :site, :cs_uuid,
                    :kind, CAST(:payload AS JSONB), :priority,
                    CAST(:cls AS constraint_class),
                    CAST(:sev AS constraint_severity),
                    CAST(:auth AS constraint_authority),
                    CAST(:conf_e AS constraint_conformance),
                    :weight, :confidence, :rationale,
                    CAST(:category AS constraint_category),
                    CAST(:review_status AS constraint_review_status),
                    CAST(:parse_method AS constraint_parse_method),
                    :verified_by, {verified_at}, FALSE,
                    CAST(:phases AS JSONB), NULL, NULL,
                    :actor, :ctx
                )
                ON CONFLICT (constraint_id) DO UPDATE
                    SET payload = EXCLUDED.payload,
                        priority = EXCLUDED.priority,
                        applicable_phases = EXCLUDED.applicable_phases,
                        review_status = EXCLUDED.review_status,
                        updated_at = NOW()
                RETURNING id;
            """), {
                "cid": c["constraint_id"],
                "site": site,
                "cs_uuid": cs_uuid,
                "kind": c["kind"],
                "payload": _json(c["payload"]),
                "priority": c["priority"],
                "cls": c["cls"],
                "sev": c["severity"],
                "auth": c["authority"],
                "conf_e": c["conformance"],
                "weight": c["weight"],
                "confidence": c["confidence"],
                "rationale": c["rationale"],
                "category": c["category"],
                "review_status": c["review_status"],
                "parse_method": c["parse_method"],
                "verified_by": DEFAULT_ACTOR if c["verified"] else None,
                "phases": _json(c["applicable_phases"]),
                "actor": DEFAULT_ACTOR,
                "ctx": ctx,
            }).first()
            constraint_uuid = str(row[0])

            for rds, strategy, inherit in c["scopes"]:
                node_id = rds_to_id.get(rds)
                if not node_id:
                    log.warning("scope skipped: rds %s not found", rds)
                    continue
                # manual 策略需要审核痕迹（INV-17 / ck_cscope_manual_verified）
                manual_verified = strategy == "manual"
                conn.execute(text("""
                    INSERT INTO constraint_scopes (
                        constraint_id, node_id, binding_strategy,
                        inherit_to_descendants, confidence,
                        verified_by_user_id, verified_at,
                        binding_evidence, created_by, mcp_context_id
                    )
                    VALUES (
                        :cid, :nid, :strategy,
                        :inherit, :conf,
                        :vby, :vat,
                        CAST(:evid AS JSONB), :actor, :ctx
                    )
                    ON CONFLICT DO NOTHING;
                """), {
                    "cid": constraint_uuid,
                    "nid": node_id,
                    "strategy": strategy,
                    "inherit": inherit,
                    "conf": 1.00 if manual_verified else 0.85,
                    "vby": DEFAULT_ACTOR if manual_verified else None,
                    "vat": "now" if manual_verified else None,  # placeholder; below
                    "evid": _json({
                        "source": "demo_seed",
                        "rds_code": rds,
                        "strategy": strategy,
                    }),
                    "actor": DEFAULT_ACTOR,
                    "ctx": ctx,
                })

            inserted += 1

        # 修正 manual scopes 的 verified_at —— 上面 placeholder
        conn.execute(text("""
            UPDATE constraint_scopes
               SET verified_at = NOW()
             WHERE binding_strategy = 'manual'
               AND verified_at IS NULL
               AND verified_by_user_id IS NOT NULL;
        """))

        # 审计
        conn.execute(text("""
            INSERT INTO audit_log_actions (
                actor, actor_role, action, target_type, target_id,
                payload, mcp_context_id
            )
            VALUES (
                :actor, 'system', 'seed_load', 'constraint_set', :set_id,
                CAST(:payload AS JSONB), :ctx
            );
        """), {
            "actor": DEFAULT_ACTOR,
            "set_id": DEFAULT_CONSTRAINT_SET_ID,
            "payload": _json({"reason": "demo seed", "constraints": inserted}),
            "ctx": ctx,
        })
    return inserted


def _json(obj: object) -> str:
    import json
    return json.dumps(obj, ensure_ascii=False)


# ─────────────────────────── verify ───────────────────────────

def _print_summary(engine: Engine, *, site: str) -> None:
    with engine.connect() as conn:
        print()
        print("=" * 60)
        print(" Constraint Demo Seed — Verification Summary")
        print("=" * 60)

        rows = conn.execute(text("""
            SELECT aspect, node_kind, COUNT(*) AS n
              FROM hierarchy_nodes
             WHERE deleted_at IS NULL
               AND (site_model_id = :site OR site_model_id IS NULL)
             GROUP BY aspect, node_kind
             ORDER BY aspect, node_kind;
        """), {"site": site}).all()
        print("\n[hierarchy_nodes by aspect × kind]")
        for r in rows:
            print(f"  {r.aspect:<10} {r.node_kind:<22} {r.n}")

        rows = conn.execute(text("""
            SELECT constraint_id, kind, category, review_status, priority,
                   applicable_phases::text AS phases
              FROM process_constraints
             WHERE site_model_id = :site AND deleted_at IS NULL
             ORDER BY constraint_id;
        """), {"site": site}).all()
        print("\n[process_constraints]")
        for r in rows:
            print(f"  {r.constraint_id:<22} {r.kind:<12} {r.category:<10} "
                  f"{r.review_status:<10} prio={r.priority:<3} phases={r.phases}")

        rows = conn.execute(text("""
            SELECT pc.constraint_id, hn.rds_code, hn.aspect,
                   cs.binding_strategy, cs.inherit_to_descendants
              FROM constraint_scopes cs
              JOIN process_constraints pc ON pc.id = cs.constraint_id
              JOIN hierarchy_nodes hn     ON hn.id = cs.node_id
             WHERE pc.site_model_id = :site
               AND cs.deleted_at IS NULL
             ORDER BY pc.constraint_id, hn.rds_code;
        """), {"site": site}).all()
        print("\n[constraint_scopes]")
        for r in rows:
            inh = "↘inherit" if r.inherit_to_descendants else "·"
            print(f"  {r.constraint_id:<22} → {r.rds_code:<28} "
                  f"[{r.aspect:<8}] {r.binding_strategy:<12} {inh}")

        print()
        print("Done. Try it out:")
        print("  -- 查询某工位有效的所有约束 (含继承)")
        print("  SELECT pc.* FROM process_constraints pc")
        print("    JOIN constraint_scopes cs ON cs.constraint_id = pc.id")
        print("    JOIN hierarchy_nodes hn   ON hn.id = cs.node_id")
        print("   WHERE hn.rds_code = '-ENT.AC.SH01.A2.L1.S20'")
        print("     AND pc.applicable_phases ? 'OPERATION';")
        print()


# ─────────────────────────── entrypoint ───────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site-model-id", default=DEFAULT_SITE_MODEL_ID)
    parser.add_argument("--mcp-context-id", default=DEFAULT_MCP_CTX)
    parser.add_argument("--constraint-set-id", default=DEFAULT_CONSTRAINT_SET_ID)
    parser.add_argument("--purge", action="store_true",
                        help="先删除已有 demo 数据再插入 (clean re-seed)")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="[%(levelname)s] %(message)s",
    )

    dsn = _get_dsn()
    engine = create_engine(dsn, future=True)

    if args.purge:
        _purge(engine, site=args.site_model_id, set_id=args.constraint_set_id,
               ctx=args.mcp_context_id)

    _insert_base(engine, site=args.site_model_id,
                 set_id=args.constraint_set_id, ctx=args.mcp_context_id)
    rds_to_id = _insert_hierarchy(engine, site=args.site_model_id,
                                  ctx=args.mcp_context_id)
    n = _insert_constraints(engine, site=args.site_model_id,
                            set_id=args.constraint_set_id,
                            ctx=args.mcp_context_id, rds_to_id=rds_to_id)
    log.info("process_constraints upserted: %d", n)

    _print_summary(engine, site=args.site_model_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
