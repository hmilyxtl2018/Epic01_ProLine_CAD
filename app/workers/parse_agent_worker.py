"""ParseAgent worker — claim PENDING runs from `mcp_contexts` and finalize them.

Lifecycle (M1 minimal happy path):

    PENDING  --(claim)-->  RUNNING  --(success)-->  SUCCESS / SUCCESS_WITH_WARNINGS
                                  \\--(failure)-->  ERROR

The worker uses `SELECT ... FOR UPDATE SKIP LOCKED` so multiple instances can
run in parallel without double-claiming a row.

The actual CAD parsing is **stubbed** in M1 -- we only verify the upload file
exists and is non-empty, then write a small `output_payload`. Full ezdxf /
Shapely pipeline integration lands in M2 alongside the SiteModel writeback.

CLI:
    python -m app.workers.parse_agent_worker --once     # drain one job, exit
    python -m app.workers.parse_agent_worker --loop     # poll forever
"""

from __future__ import annotations

import argparse
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.observability.logging import configure_logging, get_logger
from app.observability.metrics import METRICS
from app.services.enrichment import run_enrichment
from app.services.parse.cad_parser import ParseResult, parse_cad
from shared.db_schemas import McpContext, SiteModel


PARSE_AGENT_NAME = "ParseAgent"

# Status vocabulary aligned with shared.models.AgentStatus *strings* + the two
# transitional values the Dashboard owns.
STATUS_PENDING = "PENDING"
STATUS_RUNNING = "RUNNING"
STATUS_SUCCESS = "SUCCESS"
STATUS_SUCCESS_WITH_WARNINGS = "SUCCESS_WITH_WARNINGS"
STATUS_ERROR = "ERROR"

TERMINAL_STATUSES = (STATUS_SUCCESS, STATUS_SUCCESS_WITH_WARNINGS, STATUS_ERROR)

log = get_logger(__name__)


# ── Internals ──────────────────────────────────────────────────────────

