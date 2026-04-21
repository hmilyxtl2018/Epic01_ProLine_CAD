"""Prometheus /metrics endpoint.

Open-by-default in dev; production should restrict via reverse-proxy ACL.
ADR-006 §Q3 explicitly noted this is acceptable for M1.
"""

from __future__ import annotations

from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST

from app.observability.metrics import render_metrics


router = APIRouter(tags=["observability"])


@router.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    return Response(content=render_metrics(), media_type=CONTENT_TYPE_LATEST)
