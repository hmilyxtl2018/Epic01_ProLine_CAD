"""提取结果评估器 — Stub"""
from dataclasses import dataclass


@dataclass
class EvalMetrics:
    precision: float = 0.0
    recall: float = 0.0
    f1: float = 0.0
    hallucination_count: int = 0
    hallucination_rate: float = 0.0


class ExtractionEvaluator:
    def evaluate(self, extracted: list, gold_standard: dict) -> EvalMetrics:
        raise NotImplementedError

    def check_source_refs(self, constraints: list, document: str) -> float:
        raise NotImplementedError
