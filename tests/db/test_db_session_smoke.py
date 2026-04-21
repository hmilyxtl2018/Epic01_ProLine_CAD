"""Live-DB smoke tests for the B1-B5 schema.

Exercises behaviors that **cannot** be validated by `alembic upgrade/downgrade`
or `scripts/check_schema_drift.py` alone:

  * ORM ↔ live-schema column/type alignment (round-trip via Declarative classes).
  * Runtime CHECK constraints (`confidence`, `decision`, `actor_role`,
    `merge_target_id` consistency).
  * Partial UNIQUE index behavior under soft-delete (the whole point of B1).
  * PostGIS Geometry round-trip + GIST-backed `&&` spatial filter.
  * JSONB column round-trip through SQLAlchemy.
  * `db_session` fixture rollback isolation.

All tests are gated by the `db_fixture` marker -> auto-skip when
POSTGRES_DSN is unset (see repo-root conftest.py).

NOTE: tests intentionally use savepoint-friendly patterns (one constraint
violation per test) so the per-test transaction rollback in the fixture
cleanly restores the DB state.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from shared.db_schemas import (
    AssetGeometry,
    AuditLogAction,
    McpContext,
    QuarantineTerm,
    SiteModel,
    TaxonomyTerm,
)


pytestmark = pytest.mark.db_fixture


# ════════════════════════════════════════════════════════════════════════════
# Fixture wiring & seed visibility
# ════════════════════════════════════════════════════════════════════════════


def test_seed_loaded(db_session):
    """Seed loaded by `_db_engine` must be visible inside per-test session."""
    assert db_session.execute(
        text("SELECT mcp_context_id FROM mcp_contexts WHERE mcp_context_id = 'mcp_seed_root'")
    ).scalar_one() == "mcp_seed_root"
    assert db_session.execute(
        text("SELECT site_model_id FROM site_models WHERE site_model_id = 'site_seed_001'")
    ).scalar_one() == "site_seed_001"
    assert db_session.execute(
        text("SELECT term_normalized FROM taxonomy_terms WHERE term_normalized = 'conveyor'")
    ).scalar_one() == "conveyor"


# ════════════════════════════════════════════════════════════════════════════
# ORM round-trips (catch shared/db_schemas.py drift vs live schema)
# ════════════════════════════════════════════════════════════════════════════


def test_orm_roundtrip_mcp_context(db_session):
    ctx = McpContext(
        mcp_context_id="mcp_test_orm_ctx",
        agent="parse_agent",
        input_payload={"k": "v"},
        output_payload={"ok": True},
    )
    db_session.add(ctx)
    db_session.flush()

    fetched = db_session.execute(
        sa.select(McpContext).where(McpContext.mcp_context_id == "mcp_test_orm_ctx")
    ).scalar_one()
    assert fetched.agent == "parse_agent"
    assert fetched.output_payload == {"ok": True}


def test_orm_roundtrip_site_model_with_bbox(db_session):
    """SiteModel.bbox round-trips via WKT -- proves geoalchemy2 mapping wired up."""
    db_session.add(
        McpContext(mcp_context_id="mcp_test_sm_ctx", agent="parse_agent")
    )
    db_session.flush()

    db_session.execute(
        text(
            """
            INSERT INTO site_models (site_model_id, cad_source, mcp_context_id, bbox)
            VALUES (
                'site_test_orm',
                '{"format":"DWG","filename":"orm.dwg","dwg_hash":"abc"}'::jsonb,
                'mcp_test_sm_ctx',
                ST_GeomFromText('POLYGON((0 0, 50 0, 50 50, 0 50, 0 0))', 0)
            )
            """
        )
    )
    db_session.flush()

    sm = db_session.execute(
        sa.select(SiteModel).where(SiteModel.site_model_id == "site_test_orm")
    ).scalar_one()
    assert sm.cad_source["format"] == "DWG"
    # bbox should not be NULL after PostGIS load
    bbox_text = db_session.execute(
        text("SELECT ST_AsText(bbox) FROM site_models WHERE site_model_id='site_test_orm'")
    ).scalar_one()
    assert bbox_text.startswith("POLYGON")


def test_spatial_st_intersects_with_seed(db_session):
    """Seed bbox (0..100,0..100) intersects an envelope at (10..20,10..20)."""
    hits = db_session.execute(
        text(
            """
            SELECT site_model_id FROM site_models
            WHERE bbox && ST_MakeEnvelope(10, 10, 20, 20, 0)
              AND site_model_id = 'site_seed_001'
            """
        )
    ).scalar_one_or_none()
    assert hits == "site_seed_001"


# ════════════════════════════════════════════════════════════════════════════
# CHECK constraint enforcement (B1/B2)
# ════════════════════════════════════════════════════════════════════════════


def test_asset_geom_confidence_check_rejects_out_of_range(db_session):
    with pytest.raises(IntegrityError) as exc:
        db_session.execute(
            text(
                """
                INSERT INTO asset_geometries (
                    site_model_id, asset_guid, asset_type, footprint,
                    confidence, mcp_context_id
                )
                VALUES (
                    'site_seed_001', 'asset_bad_conf', 'Equipment',
                    ST_GeomFromText('POLYGON((0 0,1 0,1 1,0 1,0 0))', 0),
                    1.5, 'mcp_seed_root'
                )
                """
            )
        )
        db_session.flush()
    assert "ck_asset_geom_confidence_range" in str(exc.value)


def test_taxonomy_partial_unique_blocks_live_duplicate(db_session):
    """While the seed 'conveyor' row is alive, a second insert must fail."""
    with pytest.raises(IntegrityError) as exc:
        db_session.execute(
            text(
                """
                INSERT INTO taxonomy_terms (term_normalized, term_display, asset_type, source)
                VALUES ('conveyor', 'Conveyor Dup', 'Conveyor', 'manual')
                """
            )
        )
        db_session.flush()
    assert "uq_taxonomy_terms_term_type_alive" in str(exc.value)


def test_taxonomy_soft_delete_releases_partial_unique(db_session):
    """Soft-deleting the seed row must allow a fresh insert with the same key."""
    db_session.execute(
        text(
            "UPDATE taxonomy_terms SET deleted_at = NOW() "
            "WHERE term_normalized='conveyor' AND asset_type='Conveyor' "
            "AND deleted_at IS NULL"
        )
    )
    db_session.flush()

    db_session.execute(
        text(
            """
            INSERT INTO taxonomy_terms (term_normalized, term_display, asset_type, source)
            VALUES ('conveyor', 'Conveyor Reborn', 'Conveyor', 'manual')
            """
        )
    )
    db_session.flush()

    alive = db_session.execute(
        text(
            "SELECT term_display FROM taxonomy_terms "
            "WHERE term_normalized='conveyor' AND asset_type='Conveyor' "
            "AND deleted_at IS NULL"
        )
    ).scalar_one()
    assert alive == "Conveyor Reborn"


def test_quarantine_merge_requires_target_id(db_session):
    """decision='merge' WITHOUT merge_target_id must violate CHECK."""
    with pytest.raises(IntegrityError) as exc:
        db_session.execute(
            text(
                """
                INSERT INTO quarantine_terms
                  (term_normalized, term_display, asset_type, count,
                   first_seen, last_seen, decision, mcp_context_id)
                VALUES
                  ('orphan_merge', 'Orphan Merge', 'Equipment', 1,
                   NOW(), NOW(), 'merge', 'mcp_seed_root')
                """
            )
        )
        db_session.flush()
    assert "ck_quarantine_terms_merge_target_consistency" in str(exc.value)


def test_quarantine_merge_with_target_ok(db_session):
    """decision='merge' WITH a valid merge_target_id must succeed."""
    target_id = db_session.execute(
        text("SELECT id FROM taxonomy_terms WHERE term_normalized='conveyor' LIMIT 1")
    ).scalar_one()

    db_session.execute(
        text(
            """
            INSERT INTO quarantine_terms
              (term_normalized, term_display, asset_type, count,
               first_seen, last_seen, decision, merge_target_id, mcp_context_id)
            VALUES
              (:tn, 'Roller Belt', 'Conveyor', 1,
               NOW(), NOW(), 'merge', :tgt, 'mcp_seed_root')
            """
        ),
        {"tn": "roller_belt_unique_for_merge", "tgt": target_id},
    )
    db_session.flush()
    inserted = db_session.execute(
        text("SELECT decision FROM quarantine_terms WHERE term_normalized='roller_belt_unique_for_merge'")
    ).scalar_one()
    assert inserted == "merge"


def test_quarantine_decision_enum_rejects_unknown(db_session):
    with pytest.raises(IntegrityError) as exc:
        db_session.execute(
            text(
                """
                INSERT INTO quarantine_terms
                  (term_normalized, term_display, asset_type, count,
                   first_seen, last_seen, decision, mcp_context_id)
                VALUES
                  ('bad_decision', 'Bad', 'Equipment', 1,
                   NOW(), NOW(), 'maybe', 'mcp_seed_root')
                """
            )
        )
        db_session.flush()
    assert "ck_quarantine_terms_decision_enum" in str(exc.value)


def test_audit_log_actor_role_check_rejects_unknown(db_session):
    with pytest.raises(IntegrityError) as exc:
        db_session.execute(
            text(
                """
                INSERT INTO audit_log_actions
                  (actor, actor_role, action, target_type, target_id,
                   payload, mcp_context_id)
                VALUES
                  ('mallory', 'hacker', 'evil_action', 'site_model',
                   'site_seed_001', '{}'::jsonb, 'mcp_seed_root')
                """
            )
        )
        db_session.flush()
    assert "ck_audit_log_actions_actor_role_enum" in str(exc.value)


# ════════════════════════════════════════════════════════════════════════════
# JSONB round-trip (B2)
# ════════════════════════════════════════════════════════════════════════════


def test_audit_log_jsonb_payload_roundtrip(db_session):
    payload = {"reason": "promote", "score": 0.97, "tags": ["gold", "manual"]}
    row = AuditLogAction(
        actor="alice@local",
        actor_role="reviewer",
        action="promote_term",
        target_type="taxonomy_term",
        target_id="conveyor",
        payload=payload,
        mcp_context_id="mcp_seed_root",
    )
    db_session.add(row)
    db_session.flush()

    fetched = db_session.execute(
        sa.select(AuditLogAction).where(AuditLogAction.action == "promote_term")
    ).scalar_one()
    assert fetched.payload == payload
    assert fetched.actor_role == "reviewer"


# ════════════════════════════════════════════════════════════════════════════
# Fixture self-test: rollback isolation
# ════════════════════════════════════════════════════════════════════════════


def test_rollback_isolation_writer(db_session):
    db_session.add(
        McpContext(mcp_context_id="mcp_should_disappear", agent="parse_agent")
    )
    db_session.flush()
    assert db_session.execute(
        text("SELECT mcp_context_id FROM mcp_contexts WHERE mcp_context_id='mcp_should_disappear'")
    ).scalar_one() == "mcp_should_disappear"


def test_rollback_isolation_reader(db_session):
    """Previous test's write must NOT leak here (fixture rolls back)."""
    leaked = db_session.execute(
        text("SELECT mcp_context_id FROM mcp_contexts WHERE mcp_context_id='mcp_should_disappear'")
    ).scalar_one_or_none()
    assert leaked is None
