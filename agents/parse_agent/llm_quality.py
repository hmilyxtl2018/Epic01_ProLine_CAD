"""LLM-based quality assessment for ParseAgent results.

Architecture: Evidence-Grounded Chain-of-Thought (ECoT)
  Layer 1 — Code-side: pre-compute verifiable "evidence anchors" from raw data
  Layer 2 — LLM: structured per-dimension reasoning citing evidence IDs
  Layer 3 — Code-side: post-hoc cross-check LLM claims against actual data

5 evaluation dimensions:
  1. classification_accuracy — Are asset types plausible?
  2. confidence_calibration  — Are confidence scores well-scaled?
  3. coverage                — Are meaningful CAD objects captured?
  4. semantic_richness       — How much domain knowledge is reflected?
  5. actionability           — Can downstream Agents consume this?

Usage:
    evaluator = LLMQualityEvaluator(
        api_key="sk-...",
        base_url="https://xiaoai.plus/v1",
        model="claude-opus-4-6",
    )
    result = evaluator.evaluate(site_model_dict, meta_dict)
    # result.score          — LLMQualityScore
    # result.evidence       — code-computed facts the LLM saw
    # result.verification   — post-hoc check of LLM claims
"""

from __future__ import annotations

import json
import math
import re
import random
from collections import Counter
from dataclasses import dataclass, field, asdict
from typing import Any

from openai import OpenAI

# ── 采样参数 ──
MAX_SAMPLE_PER_TYPE = 8
MAX_LOW_CONF_SAMPLE = 10
LOW_CONF_THRESHOLD = 0.4
SAMPLE_SEED = 42  # 固定种子 → 可复现


# ════════════════ 数据结构 ════════════════


@dataclass
class DimensionJudgment:
    """单个评估维度的结构化推理。"""
    score: float = 0.0
    confidence: float = 0.0            # LLM 对自身判断的置信度 0-1
    evidence_ids: list[str] = field(default_factory=list)  # 引用的 evidence anchor ID
    observation: str = ""              # 从数据中直接看到的事实
    inference: str = ""                # 从事实推理出的结论
    uncertainty: str = ""              # 不确定性来源说明


@dataclass
class LLMQualityScore:
    """LLM 返回的 5 维质量评分 (0‒1) + 结构化推理链。"""
    classification_accuracy: float = 0.0
    confidence_calibration: float = 0.0
    coverage: float = 0.0
    semantic_richness: float = 0.0
    actionability: float = 0.0
    overall: float = 0.0
    # 结构化推理链 (每维度独立)
    judgments: dict[str, DimensionJudgment] = field(default_factory=dict)
    missed_types: list[str] = field(default_factory=list)
    suspicious_assets: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    raw_reasoning: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class EvidenceAnchor:
    """代码侧预计算的可验证事实，作为 LLM 推理的锚点。"""
    id: str                   # e.g. "E01", "E02" — LLM 在推理中引用
    category: str             # "type_dist" | "coord_stat" | "layer_stat" | "confidence_stat"
    fact: str                 # 人类可读描述
    value: Any = None         # 结构化值 (可选)


@dataclass
class VerificationResult:
    """代码侧对 LLM 输出的后验交叉检查。"""
    claim: str
    verdict: str              # "CONFIRMED" | "UNVERIFIABLE" | "CONTRADICTED"
    actual_value: Any = None
    detail: str = ""


@dataclass
class ECoTResult:
    """完整的 Evidence-Grounded Chain-of-Thought 评估结果。"""
    score: LLMQualityScore
    evidence: list[EvidenceAnchor] = field(default_factory=list)
    verification: list[VerificationResult] = field(default_factory=list)
    sample_size: int = 0
    total_assets: int = 0
    sampling_coverage: float = 0.0     # sample_size / total_assets

    def to_dict(self) -> dict:
        return asdict(self)


# ════════════════ Layer 1: 代码侧事实预计算 ════════════════


