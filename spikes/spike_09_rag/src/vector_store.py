"""向量存储 — Stub"""


class VectorStore:
    total_chunks: int = 0

    def add_chunks(self, chunks: list, source: str = ""):
        raise NotImplementedError
