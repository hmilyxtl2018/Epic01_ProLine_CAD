"""Steps A–E: semantic enrichment.

  A normalize_candidates  — multilingual / encoded-id normalization
  B softmatch              — embedding NN against gold taxonomy
  C arbiter                — accept / quarantine / reject with rationale
  D cluster_proposals      — group quarantine into reviewable proposals
  E block_kind             — classify opaque block names
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Sequence

from ..llm.embeddings import EmbeddingClient


# ── A. normalize ───────────────────────────────────────────────────────

# Strip common CAD encoding noise: trailing `_NNN`, leading `$plan$`,
# duplicated separators, full-width whitespace, etc.
_TRAILING_CODE = re.compile(r"[_\-]+\d+(?:_+\d+)*$")
_LEAD_INTERNAL = re.compile(r"^\$[a-z0-9$]+\$")
_BULK_SEP = re.compile(r"[\s_\-]{2,}")

# Cross-lingual lexicon (中/英/德/日 → English canonical form).
# Phase 1.1 (2026-04-22): expanded from 14 → ~120 entries to cover the
# six production-line domains seeded in 0012_proline_taxonomy_seed.py.
# Two design rules:
#   1. KEYS must be lower-case single tokens (no spaces) — normalize_candidate
#      tokenises on whitespace before lookup.
#   2. VALUES must match the `term_normalized` form of a gold taxonomy_terms
#      row (same casing/spacing) so step B softmatch can hit it via cosine.
# Multi-token surface forms (e.g. "stamping press") are NOT lexicon keys —
# they live in the gold taxonomy table and softmatch handles them.
# Strategy: most Chinese/German production-line terms are already present in
# the gold taxonomy_terms table verbatim (e.g. "压力机", "schweißroboter").
# So `_LEX` should NOT replace those — doing so strips them away from gold.
# We only keep two kinds of entries:
#   (1) CAD drafting noise → canonical English form that exists in gold
#       (annotation / dimension / etc.)
#   (2) True synonyms whose surface form is NOT itself in gold but whose
#       canonical English IS in gold (e.g. "press_machine" → "press machine").
# Anything that already appears in gold (中/德 verbatim) is INTENTIONALLY
# absent from this dict so normalize_candidate keeps it as-is.
_LEX = {
    # ── CAD drafting noise → gold canonical ──
    "标注": "annotation",
    "尺寸": "dimension",
    "bemaßung": "dimension",
    "beschriftung": "annotation",
    # ── Common alias forms ──
    "press_machine": "press machine",        # → gold "press machine"
    "pressmachine": "press machine",
    "weldingrobot": "welding robot",
    "handlingrobot": "handling robot",
    "robotcell": "robot cell",
    "safetyfence": "safety fence",
    "electricalpanel": "electrical panel",
    "controlpanel": "electrical panel",
    "wipstorage": "wip storage",
    # ── German compounds the tokenizer can't split ──
    # (handled by gold directly; nothing here)
}


def normalize_candidate(raw: str) -> dict[str, Any]:
    """Return `{normalized, lang, reason}` — A."""
    if not raw:
        return {"normalized": "", "lang": "und", "reason": "empty"}
    s = raw.strip().lower()
    s_in = s
    s = _LEAD_INTERNAL.sub("", s)
    s = _TRAILING_CODE.sub("", s)
    s = _BULK_SEP.sub(" ", s).strip()

    # Detect language by character ranges.
    lang = "und"
    has_cn = bool(re.search(r"[\u4e00-\u9fff]", s))
    has_de = bool(re.search(r"[äöüß]", s))
    if has_cn:
        lang = "zh"
    elif has_de:
        lang = "de"
    elif re.fullmatch(r"[a-z0-9 ]+", s):
        lang = "en"

    # Simple lexicon swap.
    swapped: list[str] = []
    for tok in re.split(r"\s+", s):
        if not tok:
            continue
        swapped.append(_LEX.get(tok, tok))
    out = " ".join(swapped).strip()
    reason_bits = []
    if s_in != s:
        reason_bits.append(f"strip_noise '{s_in}'→'{s}'")
    if out != s:
        reason_bits.append(f"lex_swap '{s}'→'{out}'")
    return {
        "normalized": out or s_in,
        "lang": lang,
        "reason": "; ".join(reason_bits) or "passthrough",
        "original": raw,
    }


def normalize_batch(raws: Sequence[str]) -> list[dict[str, Any]]:
    return [normalize_candidate(r) for r in raws]


# ── B. softmatch via embeddings ────────────────────────────────────────


def softmatch(
    embedder: EmbeddingClient,
    *,
    candidates: Sequence[dict[str, Any]],
    gold_terms: Sequence[dict[str, Any]],
    top_k: int = 3,
    accept_threshold: float = 0.86,
    review_threshold: float = 0.65,
) -> list[dict[str, Any]]:
    """For each candidate, find top-k gold neighbours by cosine. — B."""
    if not candidates or not gold_terms:
        return []
    cand_text = [c.get("term_normalized") or c.get("term_display") or "" for c in candidates]
    gold_text = [g.get("term_normalized") or "" for g in gold_terms]
    cv = embedder.embed(cand_text)
    gv = embedder.embed(gold_text)

    out: list[dict[str, Any]] = []
    for i, c in enumerate(candidates):
        sims = [
            (j, embedder.cosine(cv[i], gv[j])) for j in range(len(gv))
        ]
        sims.sort(key=lambda kv: -kv[1])
        top = sims[:top_k]
        best_j, best_sim = top[0]
        if best_sim >= accept_threshold:
            verdict = "accept"
        elif best_sim >= review_threshold:
            verdict = "review"
        else:
            verdict = "reject"
        out.append({
            "candidate": cand_text[i],
            "best_match": gold_text[best_j],
            "best_sim": round(best_sim, 4),
            "verdict": verdict,
            "topk": [
                {"term": gold_text[j], "sim": round(s, 4)} for j, s in top
            ],
        })
    return out


# ── C. arbiter (LLM-judge style decision boundary) ─────────────────────


def arbitrate(softmatch_out: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate softmatch verdicts and surface review queue. — C."""
    accepted, review, rejected = [], [], []
    for r in softmatch_out:
        bucket = {"accept": accepted, "review": review, "reject": rejected}.get(r["verdict"])
        if bucket is not None:
            bucket.append(r)
    return {
        "counts": {
            "accept": len(accepted),
            "review": len(review),
            "reject": len(rejected),
        },
        "review_queue": review[:50],
        "promotion_candidates": accepted[:50],
        "rationale": (
            "Softmatch verdicts derived from cosine ≥ 0.86 (accept) / ≥ 0.65 "
            "(review) / < 0.65 (reject). Review queue requires human approval "
            "before promote_to_gold."
        ),
    }


