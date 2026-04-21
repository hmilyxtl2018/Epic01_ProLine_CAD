"""Unified error envelope + exception handlers.

All error responses MUST share this shape (ExcPlan §2.6.2):

    {"error_code": str, "message": str, "mcp_context_id": str|None, "retryable": bool}

Frontends rely on `error_code` for branching and `retryable` for retry UX.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException


log = logging.getLogger(__name__)


class ErrorEnvelope(BaseModel):
    """Stable error contract -- DO NOT change field names without bumping API version."""

    error_code: str = Field(..., description="Machine-readable error code (UPPER_SNAKE).")
    message: str = Field(..., description="Human-readable message; safe to display.")
    mcp_context_id: str | None = Field(
        default=None, description="Trace anchor; lets users copy-paste for support."
    )
    retryable: bool = Field(
        default=False, description="If true, client may retry without user intervention."
    )


class AppError(Exception):
    """Base for application-level errors that map to ErrorEnvelope."""

    def __init__(
        self,
        error_code: str,
        message: str,
        *,
        status_code: int = 400,
        retryable: bool = False,
        mcp_context_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.status_code = status_code
        self.retryable = retryable
        self.mcp_context_id = mcp_context_id


class KillswitchActive(AppError):
    """Raised when DASHBOARD_KILLSWITCH=true blocks /dashboard/* routes."""

    def __init__(self) -> None:
        super().__init__(
            error_code="KILLSWITCH_ACTIVE",
            message="Dashboard is in maintenance mode. Try again later.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            retryable=True,
        )


def _envelope(
    *,
    error_code: str,
    message: str,
    status_code: int,
    retryable: bool,
    mcp_context_id: str | None,
) -> JSONResponse:
    body = ErrorEnvelope(
        error_code=error_code,
        message=message,
        mcp_context_id=mcp_context_id,
        retryable=retryable,
    ).model_dump()
    return JSONResponse(status_code=status_code, content=body)


def _ctx_id(request: Request) -> str | None:
    # Populated by observability.middleware; safe fallback if middleware skipped.
    return getattr(request.state, "mcp_context_id", None)


def install_exception_handlers(app: FastAPI) -> None:
    """Wire all handlers onto the FastAPI instance."""

    @app.exception_handler(AppError)
    async def _handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        return _envelope(
            error_code=exc.error_code,
            message=exc.message,
            status_code=exc.status_code,
            retryable=exc.retryable,
            mcp_context_id=exc.mcp_context_id or _ctx_id(request),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_exc(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        # Map HTTP status -> coarse error_code for frontend branching.
        code_map = {
            400: "BAD_REQUEST",
            401: "UNAUTHORIZED",
            403: "FORBIDDEN",
            404: "NOT_FOUND",
            405: "METHOD_NOT_ALLOWED",
            409: "CONFLICT",
            413: "PAYLOAD_TOO_LARGE",
            415: "UNSUPPORTED_MEDIA_TYPE",
            422: "VALIDATION_ERROR",
            429: "RATE_LIMITED",
            503: "UNAVAILABLE",
        }
        return _envelope(
            error_code=code_map.get(exc.status_code, "HTTP_ERROR"),
            message=str(exc.detail) if exc.detail else "Request failed.",
            status_code=exc.status_code,
            retryable=exc.status_code in (429, 503),
            mcp_context_id=_ctx_id(request),
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Don't leak full pydantic dump (may include payload values); send first error.
        first = exc.errors()[0] if exc.errors() else {"msg": "validation failed"}
        loc = ".".join(str(p) for p in first.get("loc", ()))
        return _envelope(
            error_code="VALIDATION_ERROR",
            message=f"{loc}: {first.get('msg', 'invalid')}",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            retryable=False,
            mcp_context_id=_ctx_id(request),
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        # Last-resort handler: never leak stack traces to clients.
        log.exception("unhandled_exception path=%s", request.url.path)
        return _envelope(
            error_code="INTERNAL_ERROR",
            message="An unexpected error occurred.",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            retryable=True,
            mcp_context_id=_ctx_id(request),
        )
