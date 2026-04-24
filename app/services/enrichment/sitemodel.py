"""Steps J–M: SiteModel enrichment.

  J site_describe   — title + description + suggested tags
  K asset_extract   — INSERT-block → asset instance hypothesis
  L geom_anomaly    — bbox / unit / scale anomaly flagging
  M provenance_note — dxf_version → AutoCAD release + multi-team hints
"""

from __future__ import annotations

import re
from typing import Any, Sequence


# ── J. SiteModel describe ──────────────────────────────────────────────

_FACTORY_HINTS = {
    "机加": ("machining_workshop", "机加车间"),
    "车间": ("workshop", "车间"),
    "装配": ("assembly_line", "装配线"),
    "仓库": ("warehouse", "仓库"),
    "包装": ("packaging", "包装区"),
    "draufsicht": ("top_view", "Draufsicht"),
    "schnitt": ("section", "Schnitt"),
    "halle": ("hall", "Halle"),
}


def site_describe(
    *,
    filename: str,
    summary: dict[str, Any],
) -> dict[str, Any]:
    """Pick a title + description from filename + layer corpus. — J."""
    layer_names: list[str] = summary.get("layer_names") or []
    block_names: list[str] = summary.get("block_names") or []
    units = summary.get("units") or "unknown"
    bbox = summary.get("bounding_box") or {}

    haystack = " ".join([filename, *layer_names[:50], *block_names[:50]]).lower()
    tags: list[str] = []
    title_hint = filename
    for key, (tag, _human) in _FACTORY_HINTS.items():
        if key.lower() in haystack:
            tags.append(tag)
    tags = sorted(set(tags))

    width = bbox.get("width") if isinstance(bbox, dict) else None
    height = bbox.get("height") if isinstance(bbox, dict) else None
    size_phrase = ""
    if isinstance(width, (int, float)) and isinstance(height, (int, float)):
        if units == "mm":
            size_phrase = f"约 {width / 1000:.1f} × {height / 1000:.1f} m"
        else:
            size_phrase = f"{width:.1f} × {height:.1f} {units}"

    description_parts = [
        f"Source file: {filename}",
        f"Entities: {summary.get('entity_total', 0)} across {summary.get('layer_count', 0)} layers",
    ]
    if size_phrase:
        description_parts.append(f"Plan extent {size_phrase}")
    if tags:
        description_parts.append(f"Auto-tags: {', '.join(tags)}")

    title = filename
    # Prefer a Chinese phrase if filename contains one.
    cn = re.findall(r"[\u4e00-\u9fff]{2,}", filename)
    if cn:
        title = cn[0] + (f"（{size_phrase}）" if size_phrase else "")

    return {
        "title": title,
        "description": " · ".join(description_parts),
        "suggested_tags": tags,
        "evidence": [
            {"source": "filename", "value": filename},
            {"source": "summary.units", "value": units},
            {"source": "summary.bounding_box", "value": bbox},
        ],
    }


# ── K. asset extraction (stub: explains the gap) ──────────────────────


