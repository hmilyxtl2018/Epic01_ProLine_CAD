"""混合检索器 — Stub"""
from dataclasses import dataclass


@dataclass
class RetrievalResult:
    source: str = ""
    text: str = ""
    score: float = 0.0


class HybridRetriever:
    def __init__(self, store=None, embedding_model=None):
        self.store = store
        self.embedding_model = embedding_model  # 注入 Mock: fn(text) -> list[float]

    def retrieve(self, query: str, top_k: int = 5) -> list[RetrievalResult]:
        raise NotImplementedError
