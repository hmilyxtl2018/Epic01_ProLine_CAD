"""Real CAD parser used by ParseAgent.

Produces a `ParseResult` containing four sections:

  1. fingerprint  -- file identity & format confirmation
  2. summary      -- entity / layer / block counts + bounding box
  3. semantics    -- taxonomy hits + quarantine candidates  (taxonomy lookup
                     is performed by the caller; we only emit raw token
                     candidates here)
  4. quality      -- warnings, confidence score, artifacts

The function is pure — no DB / network. The worker is responsible for
persisting `SiteModel` and `quarantine_terms` rows.

Format coverage (M2):
  * .dxf            full ezdxf parsing
  * .dwg            uses the repo-bundled ODA File Converter (tools/) — see
                    `_resolve_oda_path()`. Falls back to PATH / ODA_FC_PATH
                    env var. Emits a warning-only result when none is found.
  * .ifc / .step    coarse line-count + header sniff (full parse deferred)
"""

from __future__ import annotations

import hashlib
import os
import platform
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


# ── Repo-bundled ODA File Converter ────────────────────────────────────
#
# The ODA File Converter is the canonical tool for converting AutoCAD .dwg
# files into .dxf. We ship it under `tools/ODAFileConverter/` so the M2
# parser works on a clean checkout without the operator installing it
# globally.

_REPO_ROOT = Path(__file__).resolve().parents[3]
_BUNDLED_ODA = _REPO_ROOT / "tools" / "ODAFileConverter" / "ODAFileConverter.exe"


def _resolve_oda_path() -> str | None:
    """Return the absolute path to ODAFileConverter, or None.

    Lookup order:
      1. `ODA_FC_PATH` env var (operator override)
      2. Repo-bundled `tools/ODAFileConverter/ODAFileConverter.exe`
      3. `shutil.which("ODAFileConverter")` on PATH
    """
    import shutil

    env = os.getenv("ODA_FC_PATH")
    if env and Path(env).is_file():
        return env
    if _BUNDLED_ODA.is_file():
        return str(_BUNDLED_ODA)
    found = shutil.which("ODAFileConverter") or shutil.which("ODAFileConverter.exe")
    return found


# ── Public types ────────────────────────────────────────────────────────


@dataclass
class TermCandidate:
    """A label/string extracted from CAD that may match the taxonomy."""

    term_normalized: str
    term_display: str
    count: int
    evidence: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ParseResult:
    fingerprint: dict[str, Any]
    summary: dict[str, Any]
    semantics: dict[str, Any]
    quality: dict[str, Any]

    def to_payload(self) -> dict[str, Any]:
        """Flatten for `mcp_contexts.output_payload`."""
        return {
            "fingerprint": self.fingerprint,
            "summary": self.summary,
            "semantics_counts": {
                "candidate_count": len(self.semantics.get("candidates", [])),
            },
            "quality": self.quality,
        }


# ── Fingerprint ────────────────────────────────────────────────────────