# ── D. cluster proposals (P0 unblocker) ────────────────────────────────


def cluster_proposals(
    embedder: EmbeddingClient,
    *,
    quarantine: Sequence[dict[str, Any]],
    max_clusters: int = 30,
    min_members: int = 2,
    sim_threshold: float = 0.55,
) -> dict[str, Any]:
    """Greedy single-link agglomerative clustering on embeddings. — D.

    Output: list of proposals, each = `{suggested_term, asset_type_hint,
    members[5], total_count, evidence}`. Designed to compress 2k+ raw
    quarantine rows into ≤ `max_clusters` reviewable items.
    """
    if not quarantine:
        return {"proposals": [], "stats": {"input": 0, "clusters": 0}}

    texts = [q.get("term_normalized") or "" for q in quarantine]
    vecs = embedder.embed(texts)

    # Greedy clustering: assign each item to an existing cluster centroid
    # if cosine ≥ threshold, otherwise create a new one.
    clusters: list[dict[str, Any]] = []
    for i, v in enumerate(vecs):
        best = -1.0
        best_idx = -1
        for ci, c in enumerate(clusters):
            sim = embedder.cosine(v, c["centroid"])
            if sim > best:
                best, best_idx = sim, ci
        if best >= sim_threshold and best_idx >= 0:
            c = clusters[best_idx]
            c["members"].append(i)
            # incremental centroid update
            n = len(c["members"])
            c["centroid"] = [
                (c["centroid"][k] * (n - 1) + v[k]) / n for k in range(len(v))
            ]
        else:
            clusters.append({"centroid": list(v), "members": [i]})

    # Rank by member count, drop singletons (unless we have headroom).
    clusters.sort(key=lambda c: -len(c["members"]))
    proposals: list[dict[str, Any]] = []
    for c in clusters:
        if len(proposals) >= max_clusters:
            break
        members_idx = c["members"]
        if len(members_idx) < min_members and len(proposals) >= max_clusters // 2:
            continue
        member_items = [quarantine[i] for i in members_idx]
        # Suggested term: shortest member normalized form (likely most generic).
        suggested = min(
            (m["term_normalized"] for m in member_items if m.get("term_normalized")),
            key=lambda s: (len(s), s),
            default="",
        )
        # Asset-type hint: majority vote.
        type_votes: dict[str, int] = defaultdict(int)
        for m in member_items:
            type_votes[m.get("asset_type", "Other")] += int(m.get("count", 1))
        asset_hint = max(type_votes.items(), key=lambda kv: kv[1])[0] if type_votes else "Other"
        proposals.append({
            "cluster_id": f"cl_{len(proposals):03d}",
            "suggested_term": suggested,
            "asset_type_hint": asset_hint,
            "member_count": len(members_idx),
            "total_count": sum(int(m.get("count", 1)) for m in member_items),
            "members": [
                {
                    "term_normalized": m["term_normalized"],
                    "term_display": m.get("term_display"),
                    "count": int(m.get("count", 1)),
                }
                for m in member_items[:5]
            ],
            "evidence": _flatten_evidence(member_items, cap=8),
        })
    return {
        "proposals": proposals,
        "stats": {
            "input": len(quarantine),
            "clusters": len(clusters),
            "shown": len(proposals),
            "compression_ratio": (
                round(len(quarantine) / max(len(proposals), 1), 2) if proposals else None
            ),
        },
        "rationale": (
            f"Greedy single-link clustering, cosine threshold={sim_threshold}. "
            f"Compressed {len(quarantine)} quarantine terms into "
            f"{len(proposals)} review-ready proposals."
        ),
    }