def asset_extract_stub(
    *,
    summary: dict[str, Any],
    matched_terms: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    """Heuristic asset list seeded from matched_terms. — K.

    Real LLM upgrade path: feed (block_name, insert_handle, layer,
    neighbouring MTEXT within 5 m, scale, rotation) and let the model
    emit `Asset{type, code, qty, location, evidence}`.
    """
    entity_counts = summary.get("entity_counts") or {}
    insert_count = int(entity_counts.get("INSERT", 0))
    assets = [
        {
            "asset_id": f"a_{i:04d}",
            "asset_type": t.get("asset_type"),
            "term": t.get("term_display"),
            "qty": int(t.get("count", 1)),
            "evidence": [
                {"source": "taxonomy_match", "term": t.get("term_normalized")}
            ],
            "confidence": 0.85,
        }
        for i, t in enumerate(matched_terms[:200])
    ]
    return {
        "assets": assets,
        "stats": {
            "extracted": len(assets),
            "block_inserts_in_drawing": insert_count,
            "coverage_ratio": (
                round(len(assets) / insert_count, 4) if insert_count else None
            ),
        },
        "rationale": (
            "M2 stub: asset list seeded from taxonomy matches. M3 will "
            "lift INSERT entities + MTEXT spatial join into per-instance "
            "Asset records. Coverage_ratio shows how much of the drawing "
            "is currently explained."
        ),
        "backlog": [
            "Spatial join INSERT ↔ MTEXT within 5m radius",
            "Block-attribute (ATTRIB) extraction for embedded codes",
            "LLM call: (block, layer, neighbour_text) → asset_type",
        ],
    }


# ── L. geometry anomaly ────────────────────────────────────────────────


def geom_anomaly(*, summary: dict[str, Any]) -> dict[str, Any]:
    """Flag bbox / unit / scale weirdness. — L."""
    bbox = summary.get("bounding_box") or {}
    units = summary.get("units")
    findings: list[dict[str, Any]] = []
    if not bbox or not bbox.get("min") or not bbox.get("max"):
        findings.append({
            "kind": "missing_bbox",
            "severity": "high",
            "hypothesis": "Modelspace empty or extents calculation failed.",
        })
    else:
        mn, mx = bbox["min"], bbox["max"]
        try:
            xs, ys, zs = (mx[i] - mn[i] for i in range(3))
            if zs > 50 * max(xs, ys):
                findings.append({
                    "kind": "z_extent_outlier",
                    "severity": "medium",
                    "values": {"x_span": xs, "y_span": ys, "z_span": zs},
                    "hypothesis": (
                        "Z spans far exceed X/Y — likely test geometry far "
                        "from origin, multi-drawing merge, or unit confusion."
                    ),
                })
            if units == "mm" and max(xs, ys) > 5_000_000:
                findings.append({
                    "kind": "scale_suspect_mm",
                    "severity": "medium",
                    "values": {"max_span_mm": max(xs, ys)},
                    "hypothesis": (
                        "Span > 5 km in mm — units may actually be cm/m or "
                        "the drawing combines multiple sites."
                    ),
                })
        except Exception:  # noqa: BLE001
            findings.append({"kind": "bbox_invalid", "severity": "high"})
    return {
        "findings": findings,
        "rationale": "Threshold-based geometry sanity checks; LLM upgrade can hypothesise causes from layer/block context.",
    }


# ── M. provenance note ────────────────────────────────────────────────

_DXF_VERSIONS = {
    "AC1009": "AutoCAD R12 (1992)",
    "AC1012": "AutoCAD R13 (1994)",
    "AC1014": "AutoCAD R14 (1997)",
    "AC1015": "AutoCAD 2000 (1999)",
    "AC1018": "AutoCAD 2004 (2003)",
    "AC1021": "AutoCAD 2007 (2006)",
    "AC1024": "AutoCAD 2010 (2009)",
    "AC1027": "AutoCAD 2013 (2012)",
    "AC1032": "AutoCAD 2018 (2017)",
}


def provenance_note(*, fingerprint: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any]:
    """Translate technical metadata into a one-line business note. — M."""
    dxf_version = summary.get("dxf_version") or fingerprint.get("dxf_version")
    release = _DXF_VERSIONS.get(dxf_version, f"unknown DXF version ({dxf_version})")

    layer_names = summary.get("layer_names") or []
    has_cn = any(re.search(r"[\u4e00-\u9fff]", ln) for ln in layer_names)
    has_de = any(re.search(r"[äöüß]", ln.lower()) for ln in layer_names)
    has_en = any(re.fullmatch(r"[A-Za-z0-9_\- ]+", ln) for ln in layer_names)
    langs = [tag for tag, present in [("zh", has_cn), ("de", has_de), ("en", has_en)] if present]
    multi_team = len(langs) >= 2

    note_bits = [f"Format: {dxf_version} → {release}"]
    if langs:
        note_bits.append(f"Layer-name languages detected: {', '.join(langs)}")
    if multi_team:
        note_bits.append("Mixed languages → likely multi-team / multi-vendor source drawing")

    return {
        "release": release,
        "languages": langs,
        "multi_team_source": multi_team,
        "note": " · ".join(note_bits),
        "evidence": [
            {"source": "summary.dxf_version", "value": dxf_version},
            {"source": "summary.layer_names[*]", "value_sample": layer_names[:5]},
        ],
    }
