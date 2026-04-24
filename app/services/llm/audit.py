"""Audit-log writer for LLM enrichment calls.

Every LLM step in the enrichment pipeline calls `log_call` to append a
row to `audit_log_actions` (action='llm_call'). This is the
human-replay record that backs the UI's "explain this decision" link.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from .provider import LLMResult


def log_call(
    db: Session,
    *,
    mcp_context_id: str,
    step: str,
    result: LLMResult,
    target_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Append one row per LLM call. Best-effort: errors swallowed."""
    payload = {
        "step": step,
        "model": result.model,
        "prompt_version": result.prompt_version,
        "tokens_in": result.tokens_in,
        "tokens_out": result.tokens_out,
        "latency_ms": result.latency_ms,
        "fallback": result.fallback,
        "error": result.error,
        "evidence_count": len(result.evidence),
        **(extra or {}),
    }
    try:
        db.execute(
            text(
                """
                INSERT INTO audit_log_actions (
                    actor, actor_role, action, target_type, target_id,
                    payload, mcp_context_id
                )
                VALUES (
                    :actor, 'agent', 'llm_call', 'enrichment_step', :tid,
                    CAST(:payload AS jsonb), :mcp
                )
                """
            ),
            {
                "actor": f"llm:{result.model}",
                "tid": target_id or step,
                "payload": json.dumps(payload, ensure_ascii=False, default=str),
                "mcp": mcp_context_id,
            },
        )
    except Exception:  # noqa: BLE001
        # never let audit failure break the pipeline
        pass