def _stratified_sample(assets: list[dict], seed: int = SAMPLE_SEED) -> list[dict]:
    """分层采样：每种 type 最多 MAX_SAMPLE_PER_TYPE + 低置信度补充。

    固定 seed 确保可复现。
    """
    rng = random.Random(seed)
    by_type: dict[str, list[dict]] = {}
    low_conf: list[dict] = []
    for a in assets:
        t = a.get("type", "Other")
        by_type.setdefault(t, []).append(a)
        if a.get("confidence", 1.0) < LOW_CONF_THRESHOLD:
            low_conf.append(a)

    sample: list[dict] = []
    for t, items in sorted(by_type.items()):  # sorted → 确定性遍历
        k = min(MAX_SAMPLE_PER_TYPE, len(items))
        sample.extend(rng.sample(items, k))

    seen = {a.get("asset_guid") for a in sample}
    extra = [a for a in low_conf if a.get("asset_guid") not in seen]
    sample.extend(rng.sample(extra, min(MAX_LOW_CONF_SAMPLE, len(extra))))
    return sample


def _slim_asset(a: dict) -> dict:
    """精简 asset，保留评估所需字段 (含 block_name)。"""
    rec = {
        "type": a.get("type"),
        "confidence": a.get("confidence"),
        "layer": a.get("layer"),
        "coords": a.get("coords"),
    }
    if a.get("block_name"):
        rec["block_name"] = a["block_name"]
    return rec


