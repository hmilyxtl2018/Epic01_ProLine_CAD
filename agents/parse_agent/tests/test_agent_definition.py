"""Schema 校验测试 — 防止 agent.json 与代码契约漂移。

属于 H7 / S4 工程化基线: 每次 PR 必跑，破坏契约直接 fail-fast。

参考:
- agents/parse_agent/agent.json
- agents/parse_agent/agent_loader.py
- ExcPlan/parse_agent_ga_execution_plan.md §5 S4-T5
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from agents.parse_agent.agent_loader import (
    AgentDefinitionError,
    load_agent_definition,
)

AGENT_JSON = Path(__file__).resolve().parent.parent / "agent.json"


# ---------- 基础加载 ----------

def test_agent_json_exists():
    assert AGENT_JSON.exists(), f"agent.json missing: {AGENT_JSON}"


def test_agent_json_valid_json():
    json.loads(AGENT_JSON.read_text(encoding="utf-8"))


def test_load_agent_definition_succeeds():
    defn = load_agent_definition()
    assert defn.name
    assert defn.version
    assert defn.model.startswith("claude-")


# ---------- 顶层契约 ----------

@pytest.fixture(scope="module")
def defn():
    return load_agent_definition()


def test_required_top_level_fields(defn):
    raw = defn.raw
    for k in (
        "name", "version", "description", "model", "prompt",
        "tools", "input_schema", "output_schema",
        "hooks", "guardrails", "stage_gates", "evaluation",
    ):
        assert k in raw, f"missing top-level field: {k}"


def test_input_output_schema_are_objects(defn):
    assert isinstance(defn.raw["input_schema"], dict)
    assert isinstance(defn.raw["output_schema"], dict)


# ---------- Tools ----------

def test_required_tools_present(defn):
    names = {t["name"] for t in defn.tools}
    expected = {
        "lookup_block_definition",
        "list_layer_entities",
        "search_similar_blocks",
        "propose_taxonomy_term",
    }
    assert expected.issubset(names), f"missing tools: {expected - names}"


def test_tools_have_required_fields(defn):
    for t in defn.tools:
        assert "name" in t
        assert "description" in t
        assert "cost" in t and t["cost"] in {"low", "medium", "high"}
        assert "input_schema" in t and isinstance(t["input_schema"], dict)


def test_propose_taxonomy_term_requires_approval(defn):
    tool = next(t for t in defn.tools if t["name"] == "propose_taxonomy_term")
    assert tool.get("requires_approval") is True, (
        "propose_taxonomy_term 必须 requires_approval=true (词表变更需人审)"
    )


# ---------- Hooks (H1-H7) ----------

def test_all_seven_hooks_present(defn):
    expected = {
        "H1_format_validate",
        "H2_coord_sanity",
        "H3_rule_classify",
        "H4_llm_classify_unknowns",
        "H5_response_validator",
        "H6_confidence_calibration",
        "H7_gold_regression_check",
    }
    assert expected.issubset(defn.hooks.keys()), (
        f"missing hooks: {expected - defn.hooks.keys()}"
    )


def test_hooks_have_kind_field(defn):
    for hname, hbody in defn.hooks.items():
        assert "kind" in hbody, f"hook {hname} missing 'kind'"


# ---------- Stage Gates (L1-L5) ----------

def test_all_five_stage_gates_present(defn):
    expected = {
        "L1_input", "L2_geometry", "L3_semantic",
        "L4_topology", "L5_contract",
    }
    assert expected.issubset(defn.stage_gates.keys())


# ---------- Guardrails ----------

def test_cost_budgets_are_positive(defn):
    assert defn.llm_call_budget > 0
    assert defn.token_budget > 0


def test_quality_threshold_is_sane(defn):
    # gold 回归阈值应在 (0, 0.1] 之间
    t = defn.gold_regression_threshold
    assert 0 < t <= 0.1


# ---------- Evaluation 三层 ----------

def test_evaluation_has_three_tiers(defn):
    tiers = defn.evaluation["tiers"]
    for k in ("gold", "silver", "bronze"):
        assert k in tiers, f"evaluation.tiers.{k} missing"


def test_evaluation_baseline_present(defn):
    """Phase 4.6 已确立 gold=0.8267 / llm_judge=0.301 基线，必须落库。"""
    tiers = defn.evaluation["tiers"]
    gold_score = tiers["gold"].get("current_score")
    bronze_score = tiers["bronze"].get("current_score")
    assert isinstance(gold_score, (int, float)) and gold_score > 0
    assert isinstance(bronze_score, (int, float)) and bronze_score > 0
    # GA target 必须 > 当前
    assert tiers["gold"].get("ga_target", 0) > gold_score
    assert tiers["bronze"].get("ga_target", 0) > bronze_score


# ---------- Prompt 关键词防护 ----------

def test_prompt_mentions_critical_constraints(defn):
    p = defn.prompt
    for kw in ("evidence_keywords", "ClassificationResponse", "Unknown"):
        assert kw in p, f"prompt missing keyword: {kw}"


# ---------- 负向: validator 真的会拒非法输入 ----------

def test_validator_rejects_missing_field(tmp_path):
    bad = json.loads(AGENT_JSON.read_text(encoding="utf-8"))
    del bad["hooks"]
    p = tmp_path / "bad.json"
    p.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(AgentDefinitionError):
        load_agent_definition(p)


def test_validator_rejects_invalid_tool_cost(tmp_path):
    bad = json.loads(AGENT_JSON.read_text(encoding="utf-8"))
    bad["tools"][0]["cost"] = "huge"  # 非法
    p = tmp_path / "bad.json"
    p.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(AgentDefinitionError):
        load_agent_definition(p)


# ---------- Tool 生命周期 status (防"声明 ≠ 实现"漂移) ----------

def test_every_tool_has_status_field(defn):
    """每个 tool 必须显式声明 status,避免新增 tool 漏标。"""
    for t in defn.tools:
        assert "status" in t, f"tool '{t['name']}' missing 'status' field"
        assert t["status"] in {"implemented", "stub", "planned"}


def test_validator_rejects_missing_status(tmp_path):
    bad = json.loads(AGENT_JSON.read_text(encoding="utf-8"))
    del bad["tools"][0]["status"]
    p = tmp_path / "bad.json"
    p.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(AgentDefinitionError, match="missing 'status'"):
        load_agent_definition(p)


def test_validator_rejects_invalid_status(tmp_path):
    bad = json.loads(AGENT_JSON.read_text(encoding="utf-8"))
    bad["tools"][0]["status"] = "shipped"  # 非法
    p = tmp_path / "bad.json"
    p.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(AgentDefinitionError, match="invalid status"):
        load_agent_definition(p)


def test_implemented_tools_must_be_importable(defn):
    """status=implemented 的 tool 必须能 import 到 callable —— 防止上线即崩。

    status=stub/planned 不做此检查 (允许声明先行)。
    """
    import importlib

    for t in defn.tools:
        if t.get("status") != "implemented":
            continue
        impl = t.get("implementation")
        assert impl, f"tool '{t['name']}' status=implemented but no 'implementation' field"
        assert ":" in impl, (
            f"tool '{t['name']}' implementation must be 'module.path:callable_name'"
        )
        module_path, callable_name = impl.split(":", 1)
        try:
            mod = importlib.import_module(module_path)
        except ImportError as e:
            pytest.fail(
                f"tool '{t['name']}' implementation module '{module_path}' "
                f"not importable: {e}"
            )
        assert hasattr(mod, callable_name), (
            f"tool '{t['name']}' callable '{callable_name}' "
            f"not found in module '{module_path}'"
        )
        assert callable(getattr(mod, callable_name)), (
            f"tool '{t['name']}' '{callable_name}' is not callable"
        )


def test_search_similar_blocks_descoped_to_phase5(defn):
    """显式锁定: search_similar_blocks 不在 GA 范围,防止误升级阻断 GA。"""
    tool = next(t for t in defn.tools if t["name"] == "search_similar_blocks")
    assert tool["status"] == "planned", (
        "search_similar_blocks 已被声明为 Phase5+ 任务,不应在 GA 前改为 stub/implemented"
    )
