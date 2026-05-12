"""Stage A/B JSON Schema 与 thresholds 的 L0 测试（T4-prep）。

覆盖：

1. 两份 schema 文件能加载成 dict 且 ``$id`` 正确。
2. ``ExtractedConstraint.model_json_schema()`` 与 stage_b_v1 schema 在
   关键字段（必填项 + 枚举值）上保持一致 —— 防止 Pydantic 与 JSON Schema
   悄悄漂移。
3. Stage A/B schema 自身能通过 jsonschema 元校验。
4. ``current_thresholds()`` 默认值 + ENV 旋钮 + 越界回退行为正确。
5. 默认 thresholds 与 docs/kg_execution_tasks_v1.md §T4.2 锁定值一致。
"""

from __future__ import annotations

import json

import jsonschema
import pytest
from app.schemas.constraint_extraction import (
    ExtractCandidate,
    ExtractedConstraint,
)
from app.services.constraint_extractor import (
    STAGE_A_SCHEMA,
    STAGE_A_VERSION,
    STAGE_B_SCHEMA,
    STAGE_B_VERSION,
    load_schema,
)
from app.services.constraint_extractor.thresholds import (
    DEFAULT_BATCH_MIN_MEAN_CONFIDENCE,
    DEFAULT_BATCH_MIN_YIELD,
    DEFAULT_CONFIDENCE_HIGH,
    DEFAULT_CONFIDENCE_LOW,
    DEFAULT_CONFIDENCE_REJECT,
    ExtractorThresholds,
    current_thresholds,
)
from jsonschema import Draft202012Validator

# ─────────────────────────────────────────────────────────────────────────────
# 1. Schema 文件本身合法
# ─────────────────────────────────────────────────────────────────────────────


def test_stage_a_schema_id_and_envelope() -> None:
    assert STAGE_A_SCHEMA["$id"] == "proline://extractor/stage_a_v1/output"
    assert STAGE_A_SCHEMA["type"] == "object"
    assert STAGE_A_SCHEMA["required"] == ["candidates"]
    assert STAGE_A_SCHEMA["additionalProperties"] is False


def test_stage_b_schema_is_oneof_with_two_forms() -> None:
    assert STAGE_B_SCHEMA["$id"] == "proline://extractor/stage_b_v1/output"
    assert "oneOf" in STAGE_B_SCHEMA
    assert len(STAGE_B_SCHEMA["oneOf"]) == 2
    skip_form = next(f for f in STAGE_B_SCHEMA["oneOf"] if "skip" in f.get("properties", {}))
    full_form = next(f for f in STAGE_B_SCHEMA["oneOf"] if "kind" in f.get("properties", {}))
    assert skip_form["properties"]["skip"]["const"] is True
    assert full_form["additionalProperties"] is False


def test_load_schema_rejects_unknown_version() -> None:
    with pytest.raises(ValueError, match="unknown schema version"):
        load_schema("stage_z_v99")


@pytest.mark.parametrize("version", [STAGE_A_VERSION, STAGE_B_VERSION])
def test_schema_passes_jsonschema_meta_validation(version: str) -> None:
    """两份 schema 必须自身合法 —— jsonschema Draft 2020-12 meta 校验。"""
    schema = load_schema(version)
    Draft202012Validator.check_schema(schema)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Pydantic 与 stage_b_v1 schema 一致性（关键字段）
# ─────────────────────────────────────────────────────────────────────────────


def _stage_b_full_form() -> dict:
    return next(f for f in STAGE_B_SCHEMA["oneOf"] if "kind" in f.get("properties", {}))


def test_stage_b_schema_required_matches_pydantic() -> None:
    """JSON Schema required 必须与 Pydantic 必填字段一致。

    Pydantic 用 ``alias='class'``，所以 JSON 侧字段名是 ``class``。
    """
    pyd_schema = ExtractedConstraint.model_json_schema(by_alias=True)
    pyd_required = set(pyd_schema["required"])
    json_required = set(_stage_b_full_form()["required"])
    assert pyd_required == json_required, (
        f"required drift between Pydantic and stage_b_v1.schema.json: "
        f"only-in-pydantic={pyd_required - json_required} "
        f"only-in-json={json_required - pyd_required}"
    )


