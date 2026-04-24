"""Enrichment pipeline orchestrator.

Runs steps A–M in order, threading evidence through, recording each
LLM call into `audit_log_actions`, and degrading gracefully when any
step throws (the offending step's output becomes
`{step: <name>, error: <msg>}` and the rest still execute).

Output is a single JSON-able dict that the worker writes under
`output_payload.llm_enrichment`.
"""

from __future__ import annotations

import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Sequence

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..llm.audit import log_call
from ..llm.embeddings import EmbeddingClient, get_default_embedder
from ..llm.provider import LLMClient, LLMResult, get_default_client
from . import semantic as S
from . import quality as Q
from . import sitemodel as SM


@dataclass
class EnrichmentResult:
    sections: dict[str, Any] = field(default_factory=dict)
    timings_ms: dict[str, int] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)
    steps_run: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sections": self.sections,
            "timings_ms": self.timings_ms,
            "errors": self.errors,
            "steps_run": self.steps_run,
            "version": "v1",
        }


def _step(result: EnrichmentResult, name: str, fn):
    t0 = time.monotonic()
    try:
        out = fn()
        result.sections[name] = out
        result.steps_run.append(name)
    except Exception as e:  # noqa: BLE001
        tb = traceback.format_exc(limit=2)
        result.errors[name] = f"{type(e).__name__}: {e}\n{tb}"
    finally:
        result.timings_ms[name] = int((time.monotonic() - t0) * 1000)


def run_enrichment(
    *,
    db: Session,
    mcp_context_id: str,
    fingerprint: dict[str, Any],
    summary: dict[str, Any],
    candidates: Sequence[dict[str, Any]],
    matched_terms: Sequence[dict[str, Any]],
    quarantine_terms: Sequence[dict[str, Any]],
    parse_warnings: Sequence[str],
    site_model_id: str | None,
    llm: LLMClient | None = None,
    embedder: EmbeddingClient | None = None,
) -> EnrichmentResult:
    llm = llm or get_default_client()
    embedder = embedder or get_default_embedder()

    res = EnrichmentResult()

    # ── A. normalize ────────────────────────────────────────────────
    def _step_a():
        sample = [c.get("term_display") or c.get("term_normalized") or "" for c in candidates[:200]]
        items = S.normalize_batch(sample)
        return {
            "items": items[:50],
            "stats": {"input": len(sample), "shown": min(50, len(items))},
            "rationale": "Multi-lingual / encoded-id normaliser. Tiny lexicon today; LLM upgrade adds open-vocab.",
        }

    _step(res, "A_normalize", _step_a)

    # ── B. softmatch (needs gold list) ──────────────────────────────
    def _step_b():
        gold = _fetch_gold_terms(db, limit=500)
        sm = S.softmatch(
            embedder,
            candidates=quarantine_terms[:300],
            gold_terms=gold,
        )
        result = LLMResult(
            text="", parsed={"matches": sm}, model=f"embed:{embedder.name}",
            prompt_version="softmatch-v1", evidence=[{"gold_size": len(gold)}],
        )
        log_call(db, mcp_context_id=mcp_context_id, step="B_softmatch", result=result,
                 extra={"input": len(quarantine_terms[:300]), "gold": len(gold)})
        return {
            "matches": sm[:50],
            "stats": {
                "input": len(quarantine_terms[:300]),
                "gold_size": len(gold),
                "produced": len(sm),
            },
            "thresholds": {"accept": 0.86, "review": 0.65},
        }

    _step(res, "B_softmatch", _step_b)

    # ── C. arbiter ─────────────────────────────────────────────────
    def _step_c():
        sm = (res.sections.get("B_softmatch") or {}).get("matches") or []
        return S.arbitrate(sm)

    _step(res, "C_arbiter", _step_c)

    # ── D. cluster proposals (P0) ─────────────────────────────────
    def _step_d():
        out = S.cluster_proposals(embedder, quarantine=quarantine_terms)
        result = LLMResult(
            text="", parsed=out, model=f"embed:{embedder.name}",
            prompt_version="cluster-v1",
            evidence=[{"k_clusters": len(out.get("proposals", []))}],
        )
        log_call(db, mcp_context_id=mcp_context_id, step="D_cluster_proposals",
                 result=result, extra={"input": len(quarantine_terms),
                                       "proposals": len(out.get("proposals", []))})
        return out

    _step(res, "D_cluster_proposals", _step_d)

    # ── E. block kind ─────────────────────────────────────────────
    def _step_e():
        block_names = summary.get("block_names") or []
        return S.classify_blocks(block_names)

    _step(res, "E_block_kind", _step_e)

    # ── F. quality breakdown ───────────────────────────────────────
    def _step_f():
        return Q.quality_breakdown(
            summary=summary,
            matched_count=len(matched_terms),
            quarantine_count=len(quarantine_terms),
            candidate_count=len(candidates),
            warnings=parse_warnings,
        )

    _step(res, "F_quality_breakdown", _step_f)

    # ── G. root cause ─────────────────────────────────────────────
    def _step_g():
        return Q.root_cause(parse_warnings)

    _step(res, "G_root_cause", _step_g)

    # ── H. audit narrative ────────────────────────────────────────
    def _step_h():
        quality = res.sections.get("F_quality_breakdown") or {}
        return Q.audit_narrative(
            run_id=mcp_context_id,
            fingerprint=fingerprint,
            summary=summary,
            matched_count=len(matched_terms),
            quarantine_count=len(quarantine_terms),
            site_model_id=site_model_id,
            quality=quality,
            enrichment_steps=list(res.steps_run),
        )

    _step(res, "H_audit_narrative", _step_h)

    # ── I. self-check ─────────────────────────────────────────────
    def _step_i():
        quality = res.sections.get("F_quality_breakdown") or {}
        return Q.self_check(
            matched_count=len(matched_terms),
            quarantine_count=len(quarantine_terms),
            candidate_count=len(candidates),
            quality_overall=float(quality.get("overall") or 0.0),
            parse_warnings=parse_warnings,
        )

    _step(res, "I_self_check", _step_i)

    # ── J. site describe ──────────────────────────────────────────
    def _step_j():
        return SM.site_describe(
            filename=fingerprint.get("filename") or "",
            summary=summary,
        )

    _step(res, "J_site_describe", _step_j)

    # ── K. asset extract (stub) ───────────────────────────────────
    def _step_k():
        return SM.asset_extract_stub(summary=summary, matched_terms=matched_terms)

    _step(res, "K_asset_extract", _step_k)

    # ── L. geometry anomaly ───────────────────────────────────────
    def _step_l():
        return SM.geom_anomaly(summary=summary)

    _step(res, "L_geom_anomaly", _step_l)

    # ── M. provenance note ────────────────────────────────────────
    def _step_m():
        return SM.provenance_note(fingerprint=fingerprint, summary=summary)

    _step(res, "M_provenance_note", _step_m)

    return res


def _fetch_gold_terms(db: Session, limit: int = 500) -> list[dict[str, Any]]:
    rows = db.execute(
        text(
            "SELECT term_normalized, term_display, asset_type "
            "FROM taxonomy_terms "
            "WHERE deleted_at IS NULL "
            "  AND source IN ('gold','llm_promoted','manual') "
            "ORDER BY term_normalized "
            "LIMIT :lim"
        ),
        {"lim": limit},
    ).mappings().all()
    return [dict(r) for r in rows]
