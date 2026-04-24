"""Steps F–I: quality / explainability layer.

  F quality_breakdown  — multi-dimensional confidence with explanation
  G root_cause         — aggregate parse_warnings into root causes
  H audit_narrative    — human-readable trace of the entire run
  I self_check         — should we block downstream agents?
"""

from __future__ import annotations

import re
from typing import Any, Sequence


# ── F. multi-dimensional quality ───────────────────────────────────────


def quality_breakdown(
    *,
    summary: dict[str, Any],
    matched_count: int,
    quarantine_count: int,
    candidate_count: int,
    warnings: Sequence[str],
) -> dict[str, Any]:
    """Compute parse / semantic / integrity sub-scores + overall. — F."""
    entity_total = int(summary.get("entity_total") or 0)
    layer_count = int(summary.get("layer_count") or 0)
    bbox = summary.get("bounding_box") or {}

    parse_score = 1.0 if entity_total > 0 else 0.2
    if any("dwg_parser_unavailable" in w or "dxf_structure_error" in w for w in warnings):
        parse_score = 0.0
    parse_score = max(0.0, parse_score - 0.1 * len(warnings))

    semantic_score = 0.0
    if candidate_count:
        semantic_score = matched_count / candidate_count
    semantic_score = round(min(1.0, semantic_score), 4)

    # Integrity: did we get a non-degenerate bbox?
    integrity_score = 1.0
    if not bbox or not bbox.get("min") or not bbox.get("max"):
        integrity_score = 0.3
    else:
        try:
            xs = bbox["max"][0] - bbox["min"][0]
            ys = bbox["max"][1] - bbox["min"][1]
            zs = bbox["max"][2] - bbox["min"][2]
            if xs <= 0 or ys <= 0:
                integrity_score = 0.3
            elif zs > 50 * max(xs, ys):
                integrity_score = 0.6  # suspicious z-extent
        except Exception:  # noqa: BLE001
            integrity_score = 0.5

    overall = round(0.4 * parse_score + 0.3 * semantic_score + 0.3 * integrity_score, 4)

    why_bits = []
    if parse_score >= 0.9:
        why_bits.append(f"parser succeeded ({entity_total} entities, {layer_count} layers)")
    elif parse_score == 0.0:
        why_bits.append("parser failed (no entities recovered)")
    else:
        why_bits.append(f"parser produced data with {len(warnings)} warning(s)")
    if semantic_score >= 0.5:
        why_bits.append(f"taxonomy coverage {semantic_score:.0%}")
    elif candidate_count == 0:
        why_bits.append("no semantic candidates extracted")
    else:
        why_bits.append(
            f"taxonomy coverage only {semantic_score:.0%} ({matched_count}/{candidate_count})"
        )
    if integrity_score < 1.0:
        why_bits.append("geometry integrity flagged (bbox shape suspect)")

    return {
        "parse": round(parse_score, 4),
        "semantic": semantic_score,
        "integrity": round(integrity_score, 4),
        "overall": overall,
        "why": "; ".join(why_bits),
        "weights": {"parse": 0.4, "semantic": 0.3, "integrity": 0.3},
    }


# ── G. root cause aggregation ──────────────────────────────────────────

_ROOT_CAUSE_RULES = [
    (
        re.compile(r"dwg_parser_unavailable"),
        {
            "root_cause": "dwg_toolchain_missing",
            "owner": "ops",
            "fix": "Install ODA File Converter or set ODA_FC_PATH; bundled at tools/ODAFileConverter/.",
        },
    ),
    (
        re.compile(r"dxf_structure_error"),
        {
            "root_cause": "corrupt_or_unsupported_dxf",
            "owner": "data",
            "fix": "Re-export from source CAD with DXF R2018+ (AC1024).",
        },
    ),
    (
        re.compile(r"modelspace_empty"),
        {
            "root_cause": "drawing_empty",
            "owner": "data",
            "fix": "Verify the modelspace contains entities (not only paperspace).",
        },
    ),
    (
        re.compile(r"ifc_step_full_parse_pending"),
        {
            "root_cause": "ifc_parser_backlog",
            "owner": "engineering",
            "fix": "M3: integrate ifcopenshell for full IFC structural parse.",
        },
    ),
    (
        re.compile(r"site_model_write_failed"),
        {
            "root_cause": "db_write_failed",
            "owner": "ops",
            "fix": "Check PostGIS extension + bbox WKT validity in worker logs.",
        },
    ),
]


