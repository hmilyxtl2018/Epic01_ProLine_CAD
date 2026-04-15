"""图层语义映射器 — Stub"""
from dataclasses import dataclass


@dataclass
class ClassificationResult:
    accuracy: float = 0.0
    classified_count: int = 0
    unclassified_count: int = 0
    _category_counts: dict = None

    def category_count(self, category: str) -> int:
        raise NotImplementedError


class LayerSemanticMapper:
    def __init__(self, mapping: dict):
        self.mapping = mapping

    def classify(self, layers: dict) -> ClassificationResult:
        raise NotImplementedError("LayerSemanticMapper.classify 尚未实现")
