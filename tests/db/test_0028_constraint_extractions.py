"""Migration 0028 invariants — constraint_extractions table (ADR-0010).

Validates table existence, indexes, CHECK constraints, FK cascade, and the
unique-per-(constraint, span_hash) guarantee. Skipped without POSTGRES_DSN
(see top-level conftest).
"""

from __future__ import annotations

import hashlib
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError


pytestmark = pytest.mark.db_fixture


# ─────────────────────────── helpers ───────────────────────────


def _new_set_id() -> str:
    return f"cs_ce_{uuid.uuid4().hex[:8]}"


def _new_constraint_id() -> str:
    return f"PC-CE-{uuid.uuid4().hex[:8]}"


def _ensure_set(db_session, set_id: str) -> str:
    return str(
        db_session.execute(
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
    )


def _ensure_constraint(db_session, set_uuid: str, cid: str) -> str:
    """Insert a draft process_constraint and return its UUID id."""
    return str(
        db_session.execute(
            text(
                """
                INSERT INTO process_constraints
                    (constraint_id, constraint_set_id, site_model_id,
                     kind, payload, review_status)
                VALUES (:cid, :sid, 'site_seed_001',
                        'exclusion', '{}'::jsonb, 'draft')
                RETURNING id
                """
            ),
            {"cid": cid, "sid": set_uuid},
        ).scalar_one()
    )


def _hash(text_str: str) -> str:
    return hashlib.sha256(text_str.encode("utf-8")).hexdigest()


def _insert_extraction(db_session, **kwargs):
    """Insert one row; defaults are an LLM extraction with required fields."""
    span_text = kwargs.pop("span_text", "前序工序 S10 完成后方可开始铆接")
    defaults = {
        "document_id": "AO-DEMO-001",
        "chunk_id": "chunk_1",
        "page": 4,
        "char_start": 1280,
        "char_end": 1402,
        "span_text": span_text,
        "span_hash": _hash(span_text),
        "extractor_kind": "llm",
        "llm_model": "gpt-4o-mini",
        "prompt_version": "stage_b_v1",
        "extraction_run_id": "run_test_001",
        "extraction_confidence": 0.85,
        "extraction_payload": "{}",
    }
    defaults.update(kwargs)
    return db_session.execute(
        text(
            """
            INSERT INTO constraint_extractions
                (process_constraint_id, document_id, chunk_id, page,
                 char_start, char_end, span_text, span_hash, extractor_kind,
                 llm_model, prompt_version, extraction_run_id,
                 extraction_confidence, extraction_payload)
            VALUES
                (:process_constraint_id, :document_id, :chunk_id, :page,
                 :char_start, :char_end, :span_text, :span_hash, :extractor_kind,
                 :llm_model, :prompt_version, :extraction_run_id,
                 :extraction_confidence, CAST(:extraction_payload AS jsonb))
            RETURNING id
            """
        ),
        defaults,
    ).scalar_one()


# ════════════════════════ schema sanity ════════════════════════


def test_0028_table_exists(db_session):
    row = db_session.execute(
        text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_name = 'constraint_extractions'"
        )
    ).scalar_one_or_none()
    assert row == 1


def test_0028_expected_indexes_present(db_session):
    names = set(
        db_session.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE tablename = 'constraint_extractions'"
            )
        ).scalars().all()
    )
    assert {
        "idx_ce_constraint",
        "idx_ce_document",
        "idx_ce_run",
        "uq_ce_hash_per_constraint",
    }.issubset(names)


def test_0028_expected_check_constraints_present(db_session):
    names = set(
        db_session.execute(
            text(
                "SELECT conname FROM pg_constraint c "
                "JOIN pg_class t ON c.conrelid = t.oid "
                "WHERE t.relname = 'constraint_extractions' AND c.contype = 'c'"
            )
        ).scalars().all()
    )
    expected = {
        "ck_ce_extractor_kind",
        "ck_ce_span_text_len",
        "ck_ce_span_hash_format",
        "ck_ce_page_nonneg",
        "ck_ce_char_range",
        "ck_ce_char_end_after_start",
        "ck_ce_confidence_range",
        "ck_ce_payload_object",
        "ck_ce_llm_metadata",
    }
    missing = expected - names
    assert not missing, f"missing CHECK constraints: {missing}"


# ════════════════════════ happy path ════════════════════════


def test_0028_llm_extraction_round_trip(db_session):
    set_uuid = _ensure_set(db_session, _new_set_id())
    pc_uuid = _ensure_constraint(db_session, set_uuid, _new_constraint_id())
    ext_id = _insert_extraction(db_session, process_constraint_id=pc_uuid)
    assert uuid.UUID(str(ext_id))

    row = db_session.execute(
        text(
            "SELECT extractor_kind, llm_model, prompt_version, span_hash, "
            "extraction_confidence "
            "FROM constraint_extractions WHERE id = :eid"
        ),
        {"eid": str(ext_id)},
    ).one()
    assert row.extractor_kind == "llm"
    assert row.llm_model == "gpt-4o-mini"
    assert row.prompt_version == "stage_b_v1"
    assert len(row.span_hash) == 64
    assert 0.0 <= float(row.extraction_confidence) <= 1.0


# ════════════════════════ CHECK guards ════════════════════════


def test_0028_llm_kind_requires_model_and_prompt(db_session):
    """ck_ce_llm_metadata: extractor_kind='llm' must carry llm_model + prompt_version."""
    set_uuid = _ensure_set(db_session, _new_set_id())
    pc_uuid = _ensure_constraint(db_session, set_uuid, _new_constraint_id())
    with pytest.raises(IntegrityError):
        _insert_extraction(
            db_session,
            process_constraint_id=pc_uuid,
            extractor_kind="llm",
            llm_model=None,
            prompt_version=None,
        )