def _sha256_of(path: Path, chunk: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for blk in iter(lambda: fh.read(chunk), b""):
            h.update(blk)
    return h.hexdigest()


def _make_fingerprint(path: Path, detected_format: str, filename: str) -> dict[str, Any]:
    return {
        "filename": filename,
        "size_bytes": path.stat().st_size,
        "sha256": _sha256_of(path),
        "detected_format": detected_format,
    }


# ── DXF (full ezdxf) ───────────────────────────────────────────────────

_INSUNITS = {
    0: "unitless", 1: "inch", 2: "foot", 4: "mm", 5: "cm", 6: "m", 14: "dm",
}


def _parse_dxf(path: Path) -> tuple[dict[str, Any], list[str], list[str], list[str]]:
    """Returns (summary, warnings, layer_names, block_names)."""
    import ezdxf
    from ezdxf import bbox as ezbbox

    warnings: list[str] = []
    try:
        doc = ezdxf.readfile(str(path))
    except ezdxf.DXFStructureError as e:
        return (
            {"parse_error": str(e)},
            [f"dxf_structure_error: {e}"],
            [],
            [],
        )

    msp = doc.modelspace()

    # entity counts by dxftype
    counts: dict[str, int] = {}
    for ent in msp:
        t = ent.dxftype()
        counts[t] = counts.get(t, 0) + 1

    layer_names = sorted(
        {ly.dxf.name for ly in doc.layers if ly.dxf.name not in {"0", "Defpoints"}}
    )
    block_names = sorted(
        {b.name for b in doc.blocks if not b.name.startswith(("*", "_"))}
    )

    # bounding box (modelspace) — may be None for empty drawings
    bbox_obj = ezbbox.extents(msp, fast=True)
    if bbox_obj.has_data:
        mn = bbox_obj.extmin
        mx = bbox_obj.extmax
        bounding_box: dict[str, Any] | None = {
            "min": [round(mn.x, 4), round(mn.y, 4), round(mn.z, 4)],
            "max": [round(mx.x, 4), round(mx.y, 4), round(mx.z, 4)],
            "width": round(mx.x - mn.x, 4),
            "height": round(mx.y - mn.y, 4),
        }
    else:
        bounding_box = None
        warnings.append("modelspace_empty: no entities with extents")

    units_code = doc.header.get("$INSUNITS", 0)
    summary = {
        "entity_counts": counts,
        "entity_total": sum(counts.values()),
        "layer_count": len(layer_names),
        "layer_names": layer_names[:50],  # cap for payload size
        "block_definition_count": len(block_names),
        "block_names": block_names[:50],
        "bounding_box": bounding_box,
        "units": _INSUNITS.get(units_code, f"code_{units_code}"),
        "dxf_version": doc.dxfversion,
    }
    return summary, warnings, layer_names, block_names


# ── DWG (ODA) ──────────────────────────────────────────────────────────


def _parse_dwg(path: Path) -> tuple[dict[str, Any], list[str], list[str], list[str]]:
    """Convert .dwg -> .dxf via ODA File Converter, then reuse _parse_dxf."""
    try:
        import ezdxf  # noqa: F401
        from ezdxf.addons import odafc  # type: ignore[import-not-found]
    except Exception as e:  # noqa: BLE001
        return (
            {},
            [f"dwg_parser_unavailable: ezdxf.addons.odafc import failed ({e})"],
            [],
            [],
        )

    oda_path = _resolve_oda_path()
    if not oda_path:
        return (
            {},
            [
                "dwg_parser_unavailable: ODA File Converter not found. "
                "Expected at tools/ODAFileConverter/ODAFileConverter.exe "
                "or via ODA_FC_PATH env var.",
            ],
            [],
            [],
        )

    # Point ezdxf at the resolved binary (works on win + unix keys).
    import ezdxf as _ezdxf

    if platform.system() == "Windows":
        _ezdxf.options.set("odafc-addon", "win_exec_path", oda_path)
    else:
        _ezdxf.options.set("odafc-addon", "unix_exec_path", oda_path)

    try:
        doc = odafc.readfile(str(path))
    except Exception as e:  # noqa: BLE001
        return ({}, [f"odafc_readfile_failed: {e}"], [], [])

    # Persist the converted DXF next to the upload so the dashboard's
    # "原始文件预览" tab can stream it back to the browser for a real
    # client-side render (dxf-viewer). We deliberately do NOT delete it.
    converted = path.with_suffix(path.suffix + ".converted.dxf")
    try:
        doc.saveas(str(converted))
    except Exception as e:  # noqa: BLE001
        return ({}, [f"odafc_saveas_failed: {e}"], [], [])

    summary, warnings, layers, blocks = _parse_dxf(converted)
    # Stash the converted path so the worker can record it in cad_source.
    summary["converted_dxf_path"] = str(converted)
    return summary, warnings, layers, blocks


def _which(exe: str) -> str | None:
    import shutil

    return shutil.which(exe) or shutil.which(f"{exe}.exe")


# ── IFC / STEP (header sniff only) ─────────────────────────────────────


_ENTITY_LINE = re.compile(rb"^#\d+\s*=\s*([A-Z_][A-Z0-9_]*)", re.MULTILINE)


def _parse_iso10303(path: Path) -> tuple[dict[str, Any], list[str], list[str], list[str]]:
    raw = path.read_bytes()
    counts: dict[str, int] = {}
    for m in _ENTITY_LINE.finditer(raw):
        name = m.group(1).decode("ascii", errors="replace")
        counts[name] = counts.get(name, 0) + 1
    summary: dict[str, Any] = {
        "entity_counts": dict(sorted(counts.items(), key=lambda kv: -kv[1])[:30]),
        "entity_total": sum(counts.values()),
    }
    # very rough header extraction
    head = raw[:2048].decode("latin-1", errors="replace")
    sch = re.search(r"FILE_SCHEMA\s*\(\s*\(\s*'([^']+)'", head)
    if sch:
        summary["schema"] = sch.group(1)
    warnings = ["ifc_step_full_parse_pending: only entity counts extracted (M3 backlog)"]
    return summary, warnings, [], []


# ── Semantic candidate extraction ──────────────────────────────────────


_TOKEN_RE = re.compile(r"[A-Za-z\u4e00-\u9fff][A-Za-z0-9_\u4e00-\u9fff\- ]{1,80}")


def _normalize_token(s: str) -> str:
    return re.sub(r"[\s_\-]+", " ", s.strip().lower())


def _extract_candidates(
    layer_names: list[str], block_names: list[str], filename: str
) -> list[TermCandidate]:
    """Build one candidate per unique normalized token across layers + blocks."""
    bag: dict[str, TermCandidate] = {}

    for src_name, source in (("layer", layer_names), ("block", block_names)):
        for raw in source:
            norm = _normalize_token(raw)
            if not norm or len(norm) < 2:
                continue
            # skip pure numeric / system tokens
            if norm.replace(" ", "").isdigit():
                continue
            cand = bag.get(norm)
            if cand is None:
                cand = TermCandidate(
                    term_normalized=norm,
                    term_display=raw.strip()[:200],
                    count=0,
                )
                bag[norm] = cand
            cand.count += 1
            if len(cand.evidence) < 5:
                cand.evidence.append({"source": src_name, "value": raw, "file": filename})

    return sorted(bag.values(), key=lambda c: -c.count)


# ── Public entry ───────────────────────────────────────────────────────


def parse_cad(*, path: Path, detected_format: str, filename: str) -> ParseResult:
    """Full ParseAgent pipeline. Always returns a ParseResult (never raises
    for parser-level issues — those become warnings)."""
    if not path.exists():
        # Fingerprint cannot be computed; fail loud (caller maps to ERROR).
        raise FileNotFoundError(f"upload missing: {path}")

    fingerprint = _make_fingerprint(path, detected_format, filename)
    fmt = detected_format.lower()

    if fmt == "dxf":
        summary, warnings, layers, blocks = _parse_dxf(path)
    elif fmt == "dwg":
        summary, warnings, layers, blocks = _parse_dwg(path)
    elif fmt in {"ifc", "step", "stp"}:
        summary, warnings, layers, blocks = _parse_iso10303(path)
    else:
        summary, warnings, layers, blocks = (
            {},
            [f"unsupported_format: {detected_format}"],
            [],
            [],
        )

    candidates = _extract_candidates(layers, blocks, filename)

    semantics = {
        "candidates": [c.to_dict() for c in candidates],
        # extracted_terms / quarantine partitioning happens in worker after
        # taxonomy lookup.
    }

    # Confidence: 1.0 if no warnings, else degrade by 0.15 per warning,
    # floor 0.0. If summary is empty (parser failed), cap at 0.2.
    base = 1.0 - 0.15 * len(warnings)
    if not summary or summary.get("entity_total", 0) == 0:
        base = min(base, 0.2)
    confidence = max(0.0, round(base, 4))

    quality = {
        "parse_warnings": warnings,
        "confidence_score": confidence,
        "artifacts": {},  # populated when we start writing previews/normalized files
    }

    return ParseResult(
        fingerprint=fingerprint,
        summary=summary,
        semantics=semantics,
        quality=quality,
    )
