"""中文分块器 — Stub"""


class ChineseTextChunker:
    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 50, separators: list = None):
        pass

    def split(self, text: str) -> list[str]:
        raise NotImplementedError