def _compute_evidence_anchors(
    assets: list[dict],
    meta: dict,
    links: list[dict] | None = None,
) -> list[EvidenceAnchor]:
    """从原始数据预计算可验证事实，供 LLM 推理引用。"""
    anchors: list[EvidenceAnchor] = []
    total = len(assets)
    links = links or []

    # E01: 类型分布
    type_dist = dict(Counter(a.get("type", "?") for a in assets).most_common())
    other_count = type_dist.get("Other", 0)
    other_ratio = round(other_count / total, 4) if total else 0
    anchors.append(EvidenceAnchor(
        id="E01", category="type_dist",
        fact=f"Type distribution: {type_dist}. Other ratio: {other_ratio:.1%} ({other_count}/{total}).",
        value={"distribution": type_dist, "other_ratio": other_ratio},
    ))

    # E02: 图层分布 (top 15)
    layer_dist = dict(Counter(a.get("layer", "?") for a in assets).most_common(15))
    anchors.append(EvidenceAnchor(
        id="E02", category="layer_stat",
        fact=f"Top 15 layers: {layer_dist}.",
        value=layer_dist,
    ))

    # E03: 置信度统计
    confs = [a.get("confidence", 0) for a in assets]
    if confs:
        avg_c = sum(confs) / len(confs)
        low_count = sum(1 for c in confs if c < LOW_CONF_THRESHOLD)
        variance = sum((c - avg_c) ** 2 for c in confs) / len(confs)
        stdev_c = math.sqrt(variance)
        anchors.append(EvidenceAnchor(
            id="E03", category="confidence_stat",
            fact=(
                f"Confidence: avg={avg_c:.3f}, stdev={stdev_c:.3f}, "
                f"min={min(confs):.3f}, max={max(confs):.3f}, "
                f"below {LOW_CONF_THRESHOLD}: {low_count}/{total} ({low_count/total:.1%})."
            ),
            value={"avg": round(avg_c, 4), "stdev": round(stdev_c, 4),
                   "low_count": low_count, "low_ratio": round(low_count / total, 4) if total else 0},
        ))

    # E04: 坐标统计 — 原点实体 + 离群点
    origin_count = 0
    has_coords_count = 0
    xs, ys = [], []
    for a in assets:
        c = a.get("coords", {})
        if not c:
            continue
        has_coords_count += 1
        x, y = c.get("x", 0), c.get("y", 0)
        if x == 0 and y == 0:
            origin_count += 1
        xs.append(x)
        ys.append(y)
    if xs:
        xs_sorted = sorted(xs)
        ys_sorted = sorted(ys)
        n = len(xs_sorted)
        p5_x, p95_x = xs_sorted[int(n * 0.05)], xs_sorted[int(n * 0.95)]
        p5_y, p95_y = ys_sorted[int(n * 0.05)], ys_sorted[int(n * 0.95)]
        anchors.append(EvidenceAnchor(
            id="E04", category="coord_stat",
            fact=(
                f"Coords: {has_coords_count}/{total} have coords, "
                f"{origin_count} at exact (0,0) ({origin_count/total:.1%}). "
                f"X range [P5..P95]: [{p5_x:.0f}..{p95_x:.0f}], "
                f"Y range [P5..P95]: [{p5_y:.0f}..{p95_y:.0f}]."
            ),
            value={"origin_count": origin_count, "origin_ratio": round(origin_count / total, 4) if total else 0,
                   "x_p5": p5_x, "x_p95": p95_x, "y_p5": p5_y, "y_p95": p95_y},
        ))

    # E05: 采样率
    sample_size = min(
        sum(min(MAX_SAMPLE_PER_TYPE, v) for v in Counter(a.get("type", "?") for a in assets).values())
        + MAX_LOW_CONF_SAMPLE,
        total,
    )
    anchors.append(EvidenceAnchor(
        id="E05", category="sampling",
        fact=f"LLM sees ~{sample_size} sampled assets out of {total} total ({sample_size/total:.1%} coverage)." if total else "No assets.",
        value={"sample_size": sample_size, "total": total,
               "coverage": round(sample_size / total, 4) if total else 0},
    ))

    # E06: 文件上下文
    filename = meta.get("filename", "?")
    anchors.append(EvidenceAnchor(
        id="E06", category="file_context",
        fact=f"Filename: '{filename}', size: {meta.get('file_bytes', 0)} bytes.",
        value={"filename": filename},
    ))

    # E07: link 统计 (类型分布 + equipment→zone 平均度)
    # NOTE: OntologyLink 序列化字段是 "link_type" 而非 "type"
    link_types = Counter(l.get("link_type", "?") for l in links)
    located_in = link_types.get("LOCATED_IN", 0)
    equip_count = sum(1 for a in assets if a.get("type") == "Equipment")
    zone_count = sum(1 for a in assets if a.get("type") == "Zone")
    avg_zones_per_equip = round(located_in / equip_count, 2) if equip_count else 0
    anchors.append(EvidenceAnchor(
        id="E07", category="link_stat",
        fact=(
            f"Links: total={len(links)}, by_type={dict(link_types)}. "
            f"LOCATED_IN={located_in} over Equipment={equip_count} × Zone={zone_count} "
            f"→ avg {avg_zones_per_equip} zones per equipment "
            f"(>1.0 suggests Cartesian-product explosion, 0 suggests missing spatial context)."
        ),
        value={
            "total": len(links),
            "by_type": dict(link_types),
            "located_in": located_in,
            "equip_count": equip_count,
            "zone_count": zone_count,
            "avg_zones_per_equip": avg_zones_per_equip,
        },
    ))

    # E08: block_name 覆盖率 + top block names
    with_block = [a for a in assets if a.get("block_name")]
    block_coverage = round(len(with_block) / total, 4) if total else 0
    top_blocks = dict(Counter(a["block_name"] for a in with_block).most_common(10))
    anchors.append(EvidenceAnchor(
        id="E08", category="block_stat",
        fact=(
            f"Block-name coverage: {len(with_block)}/{total} ({block_coverage:.1%}) "
            f"have block_name. Top 10 block names: {top_blocks}."
        ),
        value={"with_block": len(with_block), "coverage": block_coverage, "top_blocks": top_blocks},
    ))

    return anchors


# ════════════════ Layer 2: LLM 结构化推理 ════════════════

