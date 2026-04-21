"""H5 Response Validator 单元测试。"""
from __future__ import annotations

import pytest

from agents.parse_agent.h4_llm_classifier import (
    ClassificationResponse,
    ClassifyContext,
)
from agents.parse_agent.h5_validator import (
    ValidationResult,
    apply_h5,
    validate,
)


# ---------- helpers ----------

def _ctx(block="", layer="", labels=None) -> ClassifyContext:
    return ClassifyContext(block_name=block, layer=layer, sample_labels=labels or [])


def _resp(
    type="Equipment", confidence=0.8, evidence=None, sub_type=None,
) -> ClassificationResponse:
    return ClassificationResponse(
        type=type,
        sub_type=sub_type,
        confidence=confidence,
        evidence_keywords=list(evidence) if evidence is not None else [],
    )


# ════════════════ R1: type 枚举 ════════════════

def test_r1_invalid_type_rejected():
    r = validate(_resp(type="Machine"), _ctx(block="washing"))
    assert not r.ok and r.rule == "R1_type_enum"


def test_r1_all_valid_types_pass_when_grounded():
    for t in ["Equipment", "Conveyor", "LiftingPoint", "Zone", "Annotation", "Other"]:
        r = validate(_resp(type=t, evidence=["foo"]), _ctx(block="foo_bar"))
        assert r.ok, f"type={t} should pass, got {r}"


# ════════════════ R2: confidence 范围 ════════════════

@pytest.mark.parametrize("c", [-0.01, 1.01, 1.5, -1.0])
def test_r2_confidence_out_of_range(c):
    r = validate(_resp(confidence=c, evidence=["x"]), _ctx(block="x"))
    assert not r.ok and r.rule == "R2_confidence_range"


@pytest.mark.parametrize("c", [0.0, 0.5, 1.0])
def test_r2_confidence_boundary_ok(c):
    r = validate(_resp(confidence=c, evidence=["foo"]), _ctx(block="foo"))
    assert r.ok


# ════════════════ R3: evidence ⊆ input ════════════════

def test_r3_keyword_exact_in_block_name():
    r = validate(
        _resp(evidence=["honing"]),
        _ctx(block="honing_machine_op170"),
    )
    assert r.ok


def test_r3_keyword_case_insensitive():
    r = validate(
        _resp(evidence=["HONING"]),
        _ctx(block="honing_machine"),
    )
    assert r.ok


def test_r3_keyword_chinese_substring():
    r = validate(
        _resp(evidence=["珩磨"]),
        _ctx(block="珩磨机_OP170"),
    )
    assert r.ok


def test_r3_keyword_in_layer():
    r = validate(
        _resp(evidence=["conveyor"]),
        _ctx(block="A$C123", layer="STEP_1_Conveyor"),
    )
    assert r.ok


def test_r3_keyword_in_sample_labels():
    r = validate(
        _resp(evidence=["leak"]),
        _ctx(block="abc", labels=["LEAK_TEST_OP200", "fixture"]),
    )
    assert r.ok


def test_r3_keyword_hallucinated_rejected():
    r = validate(
        _resp(evidence=["robot"]),
        _ctx(block="conveyor_2m", layer="STEP_1"),
    )
    assert not r.ok and r.rule == "R3_evidence_grounded"
    assert "robot" in r.detail


def test_r3_partial_hallucination_rejected():
    """所有 keyword 都必须落地; 一个 hallucination 即失败。"""
    r = validate(
        _resp(evidence=["honing", "fictional_term"]),
        _ctx(block="honing_machine"),
    )
    assert not r.ok and r.rule == "R3_evidence_grounded"


def test_r3_token_split_match():
    """连字符分隔的 token 应被切开后匹配。"""
    r = validate(
        _resp(evidence=["KBK"]),
        _ctx(block="KBK-缸体线-OP100"),
    )
    assert r.ok


def test_r3_cross_token_substring_match():
    """跨多个 token 的子串也算落地 (例如 'k-st' 匹配 'k-st-2100x1400')。"""
    r = validate(
        _resp(evidence=["k-st"]),
        _ctx(block="K-ST-2100x1400"),
    )
    assert r.ok


# ════════════════ R4: 非 Unknown 必须有证据 ════════════════

def test_r4_equipment_without_evidence_rejected():
    r = validate(_resp(type="Equipment", evidence=[]), _ctx(block="x"))
    assert not r.ok and r.rule == "R4_evidence_required"


def test_unknown_without_evidence_passes():
    """Unknown 是合法弃权信号, 不要求 evidence。"""
    r = validate(
        _resp(type="Unknown", confidence=0.0, evidence=[]),
        _ctx(block="???"),
    )
    assert r.ok


def test_unknown_with_evidence_also_passes():
    r = validate(
        _resp(type="Unknown", confidence=0.0, evidence=["whatever"]),
        _ctx(block="x"),
    )
    assert r.ok  # Unknown 短路, 不查 R3


# ════════════════ 边界: 输入为空 ════════════════

def test_empty_input_with_evidence_rejected():
    r = validate(
        _resp(evidence=["foo"]),
        _ctx(),  # 全空
    )
    assert not r.ok and r.rule == "R3_evidence_grounded"


def test_empty_input_unknown_passes():
    r = validate(_resp(type="Unknown", confidence=0.0, evidence=[]), _ctx())
    assert r.ok


# ════════════════ apply_h5: 回退路径 ════════════════

def test_apply_h5_pass_returns_llm_response():
    llm = _resp(type="Equipment", confidence=0.9, evidence=["honing"])
    h3 = _resp(type="Other", confidence=0.1, evidence=[])
    final, result = apply_h5(llm, _ctx(block="honing_machine"), h3)
    assert result.ok
    assert final is llm  # 直通


def test_apply_h5_fail_returns_h3_with_rejection_marker():
    llm = _resp(type="Equipment", confidence=0.9, evidence=["robot"])  # hallucinated
    h3 = ClassificationResponse(
        type="Other", sub_type="rule_other", confidence=0.2,
        evidence_keywords=["fallback_marker"], classifier_kind="rule_h3",
    )
    final, result = apply_h5(llm, _ctx(block="conveyor"), h3)
    assert not result.ok
    assert final.type == "Other"
    assert final.sub_type == "rule_other"
    assert final.confidence == 0.2
    assert final.evidence_keywords == ["fallback_marker"]
    assert final.classifier_kind == "rule_h3_after_h5_reject"
    assert final.error and "h5_rejected:R3_evidence_grounded" in final.error


def test_apply_h5_invalid_type_falls_back():
    llm = _resp(type="GarbageType", evidence=["x"])
    h3 = _resp(type="Conveyor", confidence=0.7, evidence=["belt"])
    final, result = apply_h5(llm, _ctx(block="belt"), h3)
    assert not result.ok and result.rule == "R1_type_enum"
    assert final.type == "Conveyor"
    assert "h5_rejected:R1_type_enum" in (final.error or "")


def test_validation_result_helpers():
    p = ValidationResult.pass_()
    assert p.ok and p.rule == "" and p.detail == ""
    f = ValidationResult.fail("R1_type_enum", "bad")
    assert not f.ok and f.rule == "R1_type_enum" and f.detail == "bad"
