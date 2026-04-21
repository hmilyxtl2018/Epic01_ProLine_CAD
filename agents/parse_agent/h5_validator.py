"""Hook H5 — LLM 响应语义校验器。

H4 LLM 分类输出之后, 在写入 SiteModel 之前, 对响应做硬性语义校验:
  R1. type ∈ AssetType 枚举                (H4 已查, 这里再防御)
  R2. confidence ∈ [0, 1]                  (H4 已查, 这里再防御)
  R3. evidence_keywords ⊆ input_tokens     ★ H5 核心: 防 hallucination
  R4. evidence_keywords 非空 (除非 type=Unknown)

action_on_fail: discard_response;keep_H3
  即: 任何一条失败就丢弃 LLM 响应, 回退到 H3 规则分类的结果。

参考:
- agents/parse_agent/agent.json hooks.H5_response_validator
- agents/parse_agent/h4_llm_classifier.py
- ExcPlan/parse_agent_ga_execution_plan.md §4 S2-T2
"""
from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass

from agents.parse_agent.h4_llm_classifier import (
    ClassificationResponse,
    ClassifyContext,
)

log = logging.getLogger(__name__)

_VALID_TYPES = {
    "Equipment", "Conveyor", "LiftingPoint", "Zone",
    "Annotation", "Other", "Unknown",
}

# 拆词分隔符: 空格 / 中文标点 / CAD 块名常用分隔
_TOKEN_SPLIT = re.compile(r"[\s\-_/\\.,;:()\[\]{}|+#@*]+")


@dataclass
class ValidationResult:
    ok: bool
    rule: str = ""
    detail: str = ""

    @classmethod
    def pass_(cls) -> "ValidationResult":
        return cls(ok=True)

    @classmethod
    def fail(cls, rule: str, detail: str) -> "ValidationResult":
        return cls(ok=False, rule=rule, detail=detail)


def _normalize(s: str) -> str:
    """大小写折叠 + Unicode NFKC, 用于不区分大小写的子串匹配。"""
    return unicodedata.normalize("NFKC", s).casefold().strip()


def _tokenize(s: str) -> set[str]:
    """把一个字符串拆成可能的子词 token 集合 (含原串)。"""
    n = _normalize(s)
    if not n:
        return set()
    parts = {p for p in _TOKEN_SPLIT.split(n) if p}
    parts.add(n)
    return parts


def _build_input_token_corpus(ctx: ClassifyContext) -> set[str]:
    """合并 block_name + layer + sample_labels → 归一化 token 集合。"""
    corpus: set[str] = set()
    for raw in ctx.input_tokens():
        corpus |= _tokenize(raw)
    return corpus


def _keyword_grounded(kw: str, corpus: set[str], full_blob: str) -> bool:
    """单个 keyword 是否被输入支撑。

    支撑判定 (任一即可):
      A. 归一化后是 corpus 中某 token 的子串/超串
      B. 归一化后作为子串出现在 full_blob 中 (允许跨 token 匹配)
    """
    n = _normalize(kw)
    if not n:
        return False
    # A. token 包含
    for t in corpus:
        if n in t or t in n:
            return True
    # B. 跨 token 子串匹配 (block_name 常带连字符,LLM 可能给"珩磨" 匹配 "珩磨机_op170")
    return n in full_blob


def validate(
    response: ClassificationResponse, ctx: ClassifyContext,
) -> ValidationResult:
    """对一个 H4 响应做完整 H5 校验。失败 = 丢弃响应, 回退 H3。"""
    # R1. type 枚举 (防御)
    if response.type not in _VALID_TYPES:
        return ValidationResult.fail("R1_type_enum", f"type={response.type!r}")

    # R2. confidence 范围 (防御)
    if not 0.0 <= response.confidence <= 1.0:
        return ValidationResult.fail(
            "R2_confidence_range", f"confidence={response.confidence}",
        )

    # Unknown 是合法的"放弃"信号 — 不要求 evidence
    if response.type == "Unknown":
        return ValidationResult.pass_()

    # R4. 非 Unknown 必须有证据
    if not response.evidence_keywords:
        return ValidationResult.fail(
            "R4_evidence_required",
            f"type={response.type} but evidence_keywords=[]",
        )

    # R3. evidence_keywords ⊆ input_tokens (核心防 hallucination)
    corpus = _build_input_token_corpus(ctx)
    full_blob = _normalize(" ".join(ctx.input_tokens()))

    if not corpus and not full_blob:
        # 极端: 输入完全为空, evidence 必然 hallucinated
        return ValidationResult.fail(
            "R3_evidence_grounded", "input is empty but evidence_keywords non-empty",
        )

    ungrounded = [
        kw for kw in response.evidence_keywords
        if not _keyword_grounded(kw, corpus, full_blob)
    ]
    if ungrounded:
        return ValidationResult.fail(
            "R3_evidence_grounded",
            f"keywords not in input: {ungrounded}",
        )

    return ValidationResult.pass_()


def apply_h5(
    llm_response: ClassificationResponse,
    ctx: ClassifyContext,
    h3_fallback: ClassificationResponse,
) -> tuple[ClassificationResponse, ValidationResult]:
    """H5 主入口: 校验 LLM 响应, 失败回退 H3 结果。

    Returns:
        (final_response, validation_result)
        - 通过: (llm_response, pass)
        - 失败: (h3_fallback marked classifier_kind='rule_h3_after_h5_reject', fail)
    """
    result = validate(llm_response, ctx)
    if result.ok:
        return llm_response, result

    log.info(
        "H5 rejected LLM response (rule=%s, detail=%s); falling back to H3 rule classifier",
        result.rule, result.detail,
    )
    fallback = ClassificationResponse(
        type=h3_fallback.type,
        sub_type=h3_fallback.sub_type,
        confidence=h3_fallback.confidence,
        evidence_keywords=h3_fallback.evidence_keywords,
        classifier_kind="rule_h3_after_h5_reject",
        error=f"h5_rejected:{result.rule}",
    )
    return fallback, result