def test_0028_regex_kind_does_not_require_llm_metadata(db_session):
    set_uuid = _ensure_set(db_session, _new_set_id())
    pc_uuid = _ensure_constraint(db_session, set_uuid, _new_constraint_id())
    ext_id = _insert_extraction(
        db_session,
        process_constraint_id=pc_uuid,
        extractor_kind="regex",
        llm_model=None,
        prompt_version=None,
    )
    assert ext_id is not None


def test_0028_span_hash_format_enforced(db_session):
    set_uuid = _ensure_set(db_session, _new_set_id())
    pc_uuid = _ensure_constraint(db_session, set_uuid, _new_constraint_id())
    with pytest.raises(IntegrityError):
        _insert_extraction(
            db_session,
            process_constraint_id=pc_uuid,
            span_hash="not-a-sha256",
        )


def test_0028_span_text_length_bounds(db_session):
    set_uuid = _ensure_set(db_session, _new_set_id())
    pc_uuid = _ensure_constraint(db_session, set_uuid, _new_constraint_id())
    long_text = "x" * 1001
    with pytest.raises(IntegrityError):
        _insert_extraction(
            db_session,
            process_constraint_id=pc_uuid,
            span_text=long_text,
            span_hash=_hash(long_text),
        )


def test_0028_char_end_must_exceed_start(db_session):
    set_uuid = _ensure_set(db_session, _new_set_id())
    pc_uuid = _ensure_constraint(db_session, set_uuid, _new_constraint_id())
    with pytest.raises(IntegrityError):
        _insert_extraction(
            db_session,
            process_constraint_id=pc_uuid,
            char_start=100,
            char_end=50,
        )


def test_0028_extractor_kind_enum_check(db_session):
    set_uuid = _ensure_set(db_session, _new_set_id())
    pc_uuid = _ensure_constraint(db_session, set_uuid, _new_constraint_id())
    with pytest.raises(IntegrityError):
        _insert_extraction(
            db_session,
            process_constraint_id=pc_uuid,
            extractor_kind="not_a_real_kind",
        )


def test_0028_confidence_out_of_range_rejected(db_session):
    set_uuid = _ensure_set(db_session, _new_set_id())
    pc_uuid = _ensure_constraint(db_session, set_uuid, _new_constraint_id())
    with pytest.raises(IntegrityError):
        _insert_extraction(
            db_session,
            process_constraint_id=pc_uuid,
            extraction_confidence=1.5,
        )


def test_0028_payload_must_be_object(db_session):
    set_uuid = _ensure_set(db_session, _new_set_id())
    pc_uuid = _ensure_constraint(db_session, set_uuid, _new_constraint_id())
    with pytest.raises(IntegrityError):
        _insert_extraction(
            db_session,
            process_constraint_id=pc_uuid,
            extraction_payload="[1, 2, 3]",
        )


# ════════════════════════ uniqueness ════════════════════════


def test_0028_unique_span_hash_per_constraint(db_session):
    """uq_ce_hash_per_constraint blocks duplicate (constraint, span_hash)."""
    set_uuid = _ensure_set(db_session, _new_set_id())
    pc_uuid = _ensure_constraint(db_session, set_uuid, _new_constraint_id())
    span = "重复抽取防伪检验文本"
    h = _hash(span)
    _insert_extraction(
        db_session, process_constraint_id=pc_uuid, span_text=span, span_hash=h
    )
    with pytest.raises(IntegrityError):
        _insert_extraction(
            db_session, process_constraint_id=pc_uuid, span_text=span, span_hash=h
        )


def test_0028_same_span_hash_allowed_across_constraints(db_session):
    """Same span content can be evidence for multiple distinct constraints."""
    set_uuid = _ensure_set(db_session, _new_set_id())
    pc_a = _ensure_constraint(db_session, set_uuid, _new_constraint_id())
    pc_b = _ensure_constraint(db_session, set_uuid, _new_constraint_id())
    span = "标准 HB/Q 7.2 第 4.1 节"
    h = _hash(span)
    _insert_extraction(
        db_session, process_constraint_id=pc_a, span_text=span, span_hash=h
    )
    _insert_extraction(
        db_session, process_constraint_id=pc_b, span_text=span, span_hash=h
    )
    n = db_session.execute(
        text(
            "SELECT count(*) FROM constraint_extractions WHERE span_hash = :h"
        ),
        {"h": h},
    ).scalar_one()
    assert n == 2


# ════════════════════════ FK cascade ════════════════════════


def test_0028_fk_cascade_on_constraint_delete(db_session):
    set_uuid = _ensure_set(db_session, _new_set_id())
    pc_uuid = _ensure_constraint(db_session, set_uuid, _new_constraint_id())
    _insert_extraction(db_session, process_constraint_id=pc_uuid)
    _insert_extraction(
        db_session,
        process_constraint_id=pc_uuid,
        span_text="另一条证据",
        span_hash=_hash("另一条证据"),
    )

    db_session.execute(
        text("DELETE FROM process_constraints WHERE id = :pc"), {"pc": pc_uuid}
    )
    n = db_session.execute(
        text(
            "SELECT count(*) FROM constraint_extractions "
            "WHERE process_constraint_id = :pc"
        ),
        {"pc": pc_uuid},
    ).scalar_one()
    assert n == 0
