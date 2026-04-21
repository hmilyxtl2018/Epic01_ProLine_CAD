"""POST /auth/login -> JWT (Phase E1).

M2 stub: any non-empty email is accepted as long as the request supplies a
valid role and the configured dev password. Production will replace this
handler with an SSO callback or a real user store. The token format is
already final.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, EmailStr, Field

from app.deps import ROLES, CurrentUser, get_current_user
from app.errors import AppError
from app.security.auth import issue_token
from app.security.cookies import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    cookie_secure,
    make_csrf_token,
)


router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=200)
    role: str = Field(..., min_length=1, max_length=20)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    role: str


def _dev_password() -> str:
    return os.getenv("DASHBOARD_DEV_PASSWORD", "changeme")


@router.post(
    "/login",
    response_model=LoginResponse,
    status_code=status.HTTP_200_OK,
    summary="Issue a short-lived JWT for dashboard API access (M2 stub).",
)
async def login(req: LoginRequest) -> LoginResponse:
    role = req.role.strip().lower()
    if role not in ROLES:
        raise AppError(
            error_code="VALIDATION_ERROR",
            message=f"Unknown role '{req.role}'.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if req.password != _dev_password():
        raise AppError(
            error_code="UNAUTHORIZED",
            message="Invalid credentials.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    token, expires_in = issue_token(actor=req.email, role=role)
    return LoginResponse(
        access_token=token,
        expires_in=expires_in,
        role=role,
    )


# ── Cookie session (Phase E1.2 — preferred for browser clients) ───────


class MeResponse(BaseModel):
    actor: str
    role: str


class LogoutResponse(BaseModel):
    ok: bool = True


def _set_session_cookies(response: Response, *, token: str, ttl_s: int, actor: str) -> None:
    """Write httpOnly session cookie + JS-readable CSRF cookie."""
    secure = cookie_secure()
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=ttl_s,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        key=CSRF_COOKIE,
        value=make_csrf_token(actor),
        max_age=ttl_s,
        httponly=False,  # JS reads it to echo into X-CSRF-Token
        secure=secure,
        samesite="lax",
        path="/",
    )


@router.post(
    "/login-cookie",
    response_model=MeResponse,
    status_code=status.HTTP_200_OK,
    summary="Same as /auth/login but returns the JWT in an httpOnly cookie + sets CSRF.",
)
async def login_cookie(req: LoginRequest, response: Response) -> MeResponse:
    role = req.role.strip().lower()
    if role not in ROLES:
        raise AppError(
            error_code="VALIDATION_ERROR",
            message=f"Unknown role '{req.role}'.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if req.password != _dev_password():
        raise AppError(
            error_code="UNAUTHORIZED",
            message="Invalid credentials.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    token, expires_in = issue_token(actor=req.email, role=role)
    _set_session_cookies(response, token=token, ttl_s=expires_in, actor=req.email)
    return MeResponse(actor=req.email, role=role)


@router.post(
    "/logout",
    response_model=LogoutResponse,
    status_code=status.HTTP_200_OK,
    summary="Clear the session cookies (idempotent).",
)
async def logout(response: Response) -> LogoutResponse:
    # Empty values + max_age=0 instructs the browser to delete the cookies.
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
    return LogoutResponse(ok=True)


@router.get(
    "/me",
    response_model=MeResponse,
    status_code=status.HTTP_200_OK,
    summary="Return the current authenticated identity (cookie or bearer).",
)
async def me(user: CurrentUser = Depends(get_current_user)) -> MeResponse:
    return MeResponse(actor=user.actor, role=user.role)