def _flatten_evidence(items: Sequence[dict[str, Any]], cap: int = 8) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for it in items:
        for e in (it.get("evidence") or [])[:2]:
            out.append({"term": it.get("term_normalized"), **e})
            if len(out) >= cap:
                return out
    return out


# ── E. block_kind classifier ───────────────────────────────────────────


_BLOCK_RULES = [
    ("autocad_internal", re.compile(r"^\$[a-z0-9$]+\$\d+", re.IGNORECASE), "AutoCAD internal block ($prefix$)"),
    ("door_lib", re.compile(r"dorlib", re.IGNORECASE), "AutoCAD door library"),
    ("window_lib", re.compile(r"winlib", re.IGNORECASE), "AutoCAD window library"),
    ("part_number", re.compile(r"^\d{6,}_\d+", re.IGNORECASE), "Long numeric part-code (e.g. 6010891_01_…)"),
    ("equipment_code", re.compile(r"^[A-Z]{2,5}\d{3,}$"), "Letters+digits equipment code (e.g. GRLA1228)"),
    ("title_block", re.compile(r"(title|titel|图框)", re.IGNORECASE), "Drawing title-block frame"),
    ("dimension", re.compile(r"(dim|标注|maß)", re.IGNORECASE), "Dimensioning helper"),
    ("hash_handle", re.compile(r"^A\$C[0-9A-F]{6,}", re.IGNORECASE), "AutoCAD anonymous handle"),
]


def classify_block(name: str) -> dict[str, Any]:
    """Return `{kind, reason, confidence}` for a single block name. — E."""
    for kind, regex, reason in _BLOCK_RULES:
        if regex.search(name or ""):
            return {
                "kind": kind,
                "reason": reason,
                "confidence": 0.9 if kind in ("autocad_internal", "hash_handle") else 0.7,
            }
    if (name or "").isdigit():
        return {"kind": "numeric_code", "reason": "Pure numeric block name", "confidence": 0.5}
    return {"kind": "user_defined", "reason": "No rule matched; likely domain-specific block", "confidence": 0.3}


def classify_blocks(names: Sequence[str], cap: int = 200) -> dict[str, Any]:
    out: list[dict[str, Any]] = []
    counts: dict[str, int] = defaultdict(int)
    for n in names[:cap]:
        c = classify_block(n)
        counts[c["kind"]] += 1
        out.append({"name": n, **c})
    return {
        "items": out,
        "kind_counts": dict(counts),
        "total_classified": len(out),
        "rationale": (
            "Heuristic block-name classifier. Real-LLM upgrade path: pass "
            "(name, layer, neighbouring MTEXT, scale) and let the model "
            "infer kind ∈ {equipment_code, part_number, autocad_internal, …}."
        ),
    }
