"""Constraint subsystem invariants — exercise migrations 0019/0020/0021.

Validates the new CHECK / index / enum guarantees introduced for
blueprint Gaps G1, G2, G4. Runs only when POSTGRES_DSN is set
(``db_fixture`` mark, see top-level conftest).

Each test is single-violation so the per-test rollback in
``db_session`` cleanly restores state.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError


pytestmark = pytest.mark.db_fixture


# ─────────────────────────── helpers ───────────────────────────


def _new_set_id() -> str:
    return f"cs_inv_{uuid.uuid4().hex[:8]}"


def _new_constraint_id() -> str:
    return f"PC-INV-{uuid.uuid4().hex[:8]}"


def _new_source_id() -> str:
    # constraint_sources.source_id has CHECK ck_source_id_format = '^src_[a-z0-9_]+$'
    return f"src_inv_{uuid.uuid4().hex[:8]}"


def _ensure_set(db_session, set_id: str) -> str:
    """Insert a minimal constraint_sets row anchored to seed site_seed_001."""
    inserted_id = db_session.execute(
        text(
            """
            INSERT INTO constraint_sets
                (constraint_set_id, version, status, site_model_id)
            VALUES (:csid, 'v1.0', 'draft', 'site_seed_001')
            RETURNING id
            """
        ),
        {"csid": set_id},
    ).scalar_one()
    return str(inserted_id)


# ════════════════════════ G1 — constraint_category ════════════════════════


def test_g1_category_enum_present(db_session):
    """ENUM constraint_category exists with the 10 blueprint values."""
    rows = db_session.execute(
        text(
            "SELECT enumlabel FROM pg_enum e "
            "JOIN pg_type t ON e.enumtypid = t.oid "
            "WHERE t.typname = 'constraint_category' "
            "ORDER BY e.enumsortorder"
        )
    ).scalars().all()
    assert rows == [
        "SPATIAL",
        "SEQUENCE",
        "TORQUE",
        "SAFETY",
        "ENVIRONMENTAL",
        "REGULATORY",
        "QUALITY",
        "RESOURCE",
        "LOGISTICS",
        "OTHER",
    ]


def test_g1_category_default_other_on_insert(db_session):
    """Inserting a process_constraint without category yields OTHER."""
    set_id = _ensure_set(db_session, _new_set_id())
    cid = _new_constraint_id()
    db_session.execute(
        text(
            """
            INSERT INTO process_constraints
                (constraint_id, constraint_set_id, site_model_id,
                 kind, payload, priority, is_active)
            VALUES (:cid, :sid, 'site_seed_001',
                    'exclusion', '{"asset_ids": ["a","b"]}'::jsonb, 50, TRUE)
            """
        ),
        {"cid": cid, "sid": set_id},
    )
    row = db_session.execute(
        text("SELECT category FROM process_constraints WHERE constraint_id = :cid"),
        {"cid": cid},
    ).scalar_one()
    assert row == "OTHER"


def test_g1_category_rejects_unknown_value(db_session):
    """ENUM rejects non-blueprint values."""
    set_id = _ensure_set(db_session, _new_set_id())
    with pytest.raises((IntegrityError, Exception)):
        db_session.execute(
            text(
                """
                INSERT INTO process_constraints
                    (constraint_id, constraint_set_id, site_model_id,
                     kind, payload, category)
                VALUES (:cid, :sid, 'site_seed_001',
                        'exclusion', '{}'::jsonb, 'NUCLEAR')
                """
            ),
            {"cid": _new_constraint_id(), "sid": set_id},
        )


# ════════════════════ G2 — review_status + verified_* ════════════════════


def test_g2_review_status_enum_present(db_session):
    rows = db_session.execute(
        text(
            "SELECT enumlabel FROM pg_enum e "
            "JOIN pg_type t ON e.enumtypid = t.oid "
            "WHERE t.typname = 'constraint_review_status' "
            "ORDER BY e.enumsortorder"
        )
    ).scalars().all()
    assert rows == [
        "draft",
        "under_review",
        "approved",
        "rejected",
        "superseded",
    ]


def test_g2_parse_method_enum_present(db_session):
    rows = db_session.execute(
        text(
            "SELECT enumlabel FROM pg_enum e "
            "JOIN pg_type t ON e.enumtypid = t.oid "
            "WHERE t.typname = 'constraint_parse_method' "
            "ORDER BY e.enumsortorder"
        )
    ).scalars().all()
    assert rows == [
        "MANUAL_UI",
        "EXCEL_IMPORT",
        "MBOM_IMPORT",
        "PMI_ENGINE",
        "LLM_INFERENCE",
    ]


def test_g2_inv8_approved_requires_verified(db_session):
    """INV-8: review_status='approved' requires verified_by_user_id + verified_at."""
    set_id = _ensure_set(db_session, _new_set_id())
    with pytest.raises(IntegrityError):
        db_session.execute(
            text(
                """
                INSERT INTO process_constraints
                    (constraint_id, constraint_set_id, site_model_id,
                     kind, payload, review_status,
                     verified_by_user_id, verified_at)
                VALUES (:cid, :sid, 'site_seed_001',
                        'exclusion', '{}'::jsonb, 'approved',
                        NULL, NULL)
                """
            ),
            {"cid": _new_constraint_id(), "sid": set_id},
        )


def test_g2_inv8_draft_allows_null_verified(db_session):
    """draft / under_review do NOT require verified_*."""
    set_id = _ensure_set(db_session, _new_set_id())
    cid = _new_constraint_id()
    db_session.execute(
        text(
            """
            INSERT INTO process_constraints
                (constraint_id, constraint_set_id, site_model_id,
                 kind, payload, review_status)
            VALUES (:cid, :sid, 'site_seed_001',
                    'exclusion', '{}'::jsonb, 'draft')
            """
        ),
        {"cid": cid, "sid": set_id},
    )
    row = db_session.execute(
        text(
            "SELECT review_status, verified_by_user_id, verified_at, "
            "needs_re_review, parse_method FROM process_constraints "
            "WHERE constraint_id = :cid"
        ),
        {"cid": cid},
    ).one()
    assert row.review_status == "draft"
    assert row.verified_by_user_id is None
    assert row.verified_at is None
    assert row.needs_re_review is False
    assert row.parse_method == "MANUAL_UI"


# ════════════════════ G4 — constraint_sources hash + classification ════════════════════


def test_g4_hash_format_rejects_non_hex(db_session):
    sid = _new_source_id()
    with pytest.raises(IntegrityError):
        db_session.execute(
            text(
                """
                INSERT INTO constraint_sources
                    (source_id, title, authority, hash_sha256)
                VALUES (:sid, 'bad hash', 'enterprise', 'NOT_A_VALID_HASH')
                """
            ),
            {"sid": sid},
        )


def test_g4_hash_partial_unique_dedup(db_session):
    """Two non-NULL identical hashes -> 23505."""
    digest = "a" * 64
    sid_a = _new_source_id()
    sid_b = _new_source_id()
    db_session.execute(
        text(
            """
            INSERT INTO constraint_sources
                (source_id, title, authority, hash_sha256)
            VALUES (:sid, 'first upload', 'enterprise', :h)
            """
        ),
        {"sid": sid_a, "h": digest},
    )
    with pytest.raises(IntegrityError):
        db_session.execute(
            text(
                """
                INSERT INTO constraint_sources
                    (source_id, title, authority, hash_sha256)
                VALUES (:sid, 'duplicate upload', 'enterprise', :h)
                """
            ),
            {"sid": sid_b, "h": digest},
        )


def test_g4_classification_check_rejects_unknown(db_session):
    sid = _new_source_id()
    with pytest.raises(IntegrityError):
        db_session.execute(
            text(
                """
                INSERT INTO constraint_sources
                    (source_id, title, authority, classification)
                VALUES (:sid, 'wrong class', 'enterprise', 'TOP_SECRET')
                """
            ),
            {"sid": sid},
        )


def test_g4_classification_accepts_blueprint_values(db_session):
    """All four blueprint values must be accepted."""
    for cls in ("PUBLIC", "INTERNAL", "CONFIDENTIAL", "SECRET"):
        sid = _new_source_id()
        db_session.execute(
            text(
                """
                INSERT INTO constraint_sources
                    (source_id, title, authority, classification)
                VALUES (:sid, 'ok', 'enterprise', :c)
                """
            ),
            {"sid": sid, "c": cls},
        )
        row = db_session.execute(
            text(
                "SELECT classification FROM constraint_sources WHERE source_id = :sid"
            ),
            {"sid": sid},
        ).scalar_one()
        assert row == cls