# overall 由代码侧加权计算 (不交给 LLM)
DIMENSION_WEIGHTS = {
    "classification_accuracy": 0.30,
    "confidence_calibration": 0.20,
    "coverage": 0.25,
    "semantic_richness": 0.10,
    "actionability": 0.15,
}

SYSTEM_PROMPT = """\
You are a senior CAD/factory-layout engineer reviewing the output of an \
automated DWG parsing agent (ParseAgent). The agent extracts entities from \
DWG drawings and classifies them as: Equipment, Conveyor, LiftingPoint, \
Zone, or Other.

You will receive:
  * EVIDENCE ANCHORS (E01-E08): pre-computed verifiable facts about the data
      - E01 type distribution, E02 top layers, E03 confidence stats,
      - E04 coordinate stats (incl. (0,0) ratio), E05 sampling coverage,
      - E06 file context, E07 link statistics, E08 block-name coverage.
  * Rule-based quality stats
  * A stratified asset sample with type, confidence, layer, coords, block_name

## YOUR TASK

For EACH of the 5 dimensions, provide a structured judgment:
  1. "observation" - What you DIRECTLY see in the evidence/sample (cite Exx IDs)
  2. "inference" - What you CONCLUDE from the observations
  3. "uncertainty" - What you CANNOT determine from the given data
  4. "score" - 0.0 to 1.0
  5. "confidence" - Your own confidence in this score (0.0 to 1.0)
  6. "evidence_ids" - List of Exx IDs you relied on

SCORING CALIBRATION:
  0.8-1.0: Production-grade. Taxonomy covers >80% entity types, confidence well-separated.
  0.5-0.8: Usable with manual review. classified_ratio >50%, few false positives.
  0.2-0.5: Partial value. Some types correct, many missed or misclassified.
  0.0-0.2: Near-failure. Classification mostly wrong or everything is Other.

IMPORTANT:
  - ALWAYS cite evidence IDs (E01, E02, ...) in your observations.
  - Distinguish between "I see this in the data" vs "I infer this from the filename".
  - If sample coverage (E05) is low, LOWER your confidence accordingly.
  - "missed_types" - real-world types you'd expect given the factory type.
  - "suspicious_assets" - cite specific layers/coords from the sample (max 5).
  - "recommendations" - concrete, actionable improvements (max 5).
  - Do NOT compute "overall". It will be calculated by code.
  - Respond ONLY with valid JSON. No markdown fences, no extra text.

JSON SCHEMA:
{
  "judgments": {
    "classification_accuracy": {
      "score": <float 0-1>,
      "confidence": <float 0-1>,
      "evidence_ids": ["E01", ...],
      "observation": "<what I see - cite Exx>",
      "inference": "<what I conclude>",
      "uncertainty": "<what I cannot determine>"
    },
    "confidence_calibration": { "score": 0, "confidence": 0, "evidence_ids": [], "observation": "", "inference": "", "uncertainty": "" },
    "coverage": { "score": 0, "confidence": 0, "evidence_ids": [], "observation": "", "inference": "", "uncertainty": "" },
    "semantic_richness": { "score": 0, "confidence": 0, "evidence_ids": [], "observation": "", "inference": "", "uncertainty": "" },
    "actionability": { "score": 0, "confidence": 0, "evidence_ids": [], "observation": "", "inference": "", "uncertainty": "" }
  },
  "missed_types": ["<string>", ...],
  "suspicious_assets": ["<string>", ...],
  "recommendations": ["<string>", ...]
}
"""


def _build_user_message(
    evidence: list[EvidenceAnchor],
    quality_stats: dict,
    asset_sample: list[dict],
) -> str:
    parts = [
        "## Evidence Anchors (pre-computed, verifiable)",
    ]
    for e in evidence:
        parts.append(f"**{e.id}** [{e.category}]: {e.fact}")
    parts.append("")
    parts.append("## Rule-Based Quality Stats")
    parts.append(json.dumps(quality_stats, indent=2))
    parts.append("")
    parts.append(f"## Stratified Asset Sample ({len(asset_sample)} items)")
    parts.append(json.dumps(asset_sample, ensure_ascii=False, indent=2))
    return "\n".join(parts)


