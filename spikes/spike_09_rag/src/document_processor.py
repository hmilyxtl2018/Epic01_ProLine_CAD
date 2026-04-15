"""文档处理器 — Stub"""
from dataclasses import dataclass


@dataclass
class Chunk:
    source: str = ""
    text: str = ""
    chunk_index: int = 0
    embedding: list = None


class DocumentProcessor:
    def process(self, doc_path) -> list[Chunk]:
        raise NotImplementedError