def root_cause(warnings: Sequence[str]) -> dict[str, Any]:
    """Cluster warnings into root causes with owner + fix. — G."""
    if not warnings:
        return {"root_causes": [], "uncategorized": []}
    seen: dict[str, dict[str, Any]] = {}
    uncategorized: list[str] = []
    for w in warnings:
        matched = False
        for regex, meta in _ROOT_CAUSE_RULES:
            if regex.search(w):
                key = meta["root_cause"]
                bucket = seen.setdefault(key, {**meta, "evidence": [], "count": 0})
                bucket["evidence"].append(w)
                bucket["count"] += 1
                matched = True
                break
        if not matched:
            uncategorized.append(w)
    return {
        "root_causes": list(seen.values()),
        "uncategorized": uncategorized,
        "rationale": "Pattern-matched warnings → root-cause buckets with owner & fix proposal.",
    }


# ── H. audit narrative ─────────────────────────────────────────────────


def audit_narrative(
    *,
    run_id: str,
    fingerprint: dict[str, Any],
    summary: dict[str, Any],
    matched_count: int,
    quarantine_count: int,
    site_model_id: str | None,
    quality: dict[str, Any],
    enrichment_steps: Sequence[str],
) -> dict[str, Any]:
    """Generate a 1-paragraph human-readable trace. — H."""
    fmt = fingerprint.get("detected_format", "?")
    name = fingerprint.get("filename", "<unknown>")
    size_mb = (fingerprint.get("size_bytes") or 0) / 1024 / 1024
    entities = summary.get("entity_total", 0)
    layers = summary.get("layer_count", 0)
    text = (
        f"Run {run_id[:8]}: parsed {fmt.upper()} '{name}' ({size_mb:.1f} MiB) → "
        f"{entities} entities across {layers} layers. "
        f"Taxonomy: {matched_count} matched / {quarantine_count} quarantined. "
        f"Site-model: {site_model_id or 'not generated'}. "
        f"Quality (overall): {quality.get('overall', 0):.2f}. "
        f"Enrichment steps: {', '.join(enrichment_steps) or 'none'}."
    )
    cited = [
        "fingerprint.filename",
        "fingerprint.detected_format",
        "fingerprint.size_bytes",
        "summary.entity_total",
        "summary.layer_count",
        "semantics.matched_terms_count",
        "semantics.quarantine_terms_count",
        "semantics.linked_site_model_id",
        "llm_enrichment.quality_breakdown.overall",
    ]
    return {"narrative": text, "cited_fields": cited}


# ── I. self-check ──────────────────────────────────────────────────────


def self_check(
    *,
    matched_count: int,
    quarantine_count: int,
    candidate_count: int,
    quality_overall: float,
    parse_warnings: Sequence[str],
) -> dict[str, Any]:
    """Decide if downstream agents should block. — I."""
    blockers: list[str] = []
    if quality_overall < 0.3:
        blockers.append(
            f"quality_overall={quality_overall:.2f} below 0.30 threshold"
        )
    if candidate_count > 0:
        ratio = matched_count / candidate_count
        if ratio < 0.001 and candidate_count > 100:
            blockers.append(
                f"taxonomy match ratio {ratio:.3%} ({matched_count}/{candidate_count}) "
                f"is at the historical 1‰ floor — taxonomy almost certainly stale"
            )
    if any("dwg_parser_unavailable" in w for w in parse_warnings):
        blockers.append("DWG parser unavailable — downstream cannot proceed")

    return {
        "should_block": bool(blockers),
        "severity": "high" if blockers else "ok",
        "blockers": blockers,
        "advice": (
            "Block downstream BalanceAgent/ScoringAgent until taxonomy is "
            "extended or warnings cleared."
            if blockers
            else "Safe to proceed."
        ),
    }
