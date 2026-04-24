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

    row = ProcessConstraint(
        constraint_id=body.constraint_id,
        site_model_id=site_model_id,
        kind=kind,
        payload=payload_dict,
        priority=body.priority,
        is_active=body.is_active,
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