@pytest.mark.parametrize(
    "field, expected_values",
    [
        ("kind", {"predecessor", "resource", "takt", "exclusion"}),
        ("class", {"hard", "soft", "preference"}),
        ("severity", {"critical", "major", "minor"}),
        ("authority", {"statutory", "industry", "enterprise", "project", "heuristic", "preference"}),
        ("conformance", {"MUST", "SHOULD", "MAY"}),
    ],
)
def test_stage_b_schema_enum_values(field: str, expected_values: set[str]) -> None:
    """JSON Schema 枚举与代码侧枚举闭集对齐。"""
    full_form = _stage_b_full_form()
    actual = set(full_form["properties"][field]["enum"])
    assert actual == expected_values


# ─────────────────────────────────────────────────────────────────────────────
# 3. Stage A schema 实际能拒收坏数据 / 接受好数据（端到端 sanity）
# ─────────────────────────────────────────────────────────────────────────────


def test_stage_a_schema_accepts_valid_candidate() -> None:
    payload = {
        "candidates": [
            {
                "chunk_id": "chunk_1",
                "span_start": 0,
                "span_end": 5,
                "span_text": "hello",
                "reason": "trigger word demo",
            }
        ]
    }
    Draft202012Validator(STAGE_A_SCHEMA).validate(payload)
    # Pydantic 也应通过
    ExtractCandidate.model_validate(payload["candidates"][0])


@pytest.mark.parametrize(
    "bad_payload, hint",
    [
        ({"candidates": "not-an-array"}, "candidates must be array"),
        (
            {"candidates": [{"chunk_id": "", "span_start": 0, "span_end": 1, "span_text": "x", "reason": "y"}]},
            "empty chunk_id",
        ),
        (
            {"candidates": [{"chunk_id": "c1", "span_start": 0, "span_end": 0, "span_text": "x", "reason": "y"}]},
            "span_end minimum",
        ),
        (
            {
                "candidates": [
                    {"chunk_id": "c1", "span_start": 0, "span_end": 5, "span_text": "x", "reason": "y", "extra": 1}
                ]
            },
            "additionalProperties",
        ),
    ],
)
def test_stage_a_schema_rejects_bad(bad_payload: dict, hint: str) -> None:
    with pytest.raises(jsonschema.ValidationError):
        Draft202012Validator(STAGE_A_SCHEMA).validate(bad_payload)


def test_stage_b_schema_accepts_skip_form() -> None:
    Draft202012Validator(STAGE_B_SCHEMA).validate({"skip": True, "reason": "section heading not a constraint"})


def test_stage_b_schema_accepts_full_form_round_trip_with_pydantic() -> None:
    """stage_b_v1 既要 jsonschema 通过，也要 Pydantic 反序列化通过 —— 真正"同形"。"""
    sample = {
        "kind": "exclusion",
        "category": "SAFETY",
        "class": "hard",
        "severity": "critical",
        "authority": "enterprise",
        "conformance": "MUST",
        "rule_expression": "forbid_when(S20, p<0.6)",
        "rationale": "AO 4.3: 气源不足时禁止启动铆枪",
        "applicable_phases": ["OPERATION"],
        "valid_from": None,
        "valid_to": None,
        "scope": {
            "node_rds_candidates": ["=PROC.S20"],
            "asset_guid_candidates": [],
            "product_id": None,
        },
        "source_document_id": "AO-DEMO-001",
        "source_span": {"page": 1, "char_start": 126, "char_end": 161},
        "span_text": "作业前必须确认气源压力 >= 0.6 MPa, 禁止在压力不足时启动铆枪",
        "confidence": 0.9,
    }
    Draft202012Validator(STAGE_B_SCHEMA).validate(sample)
    ExtractedConstraint.model_validate(sample)


