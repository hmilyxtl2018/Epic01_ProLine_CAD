"""H4 LLM 分类器单元测试 — 用 mock client 覆盖所有路径。"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import ezdxf
import pytest

from agents.parse_agent.agent_loader import load_agent_definition
from agents.parse_agent.h4_llm_classifier import (
    ClassifyContext,
    H4LLMClassifier,
    _build_user_message,
    _exposed_tools,
    _parse_response,
)
from agents.parse_agent.tools.registry import BudgetState, ToolDispatcher


# ════════════ Mock OpenAI ChatCompletion 响应 ════════════

@dataclass
class _MockFn:
    name: str
    arguments: str


@dataclass
class _MockToolCall:
    id: str
    function: _MockFn
    type: str = "function"


@dataclass
class _MockMessage:
    content: str = ""
    tool_calls: list[_MockToolCall] | None = None


@dataclass
class _MockChoice:
    message: _MockMessage


@dataclass
class _MockResponse:
    choices: list[_MockChoice]


class ScriptedClient:
    """按预设脚本依次返回响应,便于断言对话流。"""
    def __init__(self, script: list[_MockResponse]):
        self.script = list(script)
        self.calls: list[dict[str, Any]] = []

    def create_completion(self, *, messages, tools):
        self.calls.append({"messages": list(messages), "tools": tools})
        if not self.script:
            raise AssertionError("ScriptedClient ran out of responses")
        return self.script.pop(0)


def _final(content: dict | str) -> _MockResponse:
    txt = json.dumps(content) if isinstance(content, dict) else content
    return _MockResponse([_MockChoice(_MockMessage(content=txt))])


def _tool_call(name: str, args: dict, call_id: str = "tc1") -> _MockResponse:
    return _MockResponse([_MockChoice(_MockMessage(
        content="",
        tool_calls=[_MockToolCall(id=call_id, function=_MockFn(name, json.dumps(args)))],
    ))])


# ════════════ Fixtures ════════════

@pytest.fixture
def doc():
    d = ezdxf.new()
    blk = d.blocks.new(name="珩磨机_op170")
    blk.add_line((0, 0), (1, 1))
    msp = d.modelspace()
    msp.add_text("op170", dxfattribs={"layer": "AM_0"}).set_placement((0, 0))
    return d


@pytest.fixture
def agent_def():
    return load_agent_definition()


@pytest.fixture
def dispatcher(agent_def, doc):
    return ToolDispatcher(
        agent_def=agent_def,
        budget=BudgetState(max_calls=10),
        context={"doc": doc},
    )


@pytest.fixture
def ctx():
    return ClassifyContext(
        block_name="珩磨机_op170",
        layer="AM_0",
        sample_labels=["op170"],
    )


# ════════════ _exposed_tools / _to_openai_tool ════════════

def test_exposed_tools_filters_planned_and_high_cost(agent_def):
    tools = _exposed_tools(agent_def)
    names = {t["function"]["name"] for t in tools}
    # 暴露的: lookup + list (low + implemented)
    assert "lookup_block_definition" in names
    assert "list_layer_entities" in names
    # 不暴露: planned (search) + high-cost (propose)
    assert "search_similar_blocks" not in names
    assert "propose_taxonomy_term" not in names


def test_openai_tool_schema_shape(agent_def):
    tools = _exposed_tools(agent_def)
    for t in tools:
        assert t["type"] == "function"
        assert "name" in t["function"]
        assert "description" in t["function"]
        assert t["function"]["parameters"]["type"] == "object"


# ════════════ _build_user_message ════════════

def test_user_message_contains_inputs(ctx):
    msg = _build_user_message(ctx)
    assert "珩磨机_op170" in msg
    assert "AM_0" in msg
    assert "op170" in msg


# ════════════ _parse_response ════════════

def test_parse_valid(ctx):
    raw = '{"type":"Equipment","sub_type":"HoningMachine","confidence":0.85,"evidence_keywords":["珩磨机","op170"]}'
    r = _parse_response(raw, ctx)
    assert r.type == "Equipment"
    assert r.sub_type == "HoningMachine"
    assert r.confidence == 0.85
    assert r.evidence_keywords == ["珩磨机", "op170"]
    assert r.classifier_kind == "llm_fallback"


def test_parse_strips_markdown_fences(ctx):
    raw = '```json\n{"type":"Conveyor","confidence":0.5,"evidence_keywords":[]}\n```'
    r = _parse_response(raw, ctx)
    assert r.type == "Conveyor"


def test_parse_empty_returns_unknown(ctx):
    r = _parse_response("", ctx)
    assert r.type == "Unknown"
    assert r.error == "empty response"


def test_parse_invalid_json_returns_unknown(ctx):
    r = _parse_response("not json at all", ctx)
    assert r.type == "Unknown"
    assert "json_decode" in (r.error or "")


def test_parse_invalid_type_returns_unknown(ctx):
    raw = '{"type":"Robot","confidence":0.9,"evidence_keywords":[]}'
    r = _parse_response(raw, ctx)
    assert r.type == "Unknown"
    assert "invalid type" in (r.error or "")


def test_parse_confidence_out_of_range(ctx):
    raw = '{"type":"Equipment","confidence":1.5,"evidence_keywords":[]}'
    r = _parse_response(raw, ctx)
    assert r.type == "Unknown"
    assert "out of range" in (r.error or "")


def test_parse_confidence_not_number(ctx):
    raw = '{"type":"Equipment","confidence":"high","evidence_keywords":[]}'
    r = _parse_response(raw, ctx)
    assert r.type == "Unknown"


def test_parse_evidence_not_list(ctx):
    raw = '{"type":"Equipment","confidence":0.5,"evidence_keywords":"oops"}'
    r = _parse_response(raw, ctx)
    assert r.type == "Unknown"


def test_parse_drops_invalid_subtype(ctx):
    raw = '{"type":"Equipment","sub_type":123,"confidence":0.5,"evidence_keywords":[]}'
    r = _parse_response(raw, ctx)
    assert r.sub_type is None


# ════════════ H4LLMClassifier 端到端 ════════════

def test_classify_direct_answer(agent_def, dispatcher, ctx):
    """LLM 一次就给最终 JSON,不调工具。"""
    client = ScriptedClient([
        _final({"type": "Equipment", "confidence": 0.7,
                "evidence_keywords": ["珩磨机"]}),
    ])
    h4 = H4LLMClassifier(agent_def=agent_def, client=client)
    r = h4.classify(ctx, dispatcher)
    assert r.type == "Equipment"
    assert r.confidence == 0.7
    # tool 没被调,budget 不增
    assert dispatcher.budget.used_calls == 0
    assert len(client.calls) == 1


def test_classify_with_one_tool_call(agent_def, dispatcher, ctx):
    """LLM 先调 lookup_block_definition,再给最终答案。"""
    client = ScriptedClient([
        _tool_call("lookup_block_definition", {"block_name": "珩磨机_op170"}),
        _final({"type": "Equipment", "confidence": 0.9,
                "evidence_keywords": ["珩磨机_op170"]}),
    ])
    h4 = H4LLMClassifier(agent_def=agent_def, client=client)
    r = h4.classify(ctx, dispatcher)
    assert r.type == "Equipment"
    # 工具被实际调用,budget+1
    assert dispatcher.budget.used_calls == 1
    # 第二轮的 messages 应包含 tool 结果
    assert len(client.calls) == 2
    second_messages = client.calls[1]["messages"]
    tool_msgs = [m for m in second_messages if m.get("role") == "tool"]
    assert len(tool_msgs) == 1
    assert json.loads(tool_msgs[0]["content"])["ok"] is True


def test_classify_tool_turn_cap(agent_def, dispatcher, ctx):
    """LLM 一直要工具,超 max_tool_turns 后强制收敛 Unknown。"""
    # max_tool_turns=2 → 允许 2 轮工具,第 3 轮还要工具就 cap
    h4 = H4LLMClassifier(agent_def=agent_def, client=ScriptedClient([
        _tool_call("lookup_block_definition", {"block_name": "x"}, "t1"),
        _tool_call("lookup_block_definition", {"block_name": "y"}, "t2"),
        _tool_call("lookup_block_definition", {"block_name": "z"}, "t3"),
    ]), max_tool_turns=2)
    r = h4.classify(ctx, dispatcher)
    assert r.type == "Unknown"
    assert r.error == "tool_turn_cap"


def test_classify_llm_exception(agent_def, dispatcher, ctx):
    """LLM 抛错 → 收敛 Unknown(llm_error)。"""
    class Boom:
        def create_completion(self, **kw):
            raise RuntimeError("upstream 503")
    h4 = H4LLMClassifier(agent_def=agent_def, client=Boom())
    r = h4.classify(ctx, dispatcher)
    assert r.type == "Unknown"
    assert "llm_error" in (r.error or "")


def test_classify_budget_pre_check(agent_def, doc, ctx):
    """预算已耗尽 → 直接 Unknown,LLM 不被调。"""
    disp = ToolDispatcher(
        agent_def=agent_def,
        budget=BudgetState(max_calls=0),  # 一次都不剩
        context={"doc": doc},
    )
    client = ScriptedClient([_final({"type": "Equipment", "confidence": 0.9,
                                     "evidence_keywords": []})])
    h4 = H4LLMClassifier(agent_def=agent_def, client=client)
    r = h4.classify(ctx, disp)
    assert r.type == "Unknown"
    assert r.error == "budget_exhausted_pre_check"
    assert client.calls == []


def test_classify_budget_exhausted_mid_turn(agent_def, doc, ctx):
    """工具调用中预算耗尽 → 中止收敛 Unknown。"""
    disp = ToolDispatcher(
        agent_def=agent_def,
        budget=BudgetState(max_calls=1),  # 只允许 1 次
        context={"doc": doc},
    )
    client = ScriptedClient([
        _tool_call("lookup_block_definition", {"block_name": "x"}, "t1"),
        # 第二轮还想调,但 budget 已用完
        _tool_call("lookup_block_definition", {"block_name": "y"}, "t2"),
    ])
    h4 = H4LLMClassifier(agent_def=agent_def, client=client)
    r = h4.classify(ctx, disp)
    assert r.type == "Unknown"
    assert r.error == "budget_exceeded_mid_turn"


def test_classify_invalid_response_returns_unknown(agent_def, dispatcher, ctx):
    """LLM 返回非法 JSON → 收敛 Unknown。"""
    client = ScriptedClient([_final("¯\\_(ツ)_/¯ not json")])
    h4 = H4LLMClassifier(agent_def=agent_def, client=client)
    r = h4.classify(ctx, dispatcher)
    assert r.type == "Unknown"


def test_classify_unknown_type_passthrough(agent_def, dispatcher, ctx):
    """LLM 主动返回 Unknown 是合法响应 (证据不足),不算错。"""
    client = ScriptedClient([
        _final({"type": "Unknown", "confidence": 0.0, "evidence_keywords": []}),
    ])
    h4 = H4LLMClassifier(agent_def=agent_def, client=client)
    r = h4.classify(ctx, dispatcher)
    assert r.type == "Unknown"
    assert r.error is None  # 这次不是错路径
