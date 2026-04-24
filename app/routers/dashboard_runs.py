"""/dashboard/runs* -- M1 surface (ExcPlan §2.4).

Routes:
  GET  /dashboard/runs                  viewer+
  GET  /dashboard/runs/{id}             viewer+
  POST /dashboard/runs                  operator + admin
  WS   /dashboard/runs/{id}/stream      viewer+ (NB: WS skips RBAC dep, see code)

WebSocket RBAC enforcement is handled inline (FastAPI Depends does not run for
WebSocket routes the same way -- starlette will not invoke HTTPException
handlers, so we manually accept-then-close on auth failure).
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from sqlalchemy.orm import Session

from app.deps import (
    CurrentUser,
    get_current_user,
    get_db,
    get_db_for,
    killswitch_gate,
    require_role,
)
from app.errors import AppError
from app.observability.logging import get_logger
from app.observability.metrics import METRICS
from app.queue import enqueue_parse_run, subscribe_run_events
from app.schemas.runs import (
    RunCreatedResponse,
    RunDetail,
    RunListResponse,
    RunSummary,
)
from app.security.upload import UploadRejected
from app.services import runs_service
from shared.db_schemas import AuditLogAction


log = get_logger(__name__)

# killswitch_gate is applied at the router level so EVERY /dashboard/* route
# returns 503 when the killswitch is active. /healthz + /metrics intentionally
# live on routers without this gate.
router = APIRouter(
    prefix="/dashboard",
    tags=["dashboard"],
    dependencies=[Depends(killswitch_gate)],
)

# Cached role-gate dependencies. Reusing the same callable lets FastAPI dedupe
# the dependency invocation between the route's `user` parameter and the
# `get_db_for(...)` factory (otherwise each call to require_role() returns a
# fresh closure and FastAPI would resolve get_current_user twice per request).
_viewer_or_above = require_role("viewer", "operator", "reviewer", "admin")
_operator_or_admin = require_role("operator", "admin")
_db_viewer = get_db_for(_viewer_or_above)
_db_operator = get_db_for(_operator_or_admin)


# ── GET /dashboard/runs ────────────────────────────────────────────────
@router.get(
    "/runs",
    response_model=RunListResponse,
    summary="List ParseAgent runs (paginated, newest first)",
)
def list_runs(
    db: Session = Depends(_db_viewer),
    _user: CurrentUser = Depends(_viewer_or_above),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
) -> RunListResponse:
    rows, total = runs_service.list_runs(db, page=page, page_size=page_size)
    METRICS.dashboard_runs_total.labels(event="listed").inc()
    items: list[RunSummary] = []
    for r in rows:
        payload = r.input_payload or {}
        items.append(
            RunSummary(
                mcp_context_id=r.mcp_context_id,
                agent=r.agent,
                agent_version=r.agent_version,
                status=r.status,
                timestamp=r.timestamp,
                latency_ms=r.latency_ms or 0,
                filename=payload.get("filename"),
                size_bytes=payload.get("size_bytes"),
                detected_format=payload.get("detected_format"),
            )
        )
    return RunListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


# ── GET /dashboard/runs/{id} ───────────────────────────────────────────
@router.get(
    "/runs/{mcp_context_id}",
    response_model=RunDetail,
    summary="Single run detail (with linked SiteModel summary)",
)
def get_run(
    mcp_context_id: str,
    db: Session = Depends(_db_viewer),
    _user: CurrentUser = Depends(_viewer_or_above),
) -> RunDetail:
    detail = runs_service.get_run_detail(db, mcp_context_id)
    if detail is None:
        raise AppError(
            error_code="NOT_FOUND",
            message=f"Run '{mcp_context_id}' not found.",
            status_code=status.HTTP_404_NOT_FOUND,
            mcp_context_id=mcp_context_id,
        )
    METRICS.dashboard_runs_total.labels(event="fetched").inc()
    return RunDetail.model_validate(detail)


# ── GET /dashboard/runs/{id}/cad ───────────────────────────────────────
@router.get(
    "/runs/{mcp_context_id}/cad",
    summary="Stream the run's DXF for browser-side preview (dxf-viewer)",
    response_class=None,  # FileResponse handles its own content-type
)
def get_run_cad(
    mcp_context_id: str,
    db: Session = Depends(_db_viewer),
    _user: CurrentUser = Depends(_viewer_or_above),
):
    """Return the DXF file for this run.

    Lookup order:
      1. site_models.cad_source.converted_dxf_path  (set when the worker
         converted DWG → DXF via ODA)
      2. mcp_contexts.input_payload.upload_path     (when the upload itself
         was already DXF)
    """
    from pathlib import Path
    from fastapi.responses import FileResponse

    detail = runs_service.get_run_detail(db, mcp_context_id)
    if detail is None:
        raise AppError(
            error_code="NOT_FOUND",
            message=f"Run '{mcp_context_id}' not found.",
            status_code=status.HTTP_404_NOT_FOUND,
            mcp_context_id=mcp_context_id,
        )
    cad_source = detail.get("site_model_cad_source") or {}
    input_payload = detail.get("input_payload") or {}

    candidate: str | None = None
    converted = cad_source.get("converted_dxf_path")
    if converted and Path(converted).is_file():
        candidate = converted
    else:
        upload = input_payload.get("upload_path")
        detected = (cad_source.get("detected_format") or "").lower()
        if upload and detected == "dxf" and Path(upload).is_file():
            candidate = upload

    if not candidate:
        raise AppError(
            error_code="CAD_PREVIEW_UNAVAILABLE",
            message=(
                "No DXF available for this run. DWG conversion may have "
                "failed, or the source format is not DXF/DWG."
            ),
            status_code=status.HTTP_404_NOT_FOUND,
            mcp_context_id=mcp_context_id,
        )

    METRICS.dashboard_runs_total.labels(event="cad_streamed").inc()
    return FileResponse(
        candidate,
        media_type="application/dxf",
        filename=f"{mcp_context_id}.dxf",
    )


# ── DELETE /dashboard/runs/{id} ────────────────────────────────────────
@router.delete(
    "/runs/{mcp_context_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Hard-delete a run + all related rows + on-disk artefacts",
)
def delete_run(
    mcp_context_id: str,
    db: Session = Depends(_db_operator),
    user: CurrentUser = Depends(_operator_or_admin),
):
    deleted = runs_service.delete_run(db, mcp_context_id)
    if not deleted:
        raise AppError(
            error_code="NOT_FOUND",
            message=f"Run '{mcp_context_id}' not found.",
            status_code=status.HTTP_404_NOT_FOUND,
            mcp_context_id=mcp_context_id,
        )
    db.add(
        AuditLogAction(
            actor=user.actor,
            actor_role=user.role,
            action="run.delete",
            target_type="mcp_context",
            target_id=mcp_context_id,
            payload={},
            mcp_context_id=None,  # FK target is gone; null is allowed.
            ts=datetime.now(tz=timezone.utc),
        )
    )
    METRICS.dashboard_runs_total.labels(event="deleted").inc()
    log.info("run_deleted", run_id=mcp_context_id, actor=user.actor)
    return None


# ── POST /dashboard/runs ───────────────────────────────────────────────
@router.post(
    "/runs",
    response_model=RunCreatedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload a CAD file and enqueue a parse run",
)
async def create_run(
    background: BackgroundTasks,
    cad_file: UploadFile = File(..., description="DWG/IFC/STEP/DXF, <= 50 MB"),
    db: Session = Depends(_db_operator),
    user: CurrentUser = Depends(_operator_or_admin),
) -> RunCreatedResponse:
    raw = await cad_file.read()
    try:
        result = runs_service.create_run(
            db,
            filename=cad_file.filename or "upload.bin",
            file_bytes=raw,
            actor=user.actor,
        )
    except UploadRejected as e:
        # Map validation codes to HTTP statuses.
        http_code = (
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
            if e.code == "PAYLOAD_TOO_LARGE"
            else status.HTTP_400_BAD_REQUEST
        )
        raise AppError(error_code=e.code, message=e.message, status_code=http_code)

    # Audit-log all run creations. The 0007 migration widened actor_role to
    # accept viewer/operator/reviewer/admin/system/agent so we record the
    # caller's true role.
    db.add(
        AuditLogAction(
            actor=user.actor,
            actor_role=user.role,
            action="run.create",
            target_type="mcp_context",
            target_id=result["run_id"],
            payload={"upload_path": result["upload_path"]},
            mcp_context_id=result["run_id"],
            ts=datetime.now(tz=timezone.utc),
        )
    )

    METRICS.dashboard_runs_total.labels(event="created").inc()
    log.info("run_created", run_id=result["run_id"], actor=user.actor)

    # Commit NOW so the worker (running in a separate session / process) can
    # see the PENDING row before we enqueue.
    db.commit()

    # Enqueue the parse job. Backend selection (arq vs inline BackgroundTasks)
    # is decided by app.queue based on REDIS_URL / DASHBOARD_QUEUE_BACKEND.
    if os.getenv("DASHBOARD_DISABLE_INLINE_WORKER", "").strip() not in ("1", "true", "True"):
        job_id = await enqueue_parse_run(
            result["run_id"], fallback_background_tasks=background
        )
        log.info("run_enqueued", run_id=result["run_id"], job_id=job_id)

    return RunCreatedResponse(**result)


# ── WS /dashboard/runs/{id}/stream ─────────────────────────────────────
@router.websocket("/runs/{mcp_context_id}/stream")
async def stream_run(
    websocket: WebSocket,
    mcp_context_id: str,
) -> None:
    """Push stage_gate / hook_fire events for a single run.

    M1 implementation: poll the mcp_context row every 2s and push status
    deltas. M2 will replace this with a CDC-driven push (existing
    start_cdc_consumer.py).

    Auth: WebSocket protocols don't fire FastAPI HTTP dependencies cleanly,
    so we accept first then validate identity from the handshake.

    Browsers cannot set custom headers on a WebSocket, and Next.js dev
    rewrites do not proxy WS upgrades, so we also accept ``role`` (+ optional
    ``actor``) as query params for cross-origin dev. In production behind a
    reverse-proxy that forwards the cookie, the existing X-Role header path
    keeps working.
    """
    role_hdr = (
        websocket.headers.get("x-role", "")
        or websocket.query_params.get("role", "")
    ).strip().lower()
    from app.deps import ROLES  # local import to avoid circular at module import time
    if role_hdr not in ROLES:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    await websocket.accept()

    last_status: str | None = None

    async def _read_status_once() -> dict | None:
        from app.deps import _SessionLocal, init_engine
        init_engine()
        if _SessionLocal is None:
            return None
        with _SessionLocal() as session:
            return runs_service.get_run_detail(session, mcp_context_id)

    async def _emit(detail: dict) -> bool:
        """Send status frame; return True when terminal status reached."""
        nonlocal last_status
        if detail["status"] == last_status:
            return False
        last_status = detail["status"]
        await websocket.send_json(
            {
                "event": "status",
                "mcp_context_id": mcp_context_id,
                "status": last_status,
                "ts": datetime.now(tz=timezone.utc).isoformat(),
            }
        )
        return last_status in ("SUCCESS", "SUCCESS_WITH_WARNINGS", "ERROR")

    try:
        # Initial state -- always emit even if PENDING so client knows we're alive.
        detail = await _read_status_once()
        if detail is None:
            await websocket.send_json({"event": "not_found", "mcp_context_id": mcp_context_id})
            await websocket.close()
            return
        if await _emit(detail):
            await websocket.close()
            return

        # Subscribe to Redis pub/sub for push updates; fall back to polling
        # when the queue backend is "inline" (the context manager yields an
        # empty queue in that case so the timeout branch always fires).
        async with subscribe_run_events(mcp_context_id) as event_q:
            while True:
                try:
                    await asyncio.wait_for(event_q.get(), timeout=2.0)
                except asyncio.TimeoutError:
                    pass  # poll path below
                detail = await _read_status_once()
                if detail is None:
                    await websocket.send_json(
                        {"event": "not_found", "mcp_context_id": mcp_context_id}
                    )
                    await websocket.close()
                    return
                if await _emit(detail):
                    await websocket.close()
                    return
    except WebSocketDisconnect:
        return