@pytest.mark.parametrize(
    "bad_node_rds",
    ["S20 工位", "/abs/path", "中文编码", "S20 with space", ""],
)
def test_stage_b_schema_rds_pattern_rejects_garbage(bad_node_rds: str) -> None:
    payload = {
        "kind": "exclusion",
        "category": "SAFETY",
        "class": "hard",
        "severity": "minor",
        "authority": "enterprise",
        "conformance": "MUST",
        "rule_expression": "x()",
        "rationale": "rationale text",
        "applicable_phases": ["OPERATION"],
        "valid_from": None,
        "valid_to": None,
        "scope": {
            "node_rds_candidates": [bad_node_rds],
            "asset_guid_candidates": [],
            "product_id": None,
        },
        "source_document_id": "doc",
        "source_span": {"page": 0, "char_start": 0, "char_end": 1},
        "span_text": "x",
        "confidence": 0.5,
    }
    with pytest.raises(jsonschema.ValidationError):
        Draft202012Validator(STAGE_B_SCHEMA).validate(payload)


# ─────────────────────────────────────────────────────────────────────────────
# 4. thresholds — 默认 / ENV 旋钮 / 越界回退
# ─────────────────────────────────────────────────────────────────────────────


def test_thresholds_defaults_match_locked_values() -> None:
    """默认值与 docs/kg_execution_tasks_v1.md §T4.2 锁定一致。"""
    t = ExtractorThresholds()
    assert t.confidence_reject == DEFAULT_CONFIDENCE_REJECT == 0.40
    assert t.confidence_low == DEFAULT_CONFIDENCE_LOW == 0.60
    assert t.confidence_high == DEFAULT_CONFIDENCE_HIGH == 0.85
    assert t.batch_min_yield == DEFAULT_BATCH_MIN_YIELD == 0.20
    assert t.batch_min_mean_confidence == DEFAULT_BATCH_MIN_MEAN_CONFIDENCE == 0.50


def test_thresholds_strict_ordering_enforced() -> None:
    with pytest.raises(ValueError, match="0 <= reject < low < high <= 1"):
        ExtractorThresholds(confidence_reject=0.5, confidence_low=0.4, confidence_high=0.85)


def test_current_thresholds_picks_up_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXTRACTOR_CONFIDENCE_REJECT", "0.30")
    monkeypatch.setenv("EXTRACTOR_CONFIDENCE_LOW", "0.55")
    monkeypatch.setenv("EXTRACTOR_CONFIDENCE_HIGH", "0.80")
    t = current_thresholds()
    assert (t.confidence_reject, t.confidence_low, t.confidence_high) == (0.30, 0.55, 0.80)


@pytest.mark.parametrize("bad", ["", "abc", "-0.1", "1.5", "nan"])
def test_current_thresholds_falls_back_on_bad_env(monkeypatch: pytest.MonkeyPatch, bad: str) -> None:
    """ENV 越界/解析失败必须回退到默认值，不阻塞抽取。"""
    monkeypatch.setenv("EXTRACTOR_CONFIDENCE_REJECT", bad)
    t = current_thresholds()
    # nan 是个特例：float('nan') 解析成功且不在 [0,1] 内，会被 _env_float 退回默认
    assert t.confidence_reject == DEFAULT_CONFIDENCE_REJECT


def test_thresholds_module_exports_no_secrets() -> None:
    """sanity：thresholds 不应误把 API key / DSN 等机密夹带出来。"""
    from pathlib import Path

    from app.services.constraint_extractor import thresholds as mod

    assert mod.__file__ is not None
    src_path = Path(mod.__file__)
    assert src_path.name == "thresholds.py"
    text = src_path.read_text(encoding="utf-8")
    for forbidden in ("OPENAI_API_KEY", "POSTGRES_DSN", "JWT_SIGNING_KEY", "MCP_BEARER_TOKEN"):
        assert forbidden not in text


def test_schema_files_are_pure_json_no_comments() -> None:
    """JSON 文件不能有 // 行注释（jsonschema 不支持）。"""
    for version in (STAGE_A_VERSION, STAGE_B_VERSION):
        schema = load_schema(version)
        # 二次序列化再解析必须等价 —— 如果有非法字段会失败
        round_trip = json.loads(json.dumps(schema))
        assert round_trip == schema
