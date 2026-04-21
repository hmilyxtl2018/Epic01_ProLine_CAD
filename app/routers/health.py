"""Health probes -- intentionally NOT behind the killswitch."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.deps import get_db


router = APIRouter(tags=["health"])


@router.get("/healthz", summary="Liveness probe")
def healthz() -> dict[str, str]:
    """Liveness: process is up. Does NOT touch DB."""
    return {"status": "ok"}


@router.get("/readyz", summary="Readiness probe")
def readyz(db: Session = Depends(get_db)) -> dict[str, str]:
    """Readiness: DB is reachable. Used by load balancers before routing traffic."""
    db.execute(text("SELECT 1")).scalar()
    return {"status": "ready"}
