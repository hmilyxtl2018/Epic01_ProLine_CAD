"""tools/registry.py 单元测试 — 4 个 tool + dispatcher + budget。"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import ezdxf
import pytest

from agents.parse_agent.agent_loader import load_agent_definition
from agents.parse_agent.tools.registry import (
    BudgetState,
    ToolDispatcher,
    list_layer_entities,
    lookup_block_definition,
    propose_taxonomy_term,
    search_similar_blocks,
)


# ════════════ Fixtures ════════════

@pytest.fixture
def doc():
    """构造一个最小 DXF: 1 个 block 定义 + modelspace 上 3 个实体。"""
    d = ezdxf.new()
    blk = d.blocks.new(name="WashingMachine")
    blk.add_line((0, 0), (1, 0))
    blk.add_line((1, 0), (1, 1))
    blk.add_circle((0.5, 0.5), 0.2)

    msp = d.modelspace()
    msp.add_text("Conv-01", dxfattribs={"layer": "STEP_1"}).set_placement((0, 0))
    msp.add_line((0, 0), (10, 0), dxfattribs={"layer": "STEP_1"})
    msp.add_blockref("WashingMachine", (5, 5), dxfattribs={"layer": "AM_0"})
    return d


@pytest.fixture
def agent_def():
    return load_agent_definition()


# ════════════ lookup_block_definition ════════════

def test_lookup_existing_block(doc):
    out = lookup_block_definition(doc, "WashingMachine")
    assert out["exists"] is True
    assert out["entity_counts"]["LINE"] == 2
    assert out["entity_counts"]["CIRCLE"] == 1
    assert out["total_entities"] == 3
    assert out["bbox"] is not None and len(out["bbox"]) == 4


def test_lookup_missing_block(doc):
    out = lookup_block_definition(doc, "DoesNotExist")
    assert out["exists"] is False


# ════════════ list_layer_entities ════════════

def test_list_layer_basic(doc):
    out = list_layer_entities(doc, "STEP_1", limit=10)
    assert out["layer"] == "STEP_1"
    assert out["total_on_layer"] == 2
    assert out["truncated"] is False
    assert len(out["samples"]) == 2
    types = {s["type"] for s in out["samples"]}
    assert "TEXT" in types and "LINE" in types


def test_list_layer_empty(doc):
    out = list_layer_entities(doc, "NONEXISTENT", limit=5)
    assert out["total_on_layer"] == 0
    assert out["samples"] == []


def test_list_layer_limit_clamped(doc):
    out = list_layer_entities(doc, "STEP_1", limit=999)  # 超 50 上限
    assert len(out["samples"]) <= 50


def test_list_layer_truncation_flag(doc):
    msp = doc.modelspace()
    for i in range(5):
        msp.add_line((0, i), (1, i), dxfattribs={"layer": "MANY"})
    out = list_layer_entities(doc, "MANY", limit=2)
    assert out["total_on_layer"] == 5
    assert len(out["samples"]) == 2
    assert out["truncated"] is True


# ════════════ search_similar_blocks (planned) ════════════

def test_search_raises_not_implemented():
    with pytest.raises(NotImplementedError, match="Phase5"):
        search_similar_blocks("foo")


# ════════════ propose_taxonomy_term ════════════

def test_propose_writes_jsonl(tmp_path):
    out = propose_taxonomy_term(
        quarantine_dir=tmp_path,
        run_id="run_test",
        term="HoningMachine",
        asset_type="Equipment",
        evidence=["珩磨机", "honing"],
    )
    assert out["queued"] is True
    queue_file = tmp_path / "run_test.jsonl"
    assert queue_file.exists()
    rec = json.loads(queue_file.read_text(encoding="utf-8").strip())
    assert rec["term"] == "HoningMachine"
    assert rec["asset_type"] == "Equipment"
    assert rec["approved"] is False
    assert "term_hash" in rec


def test_propose_appends(tmp_path):
    propose_taxonomy_term(tmp_path, "r1", "A", "Equipment", ["x"])
    propose_taxonomy_term(tmp_path, "r1", "B", "Conveyor", ["y"])
    lines = (tmp_path / "r1.jsonl").read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2


def test_propose_rejects_empty_evidence(tmp_path):
    with pytest.raises(ValueError, match="evidence"):
        propose_taxonomy_term(tmp_path, "r1", "X", "Equipment", [])


def test_propose_rejects_invalid_type(tmp_path):
    with pytest.raises(ValueError, match="invalid asset_type"):
        propose_taxonomy_term(tmp_path, "r1", "X", "Robot", ["e"])


# ════════════ BudgetState ════════════

def test_budget_under_limit():
    b = BudgetState(max_calls=3, max_tokens=100)
    assert b.check_and_inc(10) == (True, None)
    assert b.check_and_inc(20) == (True, None)
    assert b.used_calls == 2
    assert b.used_tokens == 30


def test_budget_call_count_exceeded():
    b = BudgetState(max_calls=2)
    b.check_and_inc(); b.check_and_inc()
    ok, msg = b.check_and_inc()
    assert ok is False and "max_calls" in msg


def test_budget_token_exceeded():
    b = BudgetState(max_calls=10, max_tokens=50)
    ok, msg = b.check_and_inc(60)
    assert ok is False and "max_tokens" in msg


# ════════════ ToolDispatcher (端到端) ════════════

def test_dispatcher_implemented_tool(doc, agent_def):
    disp = ToolDispatcher(agent_def=agent_def, context={"doc": doc})
    r = disp.call("lookup_block_definition", block_name="WashingMachine")
    assert r.ok is True
    assert r.data["exists"] is True
    assert r.elapsed_ms > 0
    assert disp.budget.used_calls == 1


def test_dispatcher_planned_tool_blocked(agent_def):
    disp = ToolDispatcher(agent_def=agent_def)
    r = disp.call("search_similar_blocks", block_name="x")
    assert r.ok is False
    assert r.error_code == "tool_unavailable"
    # planned 不应消耗 budget
    assert disp.budget.used_calls == 0


def test_dispatcher_unknown_tool(agent_def):
    disp = ToolDispatcher(agent_def=agent_def)
    r = disp.call("nuke_database")
    assert r.ok is False
    assert r.error_code == "invalid_args"


def test_dispatcher_missing_doc_context(agent_def):
    disp = ToolDispatcher(agent_def=agent_def, context={})
    r = disp.call("lookup_block_definition", block_name="x")
    assert r.ok is False
    assert r.error_code == "invalid_args"


def test_dispatcher_budget_exhausted(doc, agent_def):
    disp = ToolDispatcher(
        agent_def=agent_def,
        budget=BudgetState(max_calls=1),
        context={"doc": doc},
    )
    r1 = disp.call("lookup_block_definition", block_name="WashingMachine")
    r2 = disp.call("lookup_block_definition", block_name="WashingMachine")
    assert r1.ok is True
    assert r2.ok is False and r2.error_code == "budget_exceeded"


def test_dispatcher_propose_taxonomy_term(agent_def, tmp_path):
    disp = ToolDispatcher(
        agent_def=agent_def,
        context={"quarantine_dir": tmp_path, "run_id": "ci_run"},
    )
    r = disp.call(
        "propose_taxonomy_term",
        term="新设备", asset_type="Equipment", evidence=["新设备"],
    )
    assert r.ok is True
    assert (tmp_path / "ci_run.jsonl").exists()


def test_dispatcher_invalid_args_caught(doc, agent_def, tmp_path):
    disp = ToolDispatcher(
        agent_def=agent_def,
        context={"quarantine_dir": tmp_path, "run_id": "r"},
    )
    r = disp.call(
        "propose_taxonomy_term",
        term="x", asset_type="BadType", evidence=["e"],
    )
    assert r.ok is False
    assert r.error_code == "invalid_args"