def _claim_pending_run(db: Session) -> McpContext | None:
    """Atomically grab the oldest PENDING ParseAgent row and flip to RUNNING.

    Uses `FOR UPDATE SKIP LOCKED` so concurrent workers never collide.
    Commits the RUNNING transition immediately so observers (Dashboard list,
    /metrics scrape) see the state change without waiting for the work to
    complete.
    """
    row = db.execute(
        select(McpContext)
        .where(McpContext.agent == PARSE_AGENT_NAME)
        .where(McpContext.status == STATUS_PENDING)
        .where(McpContext.deleted_at.is_(None))
        .order_by(McpContext.timestamp.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
    ).scalar_one_or_none()

    if row is None:
        return None

    row.status = STATUS_RUNNING
    db.commit()
    db.refresh(row)
    return row


def _do_parse(input_payload: dict[str, Any]) -> ParseResult:
    """Run real CAD parsing on the uploaded file.

    Returns a structured `ParseResult`. Raises `FileNotFoundError` /
    `ValueError` only for catastrophic input issues (missing path /
    missing file); recoverable parser issues are recorded as warnings
    inside the result.
    """
    upload_path = input_payload.get("upload_path")
    if not upload_path:
        raise ValueError("input_payload missing upload_path")
    p = Path(upload_path)
    if not p.exists():
        raise FileNotFoundError(f"upload file not found: {p}")
    if p.stat().st_size == 0:
        raise ValueError(f"upload file is empty: {p}")

    detected = (input_payload.get("detected_format") or p.suffix.lstrip(".")).lower()
    return parse_cad(
        path=p,
        detected_format=detected,
        filename=input_payload.get("filename") or p.name,
    )


def _finalize(
    db: Session,
    ctx: McpContext,
    *,
    status: str,
    output_payload: dict[str, Any] | None,
    error_message: str | None,
    latency_ms: int,
) -> None:
    ctx.status = status
    ctx.output_payload = output_payload or {}
    ctx.error_message = error_message
    ctx.latency_ms = latency_ms
    db.commit()


# ── Semantic writeback (taxonomy lookup + quarantine inserts) ───────────

_DEFAULT_QUARANTINE_ASSET_TYPE = "Other"


def _classify_candidates(
    db: Session, candidates: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split parser candidates into (gold-matched, quarantine-bound) lists.

    Lookup is a single bulk SELECT against `taxonomy_terms` keyed by
    `term_normalized` (gold or llm_promoted only).
    """
    if not candidates:
        return [], []

    norms = sorted({c["term_normalized"] for c in candidates if c.get("term_normalized")})
    if not norms:
        return [], []

    gold_rows = db.execute(
        text(
            "SELECT term_normalized, term_display, asset_type "
            "FROM taxonomy_terms "
            "WHERE deleted_at IS NULL "
            "  AND source IN ('gold','llm_promoted','manual') "
            "  AND term_normalized = ANY(:norms)"
        ),
        {"norms": norms},
    ).mappings().all()
    gold_map = {r["term_normalized"]: dict(r) for r in gold_rows}

    matched: list[dict[str, Any]] = []
    quarantine: list[dict[str, Any]] = []
    for c in candidates:
        norm = c["term_normalized"]
        if norm in gold_map:
            hit = gold_map[norm]
            matched.append({
                "term_normalized": norm,
                "term_display": hit["term_display"],
                "asset_type": hit["asset_type"],
                "count": c.get("count", 1),
                "source": "taxonomy",
            })
        else:
            quarantine.append({
                "term_normalized": norm,
                "term_display": c.get("term_display") or norm,
                "asset_type": _DEFAULT_QUARANTINE_ASSET_TYPE,
                "count": c.get("count", 1),
                "evidence": c.get("evidence", []),
            })
    return matched, quarantine


def _upsert_quarantine_terms(
    db: Session, *, mcp_context_id: str, items: list[dict[str, Any]]
) -> int:
    """Insert quarantine_terms rows; on (term_normalized, asset_type)
    conflict, bump count + extend evidence + refresh last_seen.
    Returns inserted-or-updated row count.
    """
    if not items:
        return 0
    now = datetime.now(tz=timezone.utc)
    n = 0
    for it in items:
        db.execute(
            text(
                """
                INSERT INTO quarantine_terms (
                    term_normalized, term_display, asset_type, count,
                    evidence, first_seen, last_seen, decision, mcp_context_id
                )
                VALUES (
                    :term_normalized, :term_display, :asset_type, :count,
                    CAST(:evidence AS jsonb), :now, :now, 'pending', :mcp
                )
                ON CONFLICT (term_normalized, asset_type)
                WHERE deleted_at IS NULL
                DO UPDATE SET
                    count = quarantine_terms.count + EXCLUDED.count,
                    evidence = EXCLUDED.evidence,
                    last_seen = EXCLUDED.last_seen
                """
            ),
            {
                "term_normalized": it["term_normalized"],
                "term_display": it["term_display"],
                "asset_type": it["asset_type"],
                "count": int(it.get("count", 1)),
                "evidence": _jsonb(it.get("evidence", [])),
                "now": now,
                "mcp": mcp_context_id,
            },
        )
        n += 1
    return n


def _jsonb(obj: Any) -> str:
    import json

    return json.dumps(obj, ensure_ascii=False, default=str)


def _write_site_model(
    db: Session,
    *,
    mcp_context_id: str,
    parse_result: ParseResult,
    matched_terms: list[dict[str, Any]],
    quarantine_count: int,
) -> str:
    """Insert a `site_models` row tied to this run. Returns site_model_id."""
    site_model_id = f"sm_{uuid.uuid4().hex[:12]}"
    summary = parse_result.summary or {}
    statistics = {
        "entity_counts": summary.get("entity_counts", {}),
        "entity_total": summary.get("entity_total", 0),
        "layer_count": summary.get("layer_count", 0),
        "block_definition_count": summary.get("block_definition_count", 0),
        "bounding_box": summary.get("bounding_box"),
        "units": summary.get("units"),
        "matched_terms_count": len(matched_terms),
        "quarantine_terms_count": quarantine_count,
        "warnings": parse_result.quality.get("parse_warnings", []),
    }
    cad_source = {
        **(parse_result.fingerprint or {}),
        "dxf_version": summary.get("dxf_version"),
        "schema": summary.get("schema"),
        # Set when the worker converted DWG → DXF; the dashboard streams this
        # back to the browser for client-side rendering.
        "converted_dxf_path": summary.get("converted_dxf_path"),
    }
    assets = matched_terms  # assets list seeded with taxonomy hits

    bb = summary.get("bounding_box")
    bbox_wkt: str | None = None
    if bb and bb.get("min") and bb.get("max"):
        x0, y0 = bb["min"][0], bb["min"][1]
        x1, y1 = bb["max"][0], bb["max"][1]
        if x1 > x0 and y1 > y0:
            bbox_wkt = (
                f"POLYGON(({x0} {y0}, {x1} {y0}, {x1} {y1}, {x0} {y1}, {x0} {y0}))"
            )

    db.execute(
        text(
            """
            INSERT INTO site_models (
                site_model_id, cad_source, assets, links,
                geometry_integrity_score, statistics, mcp_context_id, bbox
            )
            VALUES (
                :sid, CAST(:cad AS jsonb), CAST(:assets AS jsonb), CAST(:links AS jsonb),
                :score, CAST(:stats AS jsonb), :mcp,
                CASE WHEN :bbox_wkt IS NULL THEN NULL
                     ELSE ST_GeomFromText(:bbox_wkt, 0) END
            )
            """
        ),
        {
            "sid": site_model_id,
            "cad": _jsonb(cad_source),
            "assets": _jsonb(assets),
            "links": _jsonb([]),
            "score": float(parse_result.quality.get("confidence_score", 0.0)),
            "stats": _jsonb(statistics),
            "mcp": mcp_context_id,
            "bbox_wkt": bbox_wkt,
        },
    )
    return site_model_id


# ── Public API ─────────────────────────────────────────────────────────

def process_one(db: Session) -> str | None:
    """Drain one PENDING run. Returns its mcp_context_id or None if nothing waiting."""
    ctx = _claim_pending_run(db)
    if ctx is None:
        return None

    run_id = ctx.mcp_context_id
    log.info("worker_run_started", run_id=run_id)
    started = time.monotonic()

    try:
        result = _do_parse(ctx.input_payload or {})
    except (FileNotFoundError, ValueError) as e:
        latency_ms = int((time.monotonic() - started) * 1000)
        _finalize(
            db,
            ctx,
            status=STATUS_ERROR,
            output_payload=None,
            error_message=str(e),
            latency_ms=latency_ms,
        )
        METRICS.dashboard_runs_total.labels(event="errored").inc()
        log.warning(
            "worker_run_failed", run_id=run_id, error=str(e), latency_ms=latency_ms
        )
        return run_id

    # Section 3 — taxonomy lookup + quarantine inserts.
    matched, quarantine = _classify_candidates(
        db, result.semantics.get("candidates", [])
    )
    quarantine_inserted = _upsert_quarantine_terms(
        db, mcp_context_id=run_id, items=quarantine
    )

    # Persist SiteModel (skips if no parsed content at all, keeping fingerprint-only runs valid).
    site_model_id: str | None = None
    if result.summary or matched or quarantine:
        try:
            site_model_id = _write_site_model(
                db,
                mcp_context_id=run_id,
                parse_result=result,
                matched_terms=matched,
                quarantine_count=quarantine_inserted,
            )
        except Exception as e:  # noqa: BLE001 — degrade to SUCCESS_WITH_WARNINGS
            log.warning(
                "site_model_write_failed", run_id=run_id, error=str(e)
            )
            result.quality.setdefault("parse_warnings", []).append(
                f"site_model_write_failed: {e}"
            )

    # Build output_payload: fingerprint + summary + semantics totals + quality.
    output_payload = result.to_payload()
    output_payload["semantics"] = {
        "matched_terms": matched[:100],
        "matched_terms_count": len(matched),
        "quarantine_terms_count": quarantine_inserted,
        "linked_site_model_id": site_model_id,
    }

    # ── LLM-assisted enrichment (steps A–M) ────────────────────────
    try:
        enrichment = run_enrichment(
            db=db,
            mcp_context_id=run_id,
            fingerprint=result.fingerprint,
            summary=result.summary,
            candidates=result.semantics.get("candidates", []),
            matched_terms=matched,
            quarantine_terms=quarantine,
            parse_warnings=result.quality.get("parse_warnings", []),
            site_model_id=site_model_id,
        )
        output_payload["llm_enrichment"] = enrichment.to_dict()
    except Exception as e:  # noqa: BLE001
        log.warning("enrichment_failed", run_id=run_id, error=str(e))
        output_payload["llm_enrichment"] = {
            "sections": {},
            "errors": {"pipeline": f"{type(e).__name__}: {e}"},
            "version": "v1",
        }

    warnings = result.quality.get("parse_warnings") or []
    final_status = STATUS_SUCCESS_WITH_WARNINGS if warnings else STATUS_SUCCESS

    latency_ms = int((time.monotonic() - started) * 1000)
    _finalize(
        db,
        ctx,
        status=final_status,
        output_payload=output_payload,
        error_message=None,
        latency_ms=latency_ms,
    )
    METRICS.dashboard_runs_total.labels(event="succeeded").inc()
    log.info(
        "worker_run_succeeded",
        run_id=run_id,
        latency_ms=latency_ms,
        site_model_id=site_model_id,
        matched=len(matched),
        quarantine=quarantine_inserted,
        warnings=len(warnings),
    )
    return run_id


def run_loop(poll_interval_s: float = 2.0, stop_after: int | None = None) -> int:
    """Poll forever (or until `stop_after` runs are processed). Returns count."""
    from app.deps import init_engine, _SessionLocal  # local: avoid import cycle

    init_engine()
    if _SessionLocal is None:
        raise RuntimeError("SessionLocal is None after init_engine()")

    processed = 0
    while True:
        with _SessionLocal() as db:
            run_id = process_one(db)
        if run_id is not None:
            processed += 1
            if stop_after is not None and processed >= stop_after:
                return processed
            continue  # immediately try next without sleeping
        time.sleep(poll_interval_s)


# ── CLI ────────────────────────────────────────────────────────────────

def _cli() -> int:
    parser = argparse.ArgumentParser(description="ParseAgent run worker")
    grp = parser.add_mutually_exclusive_group(required=True)
    grp.add_argument("--once", action="store_true", help="Drain a single PENDING run and exit.")
    grp.add_argument("--loop", action="store_true", help="Poll forever.")
    parser.add_argument("--poll-interval", type=float, default=2.0)
    parser.add_argument("--stop-after", type=int, default=None,
                        help="With --loop, exit after N successful claims.")
    args = parser.parse_args()

    configure_logging()

    if args.once:
        from app.deps import init_engine, _SessionLocal
        init_engine()
        if _SessionLocal is None:
            print("ERROR: POSTGRES_DSN unset")
            return 2
        with _SessionLocal() as db:
            run_id = process_one(db)
        print(run_id or "no-pending-runs")
        return 0

    count = run_loop(args.poll_interval, args.stop_after)
    print(f"processed={count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
