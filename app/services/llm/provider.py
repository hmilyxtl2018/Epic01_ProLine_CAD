"""Provider abstraction for LLM text generation.

Default provider is `stub` — a fast, deterministic, dependency-free
"LLM" that mirrors the real API shape so the entire enrichment pipeline
runs offline (CI, dev, air-gapped). Switch to a real model via:

    LLM_PROVIDER=openai
    LLM_API_KEY=sk-...
    LLM_BASE_URL=https://api.openai.com/v1   # or compat endpoint
    LLM_MODEL=gpt-4o-mini
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LLMResult:
    text: str
    parsed: dict[str, Any] | None = None
    model: str = "stub"
    prompt_version: str = "v1"
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0
    fallback: bool = False
    error: str | None = None
    evidence: list[dict[str, Any]] = field(default_factory=list)


class LLMClient:
    """Abstract base. Subclasses implement `generate_json`."""

    name: str = "base"

    def generate_json(
        self,
        *,
        system: str,
        user: str,
        prompt_version: str,
        schema_hint: dict[str, Any] | None = None,
        stub_fn=None,
    ) -> LLMResult:
        raise NotImplementedError


class StubProvider(LLMClient):
    """Calls `stub_fn(user) -> dict` for offline deterministic outputs.

    The pipeline modules pass a Python callable that mimics what the
    LLM would produce. Result is wrapped to look like a real call.
    """

    name = "stub"

    def generate_json(
        self,
        *,
        system: str,
        user: str,
        prompt_version: str,
        schema_hint: dict[str, Any] | None = None,
        stub_fn=None,
    ) -> LLMResult:
        t0 = time.monotonic()
        if stub_fn is None:
            return LLMResult(
                text="{}",
                parsed={},
                model="stub-noop",
                prompt_version=prompt_version,
                latency_ms=0,
                fallback=True,
                error="no stub_fn provided",
            )
        try:
            parsed = stub_fn()
            if not isinstance(parsed, dict):
                parsed = {"value": parsed}
        except Exception as e:  # noqa: BLE001
            return LLMResult(
                text="{}",
                parsed={},
                model="stub-error",
                prompt_version=prompt_version,
                latency_ms=int((time.monotonic() - t0) * 1000),
                fallback=True,
                error=f"{type(e).__name__}: {e}",
            )
        text = json.dumps(parsed, ensure_ascii=False)
        return LLMResult(
            text=text,
            parsed=parsed,
            model="stub-heuristic-v1",
            prompt_version=prompt_version,
            tokens_in=len(user) // 4,
            tokens_out=len(text) // 4,
            latency_ms=int((time.monotonic() - t0) * 1000),
        )


class OpenAIProvider(LLMClient):
    """Thin OpenAI-compatible JSON-mode caller.

    Always falls back to the `stub_fn` result on any error so the
    pipeline never hard-fails because the upstream model is down.
    """

    name = "openai"

    def __init__(self) -> None:
        self.api_key = os.getenv("LLM_API_KEY") or ""
        self.base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self.model = os.getenv("LLM_MODEL", "gpt-4o-mini")
        self.timeout = float(os.getenv("LLM_TIMEOUT_S", "30"))

    def generate_json(
        self,
        *,
        system: str,
        user: str,
        prompt_version: str,
        schema_hint: dict[str, Any] | None = None,
        stub_fn=None,
    ) -> LLMResult:
        t0 = time.monotonic()
        if not self.api_key:
            # No key configured — degrade silently to stub.
            stub = StubProvider().generate_json(
                system=system, user=user, prompt_version=prompt_version, stub_fn=stub_fn
            )
            stub.fallback = True
            stub.error = "no LLM_API_KEY"
            return stub
        try:
            import httpx

            r = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "response_format": {"type": "json_object"},
                    "temperature": 0.1,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
                timeout=self.timeout,
            )
            r.raise_for_status()
            body = r.json()
            text = body["choices"][0]["message"]["content"]
            parsed = json.loads(text)
            usage = body.get("usage") or {}
            return LLMResult(
                text=text,
                parsed=parsed,
                model=body.get("model") or self.model,
                prompt_version=prompt_version,
                tokens_in=int(usage.get("prompt_tokens", 0)),
                tokens_out=int(usage.get("completion_tokens", 0)),
                latency_ms=int((time.monotonic() - t0) * 1000),
            )
        except Exception as e:  # noqa: BLE001
            stub = StubProvider().generate_json(
                system=system, user=user, prompt_version=prompt_version, stub_fn=stub_fn
            )
            stub.fallback = True
            stub.error = f"{type(e).__name__}: {e}"
            stub.latency_ms = int((time.monotonic() - t0) * 1000)
            return stub


_PROVIDERS: dict[str, type[LLMClient]] = {
    "stub": StubProvider,
    "openai": OpenAIProvider,
}


def get_default_client() -> LLMClient:
    name = os.getenv("LLM_PROVIDER", "stub").lower()
    cls = _PROVIDERS.get(name, StubProvider)
    return cls()
