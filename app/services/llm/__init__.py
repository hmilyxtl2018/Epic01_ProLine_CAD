"""LLM service layer.

Provides a single `LLMClient` abstraction with pluggable providers:

  * `stub`   — deterministic offline heuristic (default; tests + air-gapped).
  * `openai` — OpenAI-compatible HTTP API (real LLM via env vars).

Every call returns a `LLMResult` carrying `text`, `tokens_in/out`,
`latency_ms`, `model`, `prompt_version`, and is logged via `audit.log_call`
into `audit_log_actions` so downstream UI can replay decisions.
"""

from .provider import LLMClient, LLMResult, get_default_client
from .embeddings import EmbeddingClient, get_default_embedder

__all__ = [
    "LLMClient",
    "LLMResult",
    "get_default_client",
    "EmbeddingClient",
    "get_default_embedder",
]
