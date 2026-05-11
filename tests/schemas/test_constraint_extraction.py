"""L0 schema/contract tests for app.schemas.constraint_extraction (T2 / ADR-0010).

Covers Pydantic round-trip, alias handling, enum boundary checks, and
the cross-field validators that mirror DDL CHECKs (so the API surfaces
422 before Postgres throws 23514).
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

import pytest
from app.schemas.constraint_extraction import (
    DocumentChunk,
    ExtractCandidate,
    ExtractedConstraint,
    ExtractedScope,
    ExtractRequest,
    ExtractResponse,
    SourceSpan,
    chunk_content_hash,
)
from pydantic import ValidationError

from shared.models import (
    ConstraintAuthority,
    ConstraintCategory,
    ConstraintClass,
    ConstraintConformance,
    ConstraintKind,
    ConstraintSeverity,
    LifecyclePhase,
)

# ─────────────────────────── helpers ───────────────────────────


def _chunk(text: str = "前序工序 S10 完成后方可开始铆接。") -> DocumentChunk:
    return DocumentChunk(
        document_id="AO-DEMO-001",
        chunk_id="chunk_1",
        page=4,
        char_start=1280,
        char_end=1280 + len(text),
        text=text,
        content_hash=chunk_content_hash(text),
    )


def _scope(node_count: int = 2) -> ExtractedScope:
    return ExtractedScope(
        node_rds_candidates=[f"=PROC.S{i:02d}" for i in range(node_count)],
        asset_guid_candidates=["asset-guid-1"],
    )


def _valid_constraint(**overrides) -> ExtractedConstraint:
    span = "前序工序 S10 完成后方可开始铆接。"
    base = dict(
        kind=ConstraintKind.PREDECESSOR,
        category=ConstraintCategory.SEQUENCE,
        # alias key 'class' is required when populating positionally;
        # we use cls= here (populate_by_name=True).
        cls=ConstraintClass.SOFT,
        severity=ConstraintSeverity.MAJOR,
        authority=ConstraintAuthority.PROJECT,
        conformance=ConstraintConformance.SHOULD,
        rule_expression="precedes(S10, S20)",
        rationale="按 AO 第 4.1 节的工序顺序约束。",
        applicable_phases=[LifecyclePhase.OPERATION],
        scope=_scope(),
        source_document_id="AO-DEMO-001",
        source_span=SourceSpan(page=4, char_start=1280, char_end=1280 + len(span)),
        span_text=span,
        confidence=0.82,
    )
    base.update(overrides)
    return ExtractedConstraint(**base)


# ════════════════════════ DocumentChunk ════════════════════════


def test_chunk_round_trip_and_hash_helper():
    chunk = _chunk()
    serialized = chunk.model_dump_json()
    restored = DocumentChunk.model_validate_json(serialized)
    assert restored == chunk
    assert restored.content_hash == hashlib.sha256(restored.text.encode("utf-8")).hexdigest()


def test_chunk_rejects_mismatched_content_hash():
    with pytest.raises(ValidationError) as exc:
        DocumentChunk(
            document_id="d", chunk_id="c", page=0,
            char_start=0, char_end=4, text="abcd",
            content_hash="0" * 64,
        )
    assert "content_hash" in str(exc.value)


def test_chunk_rejects_inverted_char_window():
    with pytest.raises(ValidationError):
        DocumentChunk(
            document_id="d", chunk_id="c", page=0,
            char_start=10, char_end=10, text="abcd",
            content_hash=chunk_content_hash("abcd"),
        )


def test_chunk_text_max_length_enforced():
    big = "x" * 4001
    with pytest.raises(ValidationError):
        DocumentChunk(
            document_id="d", chunk_id="c", page=0,
            char_start=0, char_end=len(big), text=big,
            content_hash=chunk_content_hash(big),
        )


# ════════════════════════ ExtractCandidate ════════════════════════


def test_candidate_round_trip():
    cand = ExtractCandidate(
        chunk_id="chunk_1", span_start=10, span_end=42,
        span_text="完成后方可开始铆接", reason="顺序触发词命中",
    )
    assert cand.span_end > cand.span_start
    assert ExtractCandidate.model_validate_json(cand.model_dump_json()) == cand


def test_candidate_rejects_inverted_span():
    with pytest.raises(ValidationError):
        ExtractCandidate(
            chunk_id="chunk_1", span_start=42, span_end=10,
            span_text="x", reason="r",
        )


# ════════════════════════ ExtractedConstraint ════════════════════════


def test_constraint_happy_path_and_span_hash():
    c = _valid_constraint()
    assert c.span_hash() == hashlib.sha256(c.span_text.encode("utf-8")).hexdigest()


def test_constraint_alias_class_round_trip():
    """Field alias 'class' must work both directions (populate + serialize)."""
    span = "扭矩 4.5 N·m ±0.3"
    c = ExtractedConstraint.model_validate({
        "kind": "takt",
        "category": "TORQUE",
        "class": "soft",                # alias path
        "severity": "minor",
        "authority": "enterprise",
        "conformance": "SHOULD",
        "rule_expression": "torque(S20) in [4.2, 4.8]",
        "rationale": "扭矩窗口约束。",
        "applicable_phases": ["OPERATION"],
        "scope": {"node_rds_candidates": [], "asset_guid_candidates": []},
        "source_document_id": "AO-DEMO-001",
        "source_span": {"page": 5, "char_start": 0, "char_end": len(span)},
        "span_text": span,
        "confidence": 0.7,
    })
    assert c.cls is ConstraintClass.SOFT
    payload = c.model_dump(by_alias=True)
    assert payload["class"] == "soft"
    assert "cls" not in payload


def test_constraint_confidence_out_of_range_rejected():
    with pytest.raises(ValidationError):
        _valid_constraint(confidence=1.5)


def test_constraint_missing_source_span_rejected():
    span = "扭矩 4.5 N·m"
    with pytest.raises(ValidationError):
        ExtractedConstraint.model_validate({
            "kind": "takt",
            "category": "TORQUE",
            "class": "soft",
            "severity": "minor",
            "authority": "project",
            "conformance": "SHOULD",
            "rule_expression": "x",
            "rationale": "y",
            "applicable_phases": ["OPERATION"],
            "scope": {},
            "source_document_id": "AO-DEMO-001",
            # source_span intentionally omitted
            "span_text": span,
            "confidence": 0.5,
        })


def test_constraint_enum_out_of_range_rejected():
    with pytest.raises(ValidationError):
        _valid_constraint(kind="not_a_kind")  # type: ignore[arg-type]


def test_constraint_predecessor_requires_two_node_candidates():
    with pytest.raises(ValidationError) as exc:
        _valid_constraint(scope=_scope(node_count=1))
    assert "predecessor" in str(exc.value)


def test_constraint_authority_class_coherence_statutory_must_be_hard():
    with pytest.raises(ValidationError):
        _valid_constraint(authority=ConstraintAuthority.STATUTORY, cls=ConstraintClass.SOFT)


def test_constraint_authority_class_coherence_preference_cannot_be_hard():
    with pytest.raises(ValidationError):
        _valid_constraint(
            kind=ConstraintKind.RESOURCE,
            scope=_scope(node_count=0),
            authority=ConstraintAuthority.PREFERENCE,
            cls=ConstraintClass.HARD,
        )


def test_constraint_valid_window_rejects_inverted():
    now = datetime.now(UTC)
    with pytest.raises(ValidationError):
        _valid_constraint(valid_from=now, valid_to=now - timedelta(days=1))


def test_constraint_applicable_phases_min_length():
    with pytest.raises(ValidationError):
        _valid_constraint(applicable_phases=[])


def test_constraint_extra_fields_forbidden():
    with pytest.raises(ValidationError):
        _valid_constraint(unknown_field="oops")


# ════════════════════════ Service envelopes ════════════════════════


def test_extract_request_min_chunks_enforced():
    with pytest.raises(ValidationError):
        ExtractRequest(
            site_model_id="site_seed_001",
            document_id="AO-DEMO-001",
            chunks=[],
            mcp_context_id="ctx-test",
        )


def test_extract_request_max_chunks_enforced():
    too_many = [_chunk(f"text-{i:03d}---{'x'*5}") for i in range(51)]
    with pytest.raises(ValidationError):
        ExtractRequest(
            site_model_id="site_seed_001",
            document_id="AO-DEMO-001",
            chunks=too_many,
            mcp_context_id="ctx-test",
        )


def test_extract_response_round_trip():
    resp = ExtractResponse(
        mcp_context_id="ctx-test",
        candidates_count=5,
        extracted_count=4,
        drafts_written=4,
        evidence_written=4,
        warnings=["span 'XX' 在原文未命中，已丢弃"],
    )
    assert ExtractResponse.model_validate_json(resp.model_dump_json()) == resp
