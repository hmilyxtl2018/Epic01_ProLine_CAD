"""T3 prompt + fixture L0 单测（ADR-0010 / docs/kg_execution_tasks_v1.md §T3）。

覆盖三类断言：

1. prompt 文件存在、长度 ≥ 200 字、版本常量稳定。
2. Stage B 模板硬注入了所有相关枚举（防漏注入回归）。
3. 离线 fixture ``ao_sample_001.expected.json`` 通过
   ``ExtractedConstraint.model_validate``，且 span 偏移与原文一致。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from app.schemas.constraint_extraction import (
    ExtractedConstraint,
    chunk_content_hash,
)
from app.services.constraint_extractor import (
    STAGE_A_VERSION,
    STAGE_B_VERSION,
    load_prompt,
)

from shared.models import (
    AssetType,
    ConstraintAuthority,
    ConstraintCategory,
    ConstraintClass,
    ConstraintConformance,
    ConstraintKind,
    ConstraintSeverity,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "extraction"
SAMPLE_TXT = FIXTURE_DIR / "ao_sample_001.txt"
SAMPLE_JSON = FIXTURE_DIR / "ao_sample_001.expected.json"


# ─────────────────────────────────────────────────────────────────────────────
# 1. Prompt 文件落地与版本常量
# ─────────────────────────────────────────────────────────────────────────────


def test_stage_versions_are_stable_strings() -> None:
    """版本常量是审计锚点，必须是确定的小写下划线字符串。"""
    assert STAGE_A_VERSION == "stage_a_v1"
    assert STAGE_B_VERSION == "stage_b_v1"


@pytest.mark.parametrize(
    "version",
    [STAGE_A_VERSION, STAGE_B_VERSION],
)
def test_prompt_file_loads_and_meets_min_length(version: str) -> None:
    """每个 prompt ≥ 200 字（plan T3 验收硬指标）。"""
    text = load_prompt(version)
    assert isinstance(text, str)
    assert len(text) >= 200, f"{version} prompt too short: {len(text)} chars"
    assert text.startswith("#"), "prompt 必须以 Markdown H1 开头，便于版本对比"


def test_load_prompt_rejects_unknown_version() -> None:
    """未知版本应抛 ``ValueError``，避免静默回退。"""
    with pytest.raises(ValueError, match="unknown prompt version"):
        load_prompt("stage_c_v99")


# ─────────────────────────────────────────────────────────────────────────────
# 2. Stage B 模板硬注入枚举（防漏注入回归）
# ─────────────────────────────────────────────────────────────────────────────


def test_stage_a_prompt_mentions_candidate_contract() -> None:
    """Stage A 必须告诉 LLM 输出 candidates 数组与必填字段。"""
    text = load_prompt(STAGE_A_VERSION)
    for token in ("candidates", "span_start", "span_end", "span_text", "reason"):
        assert token in text, f"Stage A prompt 缺关键字段提示：{token}"


@pytest.mark.parametrize(
    "enum_cls",
    [
        ConstraintKind,
        ConstraintCategory,
        ConstraintClass,
        ConstraintSeverity,
        ConstraintAuthority,
        ConstraintConformance,
        AssetType,
    ],
)
def test_stage_b_prompt_injects_all_enum_values(enum_cls: type) -> None:
    """枚举值必须以字符串形式硬注入到 Stage B 模板，防止漂移。"""
    text = load_prompt(STAGE_B_VERSION)
    missing = [member.value for member in enum_cls if member.value not in text]
    assert not missing, (
        f"Stage B prompt 缺少 {enum_cls.__name__} 枚举值：{missing}；若新增枚举请同步模板并 bump prompt 版本号。"
    )


def test_stage_b_prompt_includes_rds_format_examples() -> None:
    """RDS 三视角前缀必须出现，避免 LLM 编出错误编码。"""
    text = load_prompt(STAGE_B_VERSION)
    assert "=PROC" in text
    for prefix_marker in ("FUNCTION 视角", "PRODUCT 视角", "LOCATION 视角"):
        assert prefix_marker in text, f"Stage B 缺 RDS 视角说明：{prefix_marker}"


def test_stage_b_prompt_lists_at_least_five_counter_examples() -> None:
    """plan 要求至少 5 条反例。粗略以编号 1.~5. 出现做下限校验。"""
    text = load_prompt(STAGE_B_VERSION)
    for marker in ("1.", "2.", "3.", "4.", "5."):
        assert marker in text, f"Stage B 反例段缺编号：{marker}"


# ─────────────────────────────────────────────────────────────────────────────
# 3. 离线 fixture 校验（gold 必须自洽）
# ─────────────────────────────────────────────────────────────────────────────


def _load_fixture() -> tuple[str, dict]:
    text = SAMPLE_TXT.read_text(encoding="utf-8")
    payload = json.loads(SAMPLE_JSON.read_text(encoding="utf-8"))
    return text, payload


def test_fixture_files_exist() -> None:
    assert SAMPLE_TXT.is_file(), f"missing fixture: {SAMPLE_TXT}"
    assert SAMPLE_JSON.is_file(), f"missing fixture: {SAMPLE_JSON}"


def test_fixture_meta_content_hash_matches_text() -> None:
    """``content_hash`` 必须等于 sample.txt 的 sha256，否则 gold 已漂移。"""
    text, payload = _load_fixture()
    expected_hash = payload["fixture_meta"]["chunk"]["content_hash"]
    assert chunk_content_hash(text) == expected_hash


def test_fixture_constraints_validate_against_pydantic_contract() -> None:
    """每条 gold 必须能反序列化为 ``ExtractedConstraint``。"""
    _, payload = _load_fixture()
    constraints = payload["expected_constraints"]
    assert len(constraints) >= 3, "plan T3 要求 ≥ 3 条 gold（SAFETY / SEQUENCE / RESOURCE）"
    for raw in constraints:
        ExtractedConstraint.model_validate(raw)


def test_fixture_spans_match_source_text_offsets() -> None:
    """``source_span`` 的 ``[char_start, char_end]`` 必须在原文里逐字对得上。"""
    text, payload = _load_fixture()
    for raw in payload["expected_constraints"]:
        span = raw["source_span"]
        sliced = text[span["char_start"] : span["char_end"]]
        assert sliced == raw["span_text"], (
            f"span 偏移漂移：document={raw['source_document_id']} expected={raw['span_text']!r} got={sliced!r}"
        )


def test_fixture_covers_required_categories() -> None:
    """plan 要求 fixture 覆盖 SAFETY + SEQUENCE + RESOURCE 三类。"""
    _, payload = _load_fixture()
    categories = {c["category"] for c in payload["expected_constraints"]}
    assert {"SAFETY", "SEQUENCE", "RESOURCE"}.issubset(categories), f"fixture 类别覆盖不足：{categories}"
