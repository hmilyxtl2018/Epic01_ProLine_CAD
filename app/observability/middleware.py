"""Per-request middleware: request_id, mcp_context_id, access log, metrics.

Order matters -- this middleware runs OUTSIDE the OTel FastAPI instrumentation
so it can read the trace context after OTel has populated it.
"""

from __future__ import annotations

import time
import uuid
from typing import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.observability.metrics import METRICS


_REQUEST_ID_HEADER = "X-Request-ID"
_CTX_ID_HEADER = "X-MCP-Context-ID"


def _route_label(request: Request) -> str:
    """Extract the templated route path so high-cardinality URLs don't blow up Prom."""
    route = request.scope.get("route")
    if route is not None and getattr(route, "path", None):
        return route.path
    # Fallback for unmatched paths -- group under a single label.
    return "<unmatched>"


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Stamp request_id + mcp_context_id, emit JSON access log, record metrics."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get(_REQUEST_ID_HEADER) or uuid.uuid4().hex
        mcp_context_id = request.headers.get(_CTX_ID_HEADER)

        request.state.request_id = request_id
        request.state.mcp_context_id = mcp_context_id

        # Bind to structlog contextvars so EVERY log line in this request
        # automatically carries these fields.
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            mcp_context_id=mcp_context_id,
            method=request.method,
            path=request.url.path,
        )

        log = structlog.get_logger("app.access")
        start = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            elapsed = time.perf_counter() - start
            route = _route_label(request)
            METRICS.http_request_duration_seconds.labels(
                method=request.method, route=route, status=str(status_code)
            ).observe(elapsed)
            METRICS.http_requests_total.labels(
                method=request.method, route=route, status=str(status_code)
            ).inc()
            log.info(
                "http_request",
                status=status_code,
                duration_ms=round(elapsed * 1000, 2),
                route=route,
            )
            # Echo request_id back so frontend can correlate.
            try:
                response.headers[_REQUEST_ID_HEADER] = request_id  # type: ignore[name-defined]
            except (NameError, AttributeError):
                # `response` may not exist if call_next raised before assignment.
                pass
            structlog.contextvars.clear_contextvars()
