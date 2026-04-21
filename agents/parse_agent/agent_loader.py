"""Agent definition loader — 加载并校验 agent.json 契约。

启动时调用 `load_agent_definition()`，确保 agent.json 与代码运行时假设一致。
失败立即抛 SchemaInvalidError，不允许静默降级。

参考:
- agents/parse_agent/agent.json (Claude AgentDefinition 契约)
- ExcPlan/parse_agent_ga_execution_plan.md §5 S4-T5
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# 必需的顶层字段 (与 Anthropic AgentDefinition + 项目扩展一致)
_REQUIRED_TOP_LEVEL = {
    "name", "version", "description", "model", "prompt",
    "tools", "input_schema", "output_schema",
    "hooks", "guardrails", "stage_gates", "evaluation",
}

# 必需的 hooks (H1-H7)
_REQUIRED_HOOKS = {
    "H1_format_validate", "H2_coord_sanity", "H3_rule_classify",
    "H4_llm_classify_unknowns", "H5_response_validator",
    "H6_confidence_calibration", "H7_gold_regression_check",
}

# 必需的 stage gates
_REQUIRED_STAGES = {
    "L1_input", "L2_geometry", "L3_semantic", "L4_topology", "L5_contract",
}

# 已注册的 tool 集合 (代码侧应实现的)
_REQUIRED_TOOLS = {
    "lookup_block_definition", "list_layer_entities",
    "search_similar_blocks", "propose_taxonomy_term",
}

# Asset type 枚举 (与 shared.models.AssetType 同步)
_VALID_ASSET_TYPES = {
    "Equipment", "Conveyor", "LiftingPoint", "Zone",
    "Annotation", "Other", "Unknown",
}

# Tool 生命周期状态三态:
#   implemented — 代码已落地 + 可用 (registry 必须有对应 callable)
#   stub        — 已声明待实现 (S2 范围),运行期可返回 not_implemented
#   planned     — 已声明但推后到 Phase5+,GA 不阻断
_VALID_TOOL_STATUS = {"implemented", "stub", "planned"}


class AgentDefinitionError(ValueError):
    """agent.json 契约校验失败。"""


@dataclass(frozen=True)
class AgentDefinition:
    """加载并校验后的 agent.json 视图。"""
    name: str
    version: str
    model: str
    prompt: str
    tools: list[dict[str, Any]]
    hooks: dict[str, dict[str, Any]]
    stage_gates: dict[str, dict[str, Any]]
    guardrails: dict[str, Any]
    evaluation: dict[str, Any]
    raw: dict[str, Any]

    @property
    def llm_call_budget(self) -> int:
        return int(
            self.guardrails.get("cost", {})
            .get("per_file", {})
            .get("max_llm_calls", 50)
        )

    @property
    def token_budget(self) -> int:
        return int(
            self.guardrails.get("cost", {})
            .get("per_file", {})
            .get("max_tokens", 20000)
        )

    @property
    def gold_regression_threshold(self) -> float:
        return float(
            self.guardrails.get("quality", {})
            .get("gold_regression_threshold", 0.02)
        )

    @property
    def implemented_tools(self) -> list[str]:
        """返回 status==implemented 的 tool 名。"""
        return [t["name"] for t in self.tools if t.get("status") == "implemented"]

    @property
    def stub_tools(self) -> list[str]:
        return [t["name"] for t in self.tools if t.get("status") == "stub"]

    @property
    def planned_tools(self) -> list[str]:
        return [t["name"] for t in self.tools if t.get("status") == "planned"]


def _validate(data: dict[str, Any]) -> None:
    """对 agent.json 数据做硬性校验。失败抛 AgentDefinitionError。"""
    # 1. 顶层字段
    missing = _REQUIRED_TOP_LEVEL - data.keys()
    if missing:
        raise AgentDefinitionError(
            f"agent.json missing top-level keys: {sorted(missing)}"
        )

    # 2. hooks
    hooks = data.get("hooks", {})
    if not isinstance(hooks, dict):
        raise AgentDefinitionError("hooks must be a dict")
    missing_hooks = _REQUIRED_HOOKS - hooks.keys()
    if missing_hooks:
        raise AgentDefinitionError(
            f"agent.json missing hooks: {sorted(missing_hooks)}"
        )

    # 3. stage_gates
    gates = data.get("stage_gates", {})
    missing_gates = _REQUIRED_STAGES - gates.keys()
    if missing_gates:
        raise AgentDefinitionError(
            f"agent.json missing stage_gates: {sorted(missing_gates)}"
        )

    # 4. tools — 必须全部实现
    tool_names = {t.get("name") for t in data.get("tools", []) if isinstance(t, dict)}
    missing_tools = _REQUIRED_TOOLS - tool_names
    if missing_tools:
        raise AgentDefinitionError(
            f"agent.json missing tools: {sorted(missing_tools)}"
        )

    # 5. tools 内字段
    for t in data["tools"]:
        for k in ("name", "description", "cost", "input_schema"):
            if k not in t:
                raise AgentDefinitionError(
                    f"tool '{t.get('name', '?')}' missing field: {k}"
                )
        if t["cost"] not in {"low", "medium", "high"}:
            raise AgentDefinitionError(
                f"tool '{t['name']}' cost must be low|medium|high"
            )
        # status 必须显式声明 (避免漂移:声明了 ≠ 实现了)
        status = t.get("status")
        if status is None:
            raise AgentDefinitionError(
                f"tool '{t['name']}' missing 'status' field "
                f"(must be one of {sorted(_VALID_TOOL_STATUS)})"
            )
        if status not in _VALID_TOOL_STATUS:
            raise AgentDefinitionError(
                f"tool '{t['name']}' invalid status '{status}', "
                f"must be one of {sorted(_VALID_TOOL_STATUS)}"
            )
        # implemented / stub 必须提供 implementation 路径
        if status in {"implemented", "stub"} and "implementation" not in t:
            raise AgentDefinitionError(
                f"tool '{t['name']}' status='{status}' requires 'implementation' field "
                f"(format: 'module.path:callable_name')"
            )

    # 6. propose_taxonomy_term 必须 requires_approval
    for t in data["tools"]:
        if t["name"] == "propose_taxonomy_term":
            if not t.get("requires_approval"):
                raise AgentDefinitionError(
                    "propose_taxonomy_term must have requires_approval=true"
                )

    # 7. evaluation 三层
    tiers = data.get("evaluation", {}).get("tiers", {})
    for tier in ("gold", "silver", "bronze"):
        if tier not in tiers:
            raise AgentDefinitionError(f"evaluation.tiers.{tier} missing")

    # 8. prompt 内必须提到关键约束 (防 prompt 被改残)
    prompt = data["prompt"]
    must_have = ["evidence_keywords", "ClassificationResponse", "Unknown"]
    for kw in must_have:
        if kw not in prompt:
            raise AgentDefinitionError(
                f"prompt missing required keyword: {kw}"
            )


def load_agent_definition(path: Path | str | None = None) -> AgentDefinition:
    """加载并校验 agent.json。

    Args:
        path: agent.json 路径。默认指向本模块同目录下的 agent.json。

    Returns:
        AgentDefinition 实例。

    Raises:
        FileNotFoundError: agent.json 不存在
        AgentDefinitionError: 契约校验失败
    """
    if path is None:
        path = Path(__file__).resolve().parent / "agent.json"
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"agent.json not found at: {path}")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise AgentDefinitionError(f"agent.json is not valid JSON: {e}") from e

    _validate(data)

    return AgentDefinition(
        name=data["name"],
        version=data["version"],
        model=data["model"],
        prompt=data["prompt"],
        tools=data["tools"],
        hooks=data["hooks"],
        stage_gates=data["stage_gates"],
        guardrails=data["guardrails"],
        evaluation=data["evaluation"],
        raw=data,
    )