# ════════════════ Layer 3: 代码侧后验验证 ════════════════


def _verify_claims(
    data: dict,
    evidence: list[EvidenceAnchor],
    assets: list[dict],
) -> list[VerificationResult]:
    """交叉检查 LLM 输出中的可验证声明。"""
    results: list[VerificationResult] = []
    ev_map = {e.id: e for e in evidence}

    # Check 1: LLM 引用的 evidence_ids 是否存在
    judgments = data.get("judgments", {})
    for dim, j in judgments.items():
        for eid in j.get("evidence_ids", []):
            if eid not in ev_map:
                results.append(VerificationResult(
                    claim=f"{dim} cites {eid}",
                    verdict="CONTRADICTED",
                    detail=f"Evidence ID '{eid}' does not exist. Valid IDs: {list(ev_map.keys())}.",
                ))

    # Check 2: suspicious_assets 中提到的图层名是否真实存在
    actual_layers = {a.get("layer", "") for a in assets}
    for sus in data.get("suspicious_assets", []):
        # 尝试从文本中提取单引号或 'layer ...' 模式中的层名
        layer_mentions = re.findall(r"layer\s+['\"]?([^'\"\\s,\u2014]+)", sus, re.IGNORECASE)
        layer_mentions += re.findall(r"'([^']+)'", sus)
        for lm in layer_mentions:
            if lm in actual_layers:
                results.append(VerificationResult(
                    claim=f"Suspicious asset mentions layer '{lm}'",
                    verdict="CONFIRMED",
                    actual_value=lm,
                    detail=f"Layer '{lm}' exists in the dataset.",
                ))
            else:
                match = any(lm.upper() == al.upper() for al in actual_layers)
                results.append(VerificationResult(
                    claim=f"Suspicious asset mentions layer '{lm}'",
                    verdict="CONFIRMED" if match else "UNVERIFIABLE",
                    detail=f"Layer '{lm}' {'matched (case-insensitive)' if match else 'not found in dataset (may be from unseen entities)'}.",
                ))

    # Check 3: 每个维度是否都提供了 evidence_ids
    for dim in DIMENSION_WEIGHTS:
        j = judgments.get(dim, {})
        if not j.get("evidence_ids"):
            results.append(VerificationResult(
                claim=f"{dim} judgment has no evidence citations",
                verdict="CONTRADICTED",
                detail="Judgment lacks grounding \u2014 no evidence IDs cited.",
            ))

    return results


# ════════════════ 主评估器 ════════════════


