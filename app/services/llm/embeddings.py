"""Embedding helpers.

The `stub` embedder is a deterministic 64-dim hash-based vector that lets
the pipeline run cosine-style similarity offline. Swap for a real
embedding provider via env (`EMBED_PROVIDER=openai`, `EMBED_MODEL=...`).
"""

from __future__ import annotations

import hashlib
import math
import os
from typing import Iterable, Sequence


class EmbeddingClient:
    name = "base"
    dim = 64

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        raise NotImplementedError

    @staticmethod
    def cosine(a: Sequence[float], b: Sequence[float]) -> float:
        if not a or not b:
            return 0.0
        num = sum(x * y for x, y in zip(a, b))
        da = math.sqrt(sum(x * x for x in a)) or 1.0
        db = math.sqrt(sum(y * y for y in b)) or 1.0
        return num / (da * db)


class StubEmbedder(EmbeddingClient):
    """Hash-bucket embedder: same input -> same vector, no network."""

    name = "stub"
    dim = 64

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for t in texts:
            v = [0.0] * self.dim
            tokens = _shingle((t or "").lower(), n=3)
            for tok in tokens:
                h = int(hashlib.blake2s(tok.encode("utf-8"), digest_size=8).hexdigest(), 16)
                idx = h % self.dim
                sign = 1.0 if (h >> 63) & 1 == 0 else -1.0
                v[idx] += sign
            # L2 normalise
            n = math.sqrt(sum(x * x for x in v)) or 1.0
            out.append([x / n for x in v])
        return out


def _shingle(s: str, n: int = 3) -> list[str]:
    s = s.strip()
    if len(s) <= n:
        return [s] if s else []
    return [s[i : i + n] for i in range(len(s) - n + 1)]


def get_default_embedder() -> EmbeddingClient:
    # Real provider plug-in point; for now stub is the only impl.
    name = os.getenv("EMBED_PROVIDER", "stub").lower()
    if name == "stub":
        return StubEmbedder()
    return StubEmbedder()
