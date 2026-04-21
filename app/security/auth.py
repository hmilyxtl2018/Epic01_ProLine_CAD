"""HS256 JWT issue / verify (Phase E1).

Why HS256 and not RS256?
    M2 ships a single-process backend; the secret can live in env. When we
    add a second issuer (e.g. SSO) we will swap to RS256 + JWKS. The
    interface here (`issue_token` / `decode_token`) is stable across that
    migration.

Configuration:
    DASHBOARD_JWT_SECRET     (required for non-test runs; tests use a fixed
                              dev secret so cassettes stay reproducible.)
    DASHBOARD_JWT_TTL_S      (default 3600)
    DASHBOARD_JWT_ISSUER     (default "proline-dashboard")
    DASHBOARD_JWT_AUDIENCE   (default "dashboard-api")
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

from jose import JWTError, jwt


_DEFAULT_TTL_S = 3600
_DEFAULT_ALG = "HS256"
_DEFAULT_ISS = "proline-dashboard"
_DEFAULT_AUD = "dashboard-api"
_DEV_SECRET = "dev-only-secret-do-not-use-in-prod"


class AuthError(Exception):
    """Raised when a token is missing, malformed, expired, or has wrong claims."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class TokenClaims:
    sub: str  # actor (email or service account id)
    role: str  # one of app.deps.ROLES
    iat: int
    exp: int
    iss: str
    aud: str


def _secret() -> str:
    return os.getenv("DASHBOARD_JWT_SECRET", "").strip() or _DEV_SECRET


def _ttl_s() -> int:
    raw = os.getenv("DASHBOARD_JWT_TTL_S", "").strip()
    try:
        return int(raw) if raw else _DEFAULT_TTL_S
    except ValueError:
        return _DEFAULT_TTL_S


def _issuer() -> str:
    return os.getenv("DASHBOARD_JWT_ISSUER", _DEFAULT_ISS)


def _audience() -> str:
    return os.getenv("DASHBOARD_JWT_AUDIENCE", _DEFAULT_AUD)


def issue_token(*, actor: str, role: str, ttl_s: int | None = None) -> tuple[str, int]:
    """Sign and return (token, expires_in_seconds)."""
    now = int(time.time())
    expires_in = ttl_s or _ttl_s()
    payload = {
        "sub": actor,
        "role": role,
        "iat": now,
        "exp": now + expires_in,
        "iss": _issuer(),
        "aud": _audience(),
    }
    token = jwt.encode(payload, _secret(), algorithm=_DEFAULT_ALG)
    return token, expires_in


def decode_token(token: str) -> TokenClaims:
    """Verify signature, exp, iss, aud. Raise AuthError on any failure."""
    if not token:
        raise AuthError("UNAUTHORIZED", "Empty bearer token.")
    try:
        payload = jwt.decode(
            token,
            _secret(),
            algorithms=[_DEFAULT_ALG],
            audience=_audience(),
            issuer=_issuer(),
        )
    except JWTError as e:
        raise AuthError("UNAUTHORIZED", f"Invalid token: {e}") from e

    sub = payload.get("sub")
    role = payload.get("role")
    if not sub or not role:
        raise AuthError("UNAUTHORIZED", "Token missing 'sub' or 'role' claim.")
    return TokenClaims(
        sub=str(sub),
        role=str(role).lower(),
        iat=int(payload.get("iat", 0)),
        exp=int(payload.get("exp", 0)),
        iss=str(payload.get("iss", "")),
        aud=str(payload.get("aud", "")),
    )
