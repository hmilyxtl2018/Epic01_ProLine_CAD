"""Hook H4 — LLM 兜底分类器。

仅在 H3 规则分类失败 (type=Other AND confidence<0.3) 时被触发。
使用 OpenAI-compatible API (xiaoai.plus) + Claude tool-use 协议,
最多 3 轮 tool_call,通过 ToolDispatcher 调度只读工具。

合约 (与 agent.json prompt 对齐):
    输入: ClassifyContext(block_name, layer, sample_labels, doc)
    输出: ClassificationResponse(type, sub_type, confidence, evidence_keywords)

错误路径:
    - LLM 异常 / budget 用尽 → 返回 Unknown(0.0, [])
    - response 缺字段 / type 非法 / evidence 不在输入中 → 返回 Unknown(0.0, [])
      (H5 校验器是另一道防线;此处先做形式校验,语义校验留给 H5)

参考:
- agents/parse_agent/agent.json (prompt + tools 声明)
- agents/parse_agent/tools/registry.py (ToolDispatcher)
- ExcPlan/parse_agent_ga_execution_plan.md §4 S2-T1
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

from agents.parse_agent.agent_loader import AgentDefinition
from agents.parse_agent.tools.registry import ToolDispatcher

log = logging.getLogger(__name__)

# 与 shared.models.AssetType 同步
_VALID_TYPES = {
    "Equipment", "Conveyor", "LiftingPoint", "Zone",
    "Annotation", "Other", "Unknown",
}

# 单次 LLM 调用最多让模型连续调几次工具 (硬上限,与 prompt 内规则一致)
_MAX_TOOL_TURNS = 3


# ════════════════ 数据结构 ════════════════

@dataclass
class ClassifyContext:
    """H4 输入:rule classifier 失败时,调用方提供的上下文。"""
    block_name: str = ""
    layer: str = ""
    sample_labels: list[str] = field(default_factory=list)

    def input_tokens(self) -> set[str]:
        """所有 LLM 可见的输入 token (用于 evidence_keywords 校验)。"""
        toks: set[str] = set()
        if self.block_name:
            toks.add(self.block_name)
        if self.layer:
            toks.add(self.layer)
        toks.update(s for s in self.sample_labels if s)
        return toks


@dataclass
class ClassificationResponse:
    """H4 输出。所有失败路径都收敛到 Unknown(0.0, [])。"""
    type: str = "Unknown"
    sub_type: str | None = None
    confidence: float = 0.0
    evidence_keywords: list[str] = field(default_factory=list)
    classifier_kind: str = "llm_fallback"  # 供 H6 校准识别
    error: str | None = None  # 调试用,不影响下游

    @classmethod
    def unknown(cls, error: str | None = None) -> "ClassificationResponse":
        return cls(type="Unknown", confidence=0.0, evidence_keywords=[], error=error)


class _ChatClient(Protocol):
    """最小化 OpenAI client 接口 (便于 mock)。"""
    def create_completion(
        self, *, messages: list[dict], tools: list[dict] | None,
    ) -> Any: ...


# ════════════════ Tool Schema 转换 ════════════════

def _to_openai_tool(tool: dict[str, Any]) -> dict[str, Any]:
    """把 agent.json 的 tool 声明转成 OpenAI function-calling schema。"""
    return {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool["description"],
            "parameters": tool["input_schema"],
        },
    }


def _exposed_tools(agent_def: AgentDefinition) -> list[dict[str, Any]]:
    """只暴露 implemented + 非 high-cost 的 tool 给 LLM。

    - planned: 跳过(LLM 看不到)
    - high cost (e.g. propose_taxonomy_term): 跳过(只在 quarantine 流程中用)
    - implemented + low/medium: 暴露
    """
    out: list[dict[str, Any]] = []
    for t in agent_def.tools:
        if t.get("status") != "implemented":
            continue
        if t.get("cost") == "high":
            continue
        out.append(_to_openai_tool(t))
    return out


# ════════════════ User Prompt ════════════════

def _build_user_message(ctx: ClassifyContext) -> str:
    return (
        "Classify the following CAD block.\n\n"
        f"block_name: {ctx.block_name or '(none)'}\n"
        f"layer:      {ctx.layer or '(none)'}\n"
        "sample_labels:\n"
        + ("\n".join(f"  - {s}" for s in ctx.sample_labels[:20]) or "  (none)")
        + "\n\n"
        "Reply with the JSON object only. If insufficient evidence, "
        'return {"type": "Unknown", "confidence": 0.0, "evidence_keywords": []}.'
    )


# ════════════════ 响应解析 ════════════════

_JSON_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _parse_response(raw: str, ctx: ClassifyContext) -> ClassificationResponse:
    """形式校验: JSON 解析 + 字段类型 + 枚举 + confidence 范围。

    语义校验 (evidence_keywords ⊆ input_tokens) 留给 H5 — 这里只做必要防御。
    """
    if not raw:
        return ClassificationResponse.unknown("empty response")

    text = _JSON_FENCE.sub("", raw.strip()).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        return ClassificationResponse.unknown(f"json_decode: {e}")

    if not isinstance(data, dict):
        return ClassificationResponse.unknown("response not an object")

    type_ = data.get("type", "Unknown")
    if type_ not in _VALID_TYPES:
        return ClassificationResponse.unknown(f"invalid type: {type_}")

    try:
        conf = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        return ClassificationResponse.unknown("confidence not a number")
    if not 0.0 <= conf <= 1.0:
        return ClassificationResponse.unknown(f"confidence out of range: {conf}")

    kws_raw = data.get("evidence_keywords", [])
    if not isinstance(kws_raw, list):
        return ClassificationResponse.unknown("evidence_keywords not a list")
    kws = [str(k) for k in kws_raw if k]

    sub_type = data.get("sub_type")
    if sub_type is not None and not isinstance(sub_type, str):
        sub_type = None

    return ClassificationResponse(
        type=type_,
        sub_type=sub_type,
        confidence=conf,
        evidence_keywords=kws,
    )


# ════════════════ 主分类器 ════════════════

@dataclass
class H4LLMClassifier:
    """H4 hook 的具体实现。无状态,可复用。

    依赖注入:
        agent_def: 提供 prompt + tools 声明
        client: 任何实现 create_completion 的对象 (OpenAI/mock)
    """
    agent_def: AgentDefinition
    client: _ChatClient
    max_tool_turns: int = _MAX_TOOL_TURNS

    def classify(
        self, ctx: ClassifyContext, dispatcher: ToolDispatcher,
    ) -> ClassificationResponse:
        """执行 1 次分类。失败/超预算/异常一律收敛到 Unknown。"""
        # 1. 预算预检 — 如果连 1 次 LLM 调用都不剩,直接放弃
        if dispatcher.budget.used_calls >= dispatcher.budget.max_calls:
            return ClassificationResponse.unknown("budget_exhausted_pre_check")

        tools = _exposed_tools(self.agent_def)
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.agent_def.prompt},
            {"role": "user", "content": _build_user_message(ctx)},
        ]

        # 2. tool-use 循环 (最多 max_tool_turns + 1 次 final)
        for turn in range(self.max_tool_turns + 1):
            try:
                resp = self.client.create_completion(messages=messages, tools=tools)
            except Exception as e:  # noqa: BLE001 — LLM 错都吃掉,降级为 Unknown
                log.warning("H4 LLM call failed: %s", e)
                return ClassificationResponse.unknown(f"llm_error: {e}")

            choice = resp.choices[0]
            msg = choice.message
            tool_calls = getattr(msg, "tool_calls", None)

            # 没要工具 → 这就是最终回答
            if not tool_calls:
                return _parse_response(msg.content or "", ctx)

            # 已用满 turn,但模型还在要工具 → 强制收敛
            if turn >= self.max_tool_turns:
                log.info("H4 tool turn cap reached; forcing Unknown")
                return ClassificationResponse.unknown("tool_turn_cap")

            # 把 assistant 的 tool_call 消息回填,然后逐个执行 + 回填结果
            messages.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in tool_calls
                ],
            })

            for tc in tool_calls:
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                result = dispatcher.call(name, **args)
                payload = (
                    {"ok": True, "data": result.data}
                    if result.ok
                    else {"ok": False, "error": result.error,
                          "error_code": result.error_code}
                )
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": name,
                    "content": json.dumps(payload, ensure_ascii=False),
                })

                # 预算耗尽 → 不再继续 turn
                if result.error_code == "budget_exceeded":
                    return ClassificationResponse.unknown("budget_exceeded_mid_turn")

        # 理论不可达
        return ClassificationResponse.unknown("loop_exited_unexpectedly")
