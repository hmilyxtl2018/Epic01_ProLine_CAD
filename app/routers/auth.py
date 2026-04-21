"""POST /auth/login -> JWT (Phase E1).

M2 stub: any non-empty email is accepted as long as the request supplies a
valid role and the configured dev password. Production will replace this
handler with an SSO callback or a real user store. The token format is
already final.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, status
from pydantic import BaseModel, EmailStr, Field

from app.deps import ROLES
from app.errors import AppError
from app.security.auth import issue_token


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
