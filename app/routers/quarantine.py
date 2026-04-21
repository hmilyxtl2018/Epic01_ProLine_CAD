"""/dashboard/quarantine* -- Phase E2 reviewer surface.

Routes:
  GET  /dashboard/quarantine              viewer+   (list with status filter)
  POST /dashboard/quarantine/{id}/decide  reviewer + admin

Decisions are append-once: once `decision` is set on a row, subsequent POSTs
return 409 CONFLICT. Every decision writes a row to audit_log_actions.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.deps import (
    CurrentUser,
    get_db_for,
    killswitch_gate,
    require_role,
)
from app.errors import AppError
from app.observability.logging import get_logger
from app.observability.metrics import METRICS
from app.schemas.quarantine import (
    DecideRequest,
    DecideResponse,
    QuarantineItem,
    QuarantineListResponse,
)
from shared.db_schemas import AuditLogAction, QuarantineTerm, TaxonomyTerm


log = get_logger(__name__)

router = APIRouter(
    prefix="/dashboard",
    tags=["dashboard"],
    dependencies=[Depends(killswitch_gate)],
)

# Cached role-gate deps -- mirror dashboard_runs.py for FastAPI dedup.
_viewer_or_above = require_role("viewer", "operator", "reviewer", "admin")
_reviewer_or_admin = require_role("reviewer", "admin")
_db_viewer = get_db_for(_viewer_or_above)
_db_reviewer = get_db_for(_reviewer_or_admin)


_ALLOWED_STATUS_FILTERS = {"pending", "approve", "reject", "merge", "all"}


@router.get(
    "/quarantine",
    response_model=QuarantineListResponse,
    summary="List quarantine terms (paginated, newest first).",
)
def list_quarantine(
    db: Session = Depends(_db_viewer),
    _user: CurrentUser = Depends(_viewer_or_above),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    status_filter: str = Query(
        "pending",
        alias="status",
        description="One of: pending | approve | reject | merge | all.",
    ),
    asset_type: str | None = Query(None, max_length=30),
) -> QuarantineListResponse:
    sf = status_filter.strip().lower()
    if sf not in _ALLOWED_STATUS_FILTERS:
        raise AppError(
            error_code="VALIDATION_ERROR",
            message=f"Unknown status filter '{status_filter}'.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    base = select(QuarantineTerm).where(QuarantineTerm.deleted_at.is_(None))
    if sf == "pending":
        # 'pending' covers both NULL decision and explicit 'pending' decision.
        base = base.where(
            (QuarantineTerm.decision.is_(None)) | (QuarantineTerm.decision == "pending")
        )
    elif sf != "all":
        base = base.where(QuarantineTerm.decision == sf)
    if asset_type:
        base = base.where(QuarantineTerm.asset_type == asset_type)

    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0

    rows = (
        db.scalars(
            base.order_by(QuarantineTerm.last_seen.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .all()
    )

    METRICS.dashboard_runs_total.labels(event="quarantine_listed").inc()

    return QuarantineListResponse(
        items=[QuarantineItem.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/quarantine/{quarantine_id}/decide",
    response_model=DecideResponse,
    status_code=status.HTTP_200_OK,
    summary="Record a reviewer decision (approve / reject / merge).",
)
def decide_quarantine(
    payload: DecideRequest,
    quarantine_id: str = Path(..., min_length=1, max_length=64),
    db: Session = Depends(_db_reviewer),
    user: CurrentUser = Depends(_reviewer_or_admin),
) -> DecideResponse:
    row = db.get(QuarantineTerm, quarantine_id)
    if row is None or row.deleted_at is not None:
        raise AppError(
            error_code="NOT_FOUND",
            message=f"quarantine_term '{quarantine_id}' not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    if row.decision and row.decision != "pending":
        raise AppError(
            error_code="CONFLICT",
            message=f"quarantine_term '{quarantine_id}' already decided ({row.decision}).",
            status_code=status.HTTP_409_CONFLICT,
        )

    if payload.decision == "merge":
        if not payload.merge_target_id:
            raise AppError(
                error_code="VALIDATION_ERROR",
                message="merge_target_id is required when decision='merge'.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        target = db.get(TaxonomyTerm, payload.merge_target_id)
        if target is None:
            raise AppError(
                error_code="VALIDATION_ERROR",
                message=f"taxonomy_terms target '{payload.merge_target_id}' not found.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        row.merge_target_id = payload.merge_target_id
    else:
        # Defensive: clear any stale merge target on approve/reject.
        row.merge_target_id = None

    now = datetime.now(tz=timezone.utc)
    row.decision = payload.decision
    row.reviewer = user.actor
    row.reviewed_at = now

    db.add(
        AuditLogAction(
            actor=user.actor,
            actor_role=user.role,
            action=f"quarantine.{payload.decision}",
            target_type="quarantine_term",
            target_id=quarantine_id,
            payload={
                "merge_target_id": row.merge_target_id,
                "reason": payload.reason,
                "term_normalized": row.term_normalized,
                "asset_type": row.asset_type,
            },
            mcp_context_id=row.mcp_context_id,
            ts=now,
        )
    )

    METRICS.dashboard_runs_total.labels(event=f"quarantine_{payload.decision}").inc()
    log.info(
        "quarantine_decided",
        quarantine_id=quarantine_id,
        decision=payload.decision,
        actor=user.actor,
    )

    return DecideResponse(
        id=quarantine_id,
        decision=payload.decision,
        reviewer=user.actor,
        reviewed_at=now,
    )