class LLMQualityEvaluator:
    """ECoT 质量评估器 \u2014 代码预计算 \u2192 LLM 推理 \u2192 代码验证。"""

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "",
        model: str = "",
        temperature: float = 0.0,
        timeout: float = 120.0,
    ):
        import os
        self._api_key = api_key or os.getenv("ANTHROPIC_AUTH_TOKEN", "") or os.getenv("OPENAI_API_KEY", "")
        self._base_url = base_url or os.getenv("ANTHROPIC_BASE_URL", "")
        self._model = model or os.getenv("ANTHROPIC_MODEL", "") or os.getenv("LLM_MODEL", "gpt-4o")
        self._temperature = temperature
        self._timeout = timeout
        self._client: OpenAI | None = None

    @property
    def client(self) -> OpenAI:
        if self._client is None:
            if not self._api_key:
                raise RuntimeError("No API key. Set ANTHROPIC_AUTH_TOKEN or OPENAI_API_KEY.")
            kwargs: dict[str, Any] = {"api_key": self._api_key, "timeout": self._timeout}
            if self._base_url:
                url = self._base_url.rstrip("/")
                if not url.endswith("/v1"):
                    url += "/v1"
                kwargs["base_url"] = url
            # Bypass system proxy (e.g., Clash at 127.0.0.1:7897) that can hang
            # on large ECoT prompts (~13K chars). System proxy is auto-read by
            # httpx via trust_env=True (default). We explicitly disable it.
            import httpx as _httpx
            kwargs["http_client"] = _httpx.Client(trust_env=False, timeout=self._timeout)
            self._client = OpenAI(**kwargs)
        return self._client

    def evaluate(self, site_model: dict, meta: dict) -> ECoTResult:
        """对单个 DWG 的解析结果做 ECoT 质量评估。

        返回 ECoTResult，包含:
          - score: 5 维分数 + overall (代码加权)
          - evidence: 代码预计算事实
          - verification: LLM 声明的后验检查
        """
        assets = site_model.get("assets", [])
        links = site_model.get("links", [])
        quality_stats = site_model.get("statistics", {}).get("quality", {})

        # Layer 1: 代码侧预计算 evidence anchors
        evidence = _compute_evidence_anchors(assets, meta, links)

        sample = _stratified_sample(assets)
        slim_sample = [_slim_asset(a) for a in sample]

        user_msg = _build_user_message(evidence, quality_stats, slim_sample)

        # Layer 2: LLM 结构化推理 (带 retry:上游 xiaoai.plus 偶发挂起,短超时+重试更可靠)
        import time as _time
        last_exc: Exception | None = None
        response = None
        for attempt in range(3):
            try:
                response = self.client.chat.completions.create(
                    model=self._model,
                    temperature=self._temperature,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_msg},
                    ],
                    timeout=90.0,
                )
                break
            except Exception as exc:
                last_exc = exc
                if attempt < 2:
                    _time.sleep(3 * (attempt + 1))
        if response is None:
            raise RuntimeError(f"LLM call failed after 3 attempts: {last_exc}")

        raw = response.choices[0].message.content or "{}"
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())

        data = json.loads(text)

        # 解析结构化 judgments
        judgments: dict[str, DimensionJudgment] = {}
        dim_scores: dict[str, float] = {}
        for dim in DIMENSION_WEIGHTS:
            j_raw = data.get("judgments", {}).get(dim, {})
            judgments[dim] = DimensionJudgment(
                score=float(j_raw.get("score", 0)),
                confidence=float(j_raw.get("confidence", 0)),
                evidence_ids=j_raw.get("evidence_ids", []),
                observation=j_raw.get("observation", ""),
                inference=j_raw.get("inference", ""),
                uncertainty=j_raw.get("uncertainty", ""),
            )
            dim_scores[dim] = judgments[dim].score

        # overall 由代码按固定权重计算 → 可复现
        overall = round(
            sum(DIMENSION_WEIGHTS[d] * dim_scores.get(d, 0) for d in DIMENSION_WEIGHTS),
            4,
        )

        score = LLMQualityScore(
            classification_accuracy=dim_scores.get("classification_accuracy", 0),
            confidence_calibration=dim_scores.get("confidence_calibration", 0),
            coverage=dim_scores.get("coverage", 0),
            semantic_richness=dim_scores.get("semantic_richness", 0),
            actionability=dim_scores.get("actionability", 0),
            overall=overall,
            judgments=judgments,
            missed_types=data.get("missed_types", []),
            suspicious_assets=data.get("suspicious_assets", []),
            recommendations=data.get("recommendations", []),
            raw_reasoning=json.dumps(data.get("judgments", {}), ensure_ascii=False),
        )

        # Layer 3: 代码侧后验验证
        verification = _verify_claims(data, evidence, assets)

        sample_size = len(sample)
        total = len(assets)
        return ECoTResult(
            score=score,
            evidence=evidence,
            verification=verification,
            sample_size=sample_size,
            total_assets=total,
            sampling_coverage=round(sample_size / total, 4) if total else 0,
        )
