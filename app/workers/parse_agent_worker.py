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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.observability.logging import configure_logging, get_logger
from app.observability.metrics import METRICS
from shared.db_schemas import McpContext


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


def _do_parse(input_payload: dict[str, Any]) -> dict[str, Any]:
    """M1 stub: validate the uploaded file is readable.

    Returns an output_payload dict on success. Raises FileNotFoundError /
    ValueError on failure -- caller maps to ERROR status.

    M2 will replace this with a real call into ParseService.execute().
    """
    upload_path = input_payload.get("upload_path")
    if not upload_path:
        raise ValueError("input_payload missing upload_path")
    p = Path(upload_path)
    if not p.exists():
        raise FileNotFoundError(f"upload file not found: {p}")
    raw = p.read_bytes()
    if not raw:
        raise ValueError(f"upload file is empty: {p}")

    return {
        "bytes_read": len(raw),
        "filename": input_payload.get("filename"),
        "parse_stub": True,  # remove in M2 when real parser lands
    }


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
        out = _do_parse(ctx.input_payload or {})
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

    latency_ms = int((time.monotonic() - started) * 1000)
    _finalize(
        db,
        ctx,
        status=STATUS_SUCCESS,
        output_payload=out,
        error_message=None,
        latency_ms=latency_ms,
    )
    METRICS.dashboard_runs_total.labels(event="succeeded").inc()
    log.info("worker_run_succeeded", run_id=run_id, latency_ms=latency_ms)
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
