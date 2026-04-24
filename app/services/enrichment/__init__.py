"""LLM-assisted enrichment pipeline (steps A–M).

The pipeline runs **after** parse_cad and **after** the worker's bulk
taxonomy lookup, taking the raw candidates / matched / quarantine lists
and producing a structured `enrichment` dict that's stored under
`output_payload.llm_enrichment` and rendered by the dashboard.

Every step has:

  * a stub heuristic (deterministic, offline, dependency-free), so the
    pipeline runs in CI / dev / air-gapped without any LLM key;
  * a real-LLM swap point via `LLMClient.generate_json(...)`;
  * structured evidence pinning each decision back to a source field;
  * an audit row written to `audit_log_actions` (action='llm_call').

The 13 steps map to the LLM landing-points discussed in the design:

    A normalize          (semantic)
    B softmatch          (semantic)
    C arbiter            (semantic)
    D cluster_proposals  (semantic)         ← P0 unblocker
    E block_kind         (semantic)
    F quality_breakdown  (quality)
    G root_cause         (quality)
    H audit_narrative    (quality)
    I self_check         (quality)
    J site_describe      (sitemodel)
    K asset_extract      (sitemodel)
    L geom_anomaly       (sitemodel)
    M provenance_note    (sitemodel)
"""

from .pipeline import run_enrichment, EnrichmentResult

__all__ = ["run_enrichment", "EnrichmentResult"]
