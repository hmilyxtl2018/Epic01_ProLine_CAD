"""ConstraintExtractor 阈值与运行参数（T4.2 / T4.0 §G 校验）。

集中所有"决策性数字"以便：

1. 单点修改、单点测试；
2. 通过环境变量在部署期调档（无需改代码 / 重新打包）；
3. 业务影响透明（每个常量写明业务含义与调高/调低的代价）。

环境变量命名前缀 ``EXTRACTOR_``。所有 ENV 缺失或解析失败时回退到默认值，
不抛异常（运维侧错配不应阻塞抽取）。

**调档建议**（见 docs/kg_execution_tasks_v1.md §T4.2）：

- 沈飞冷启动前 3 周：``EXTRACTOR_CONFIDENCE_REJECT=0.30`` 提高召回；
- 文档稳定后：默认 0.40 即可；
- 工艺人员紧张：``EXTRACTOR_CONFIDENCE_REJECT=0.50`` 宁少勿错。
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass


def _env_float(name: str, default: float, *, lo: float = 0.0, hi: float = 1.0) -> float:
    """读取 0..1 区间的浮点 ENV，越界 / NaN / 解析失败回退默认值。"""
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    if math.isnan(value) or math.isinf(value):
        return default
    if value < lo or value > hi:
        return default
    return value


@dataclass(frozen=True, slots=True)
class ExtractorThresholds:
    """ConstraintExtractor 校验/分档阈值的不可变快照。

    通过 :func:`current_thresholds` 在每次抽取调用开始时读取一次，
    本次抽取生命周期内不再变化（避免运维改 ENV 影响进行中的批次）。
    """

    # ── 单条置信度分档（T4.2） ──
    # REJECT < LOW <= MEDIUM < HIGH 必须严格成立；构造时 __post_init__ 校验。
    confidence_reject: float = 0.40
    """单条置信度低于此值 -> 不入库，记 ``rejection_breakdown.low_confidence``。"""

    confidence_low: float = 0.60
    """``[reject, low)`` 入 LOW 桶 -> draft + UI 灰显。"""

    confidence_high: float = 0.85
    """``>= high`` 入 HIGH 桶 -> draft + 评审页置顶。``[low, high)`` 入 MEDIUM 桶。"""

    # ── 整批 G 校验（T4.0 §G，warning 不阻塞） ──
    batch_min_yield: float = 0.20
    """G1：``extracted_count / candidates_count`` 下限。低于触发 ``low_yield`` warning。"""

    batch_min_mean_confidence: float = 0.50
    """G3：已入库 draft 平均置信度下限。低于触发 ``low_mean_confidence`` warning。"""

    def __post_init__(self) -> None:
        if not (0.0 <= self.confidence_reject < self.confidence_low < self.confidence_high <= 1.0):
            raise ValueError(
                "thresholds must satisfy 0 <= reject < low < high <= 1; "
                f"got reject={self.confidence_reject} low={self.confidence_low} high={self.confidence_high}"
            )
        if not (0.0 <= self.batch_min_yield <= 1.0):
            raise ValueError(f"batch_min_yield out of [0,1]: {self.batch_min_yield}")
        if not (0.0 <= self.batch_min_mean_confidence <= 1.0):
            raise ValueError(f"batch_min_mean_confidence out of [0,1]: {self.batch_min_mean_confidence}")


# ── 默认值（与 docs/kg_execution_tasks_v1.md §T4.2 锁定） ──
DEFAULT_CONFIDENCE_REJECT: float = 0.40
DEFAULT_CONFIDENCE_LOW: float = 0.60
DEFAULT_CONFIDENCE_HIGH: float = 0.85
DEFAULT_BATCH_MIN_YIELD: float = 0.20
DEFAULT_BATCH_MIN_MEAN_CONFIDENCE: float = 0.50


def current_thresholds() -> ExtractorThresholds:
    """读取 ENV 旋钮，构造一次性快照。

    无任何 ENV 配置时等价于全部默认值。任意 ENV 解析失败/越界都按默认值兜底，
    不会因配置错误阻塞抽取。
    """
    candidate = ExtractorThresholds(
        confidence_reject=_env_float("EXTRACTOR_CONFIDENCE_REJECT", DEFAULT_CONFIDENCE_REJECT),
        confidence_low=_env_float("EXTRACTOR_CONFIDENCE_LOW", DEFAULT_CONFIDENCE_LOW),
        confidence_high=_env_float("EXTRACTOR_CONFIDENCE_HIGH", DEFAULT_CONFIDENCE_HIGH),
        batch_min_yield=_env_float("EXTRACTOR_BATCH_MIN_YIELD", DEFAULT_BATCH_MIN_YIELD),
        batch_min_mean_confidence=_env_float("EXTRACTOR_BATCH_MIN_MEAN", DEFAULT_BATCH_MIN_MEAN_CONFIDENCE),
    )
    # __post_init__ 校验严格次序；若 ENV 把次序破坏掉（例如 reject>low），
    # 退回全默认而不是抛异常。
    try:
        return candidate
    except ValueError:
        return ExtractorThresholds()


# ── 桶名常量，避免在 extractor.py 里散落 magic string ──
BUCKET_HIGH: str = "high"
BUCKET_MEDIUM: str = "medium"
BUCKET_LOW: str = "low"

# ── 拒收原因键，统一进入 ExtractResponse.rejection_breakdown ──
REJ_JSON_SHAPE: str = "json_shape"
REJ_SCHEMA: str = "schema"
REJ_SPAN_MISMATCH: str = "span_mismatch"
REJ_LOW_CONFIDENCE: str = "low_confidence"
REJ_LLM_SKIPPED: str = "llm_skipped"
REJ_COMPLETENESS: str = "completeness"


__all__: list[str] = [
    "BUCKET_HIGH",
    "BUCKET_LOW",
    "BUCKET_MEDIUM",
    "DEFAULT_BATCH_MIN_MEAN_CONFIDENCE",
    "DEFAULT_BATCH_MIN_YIELD",
    "DEFAULT_CONFIDENCE_HIGH",
    "DEFAULT_CONFIDENCE_LOW",
    "DEFAULT_CONFIDENCE_REJECT",
    "ExtractorThresholds",
    "REJ_COMPLETENESS",
    "REJ_JSON_SHAPE",
    "REJ_LLM_SKIPPED",
    "REJ_LOW_CONFIDENCE",
    "REJ_SCHEMA",
    "REJ_SPAN_MISMATCH",
    "current_thresholds",
]
