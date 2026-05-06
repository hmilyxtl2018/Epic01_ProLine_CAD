"""/sites/{site_model_id}/constraints — Phase 2.2 CRUD + validator surface.

Routes:
  GET    /sites/{sid}/constraints                viewer+
  POST   /sites/{sid}/constraints                operator+ admin
  PATCH  /sites/{sid}/constraints/{cid}          operator+ admin
  DELETE /sites/{sid}/constraints/{cid}          operator+ admin   (soft-delete)
  GET    /sites/{sid}/constraints/validate       viewer+

All writes are funnelled through the same role gate as quarantine, and
every successful write emits an `audit_log_actions` row.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.deps import (
    CurrentUser,
    get_db_for,
    killswitch_gate,
    require_role,
)
from app.errors import AppError
from app.observability.logging import get_logger
from app.schemas.constraints import (
    ConstraintCreate,
    ConstraintItem,
    ConstraintListResponse,
    ConstraintUpdate,
    ValidationReport,
)
from app.services.constraints_validator import validate_constraints
from shared.db_schemas import AuditLogAction, ProcessConstraint, SiteModel
from shared.models import (
    ConstraintCategory,
    ConstraintParseMethod,
    ConstraintReviewStatus,
)


log = get_logger(__name__)

router = APIRouter(
    prefix="/sites",
    tags=["constraints"],
    dependencies=[Depends(killswitch_gate)],
)

_viewer_or_above = require_role("viewer", "operator", "reviewer", "admin")
_operator_or_admin = require_role("operator", "admin")
_db_viewer = get_db_for(_viewer_or_above)
_db_operator = get_db_for(_operator_or_admin)


_KIND_FILTERS = {"predecessor", "resource", "takt", "exclusion"}


# Allowed source -> targets for review_status (blueprint §2 state machine).
# 'superseded' is reserved for M4 conflict arbitration; not user-driven here.
_REVIEW_TRANSITIONS: dict[str, frozenset[str]] = {
    "draft":        frozenset({"draft", "under_review", "rejected"}),
    "under_review": frozenset({"under_review", "approved", "rejected"}),
    "approved":     frozenset({"approved", "superseded"}),
    "rejected":     frozenset({"rejected", "draft"}),
    "superseded":   frozenset({"superseded"}),
}


def _ensure_site(db: Session, site_model_id: str) -> None:
    """Raise 404 if the site_model business key does not exist."""
    exists = db.scalar(
        select(SiteModel.id).where(
            SiteModel.site_model_id == site_model_id,
            SiteModel.deleted_at.is_(None),
        )
    )
    if exists is None:
        raise AppError(
            error_code="NOT_FOUND",
            message=f"site_model '{site_model_id}' not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )


def _audit(db: Session, user: CurrentUser, action: str, cid: str, payload: dict) -> None:
    db.add(
        AuditLogAction(
            actor=user.actor,
            actor_role=user.role,
            action=action,
            target_type="process_constraint",
            target_id=cid,
            payload=payload,
        )
    )


# ── LIST ────────────────────────────────────────────────────────────────


@router.get(
    "/{site_model_id}/constraints",
    response_model=ConstraintListResponse,
    summary="List process constraints for a site model.",
)
def list_constraints(
    site_model_id: str = Path(..., min_length=1, max_length=50),
    db: Session = Depends(_db_viewer),
    _user: CurrentUser = Depends(_viewer_or_above),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    kind: str | None = Query(None),
    category: ConstraintCategory | None = Query(None),
    review_status: ConstraintReviewStatus | None = Query(None),
    active_only: bool = Query(True),
) -> ConstraintListResponse:
    _ensure_site(db, site_model_id)

    base = select(ProcessConstraint).where(
        ProcessConstraint.site_model_id == site_model_id,
        ProcessConstraint.deleted_at.is_(None),
    )
    if kind:
        if kind not in _KIND_FILTERS:
            raise AppError(
                error_code="VALIDATION_ERROR",
                message=f"unknown kind filter '{kind}'.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        base = base.where(ProcessConstraint.kind == kind)
    if category is not None:
        base = base.where(ProcessConstraint.category == category.value)
    if review_status is not None:
        base = base.where(ProcessConstraint.review_status == review_status.value)
    if active_only:
        base = base.where(ProcessConstraint.is_active.is_(True))

    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.scalars(
        base.order_by(ProcessConstraint.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    return ConstraintListResponse(
        items=[ConstraintItem.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


# ── CREATE ──────────────────────────────────────────────────────────────


@router.post(
    "/{site_model_id}/constraints",
    response_model=ConstraintItem,
    status_code=status.HTTP_201_CREATED,
    summary="Create one process constraint.",
)
def create_constraint(
    body: ConstraintCreate,
    site_model_id: str = Path(..., min_length=1, max_length=50),
    db: Session = Depends(_db_operator),
    user: CurrentUser = Depends(_operator_or_admin),
) -> ConstraintItem:
    _ensure_site(db, site_model_id)

    # `payload.model_dump(by_alias=True)` keeps "from"/"to" keys for predecessor.
    payload_dict = body.payload.model_dump(by_alias=True)
    kind = payload_dict["kind"]

    # blueprint G1/G2 defaults: manual UI rows are trusted (approved + verified now).
    review = (body.review_status or ConstraintReviewStatus.APPROVED).value
    parse_method = (body.parse_method or ConstraintParseMethod.MANUAL_UI).value
    category = (body.category or ConstraintCategory.OTHER).value
    now = datetime.now(tz=timezone.utc)
    verified_by = user.actor if review == ConstraintReviewStatus.APPROVED.value else None
    verified_at = now if review == ConstraintReviewStatus.APPROVED.value else None

    row = ProcessConstraint(
        constraint_id=body.constraint_id,
        site_model_id=site_model_id,
        kind=kind,
        payload=payload_dict,
        priority=body.priority,
        is_active=body.is_active,
        category=category,
        review_status=review,
        parse_method=parse_method,
        verified_by_user_id=verified_by,
        verified_at=verified_at,
        created_by=user.actor,
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError as e:
        db.rollback()
        raise AppError(
            error_code="CONFLICT",
            message=f"constraint_id '{body.constraint_id}' already exists.",
            status_code=status.HTTP_409_CONFLICT,
        ) from e

    _audit(db, user, "constraint.create", body.constraint_id,
           {"site_model_id": site_model_id, "kind": kind})
    db.commit()
    db.refresh(row)
    return ConstraintItem.model_validate(row)


# ── PATCH ───────────────────────────────────────────────────────────────


@router.patch(
    "/{site_model_id}/constraints/{constraint_id}",
    response_model=ConstraintItem,
    summary="Update payload / priority / active flag (kind cannot change).",
)
def update_constraint(
    body: ConstraintUpdate,
    site_model_id: str = Path(..., min_length=1, max_length=50),
    constraint_id: str = Path(..., min_length=1, max_length=64),
    db: Session = Depends(_db_operator),
    user: CurrentUser = Depends(_operator_or_admin),
) -> ConstraintItem:
    row = db.scalar(
        select(ProcessConstraint).where(
            ProcessConstraint.constraint_id == constraint_id,
            ProcessConstraint.site_model_id == site_model_id,
            ProcessConstraint.deleted_at.is_(None),
        )
    )
    if row is None:
        raise AppError(
            error_code="NOT_FOUND",
            message=f"constraint '{constraint_id}' not found in site '{site_model_id}'.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    changed: dict = {}
    if body.payload is not None:
        new_payload = body.payload.model_dump(by_alias=True)
        if new_payload["kind"] != row.kind:
            raise AppError(
                error_code="VALIDATION_ERROR",
                message=(
                    f"cannot change kind from '{row.kind}' to "
                    f"'{new_payload['kind']}'; delete and recreate."
                ),
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        row.payload = new_payload
        changed["payload"] = True
    if body.priority is not None:
        row.priority = body.priority
        changed["priority"] = body.priority
    if body.is_active is not None:
        row.is_active = body.is_active
        changed["is_active"] = body.is_active
    if body.category is not None:
        row.category = body.category.value
        changed["category"] = body.category.value
    if body.review_status is not None:
        new_status = body.review_status.value
        allowed = _REVIEW_TRANSITIONS.get(row.review_status, frozenset())
        if new_status not in allowed:
            raise AppError(
                error_code="VALIDATION_ERROR",
                message=(
                    f"illegal review_status transition "
                    f"'{row.review_status}' -> '{new_status}'."
                ),
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        row.review_status = new_status
        if new_status == ConstraintReviewStatus.APPROVED.value:
            row.verified_by_user_id = user.actor
            row.verified_at = datetime.now(tz=timezone.utc)
            row.needs_re_review = False
        changed["review_status"] = new_status
    if body.needs_re_review is not None:
        row.needs_re_review = body.needs_re_review
        changed["needs_re_review"] = body.needs_re_review

    if not changed:
        raise AppError(
            error_code="VALIDATION_ERROR",
            message="no updatable fields provided.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    row.updated_at = datetime.now(tz=timezone.utc)
    _audit(db, user, "constraint.update", constraint_id,
           {"site_model_id": site_model_id, "changed": list(changed.keys())})
    db.commit()
    db.refresh(row)
    return ConstraintItem.model_validate(row)


# ── DELETE (soft) ───────────────────────────────────────────────────────


@router.delete(
    "/{site_model_id}/constraints/{constraint_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft-delete a constraint.",
)
def delete_constraint(
    site_model_id: str = Path(..., min_length=1, max_length=50),
    constraint_id: str = Path(..., min_length=1, max_length=64),
    db: Session = Depends(_db_operator),
    user: CurrentUser = Depends(_operator_or_admin),
) -> None:
    row = db.scalar(
        select(ProcessConstraint).where(
            ProcessConstraint.constraint_id == constraint_id,
            ProcessConstraint.site_model_id == site_model_id,
            ProcessConstraint.deleted_at.is_(None),
        )
    )
    if row is None:
        raise AppError(
            error_code="NOT_FOUND",
            message=f"constraint '{constraint_id}' not found in site '{site_model_id}'.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    row.deleted_at = datetime.now(tz=timezone.utc)
    _audit(db, user, "constraint.delete", constraint_id,
           {"site_model_id": site_model_id})
    db.commit()


# ── VALIDATE ────────────────────────────────────────────────────────────


@router.get(
    "/{site_model_id}/constraints/validate",
    response_model=ValidationReport,
    summary="Run cycle / over-commit / takt sanity checks.",
)
def validate_site_constraints(
    site_model_id: str = Path(..., min_length=1, max_length=50),
    db: Session = Depends(_db_viewer),
    _user: CurrentUser = Depends(_viewer_or_above),
) -> ValidationReport:
    _ensure_site(db, site_model_id)
    rows = db.scalars(
        select(ProcessConstraint).where(
            ProcessConstraint.site_model_id == site_model_id,
            ProcessConstraint.deleted_at.is_(None),
        )
    ).all()
    return validate_constraints(site_model_id, list(rows))
