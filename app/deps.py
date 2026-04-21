"""FastAPI dependencies: DB session, RBAC role gate, killswitch gate.

RBAC v0 (per ADR-006 + ExcPlan §2.6.4):
  - 4 application roles: viewer / operator / reviewer / admin
  - Role is read from the X-Role header (M1: trust the header; M3: JWT).
  - Use require_role(*allowed) as a Depends(...) on each route.

Killswitch:
  - When env DASHBOARD_KILLSWITCH=true, all /dashboard/* routes raise 503.
  - Health/metrics endpoints intentionally bypass the killswitch.
"""

from __future__ import annotations

import os
from typing import Iterable, Iterator

from fastapi import Depends, Header, status
from fastapi import Request
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.errors import AppError, KillswitchActive


ROLES: tuple[str, ...] = ("viewer", "operator", "reviewer", "admin")


# ── DB engine / session ────────────────────────────────────────────────
_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def _resolve_dsn() -> str:
    dsn = os.environ.get("POSTGRES_DSN", "").strip()
    if not dsn:
        raise RuntimeError(
            "POSTGRES_DSN is not set. The Dashboard backend cannot start "
            "without a database. See scripts/dev_up.ps1 to bring one up."
        )
    return dsn


def init_engine(dsn: str | None = None) -> Engine:
    """Create the global engine. Safe to call multiple times (returns cached)."""
    global _engine, _SessionLocal
    if _engine is not None:
        return _engine
    _engine = create_engine(
        dsn or _resolve_dsn(),
        future=True,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )
    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)
    return _engine


def dispose_engine() -> None:
    """Tear down the engine (used by lifespan shutdown + tests)."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None


def get_db() -> Iterator[Session]:
    """FastAPI dependency: yields a session; rolls back on uncaught exception."""
    if _SessionLocal is None:
        init_engine()
    assert _SessionLocal is not None
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# Application role -> PostgreSQL role mapping (Phase E2).
_PG_ROLE_BY_APP_ROLE: dict[str, str] = {
    "viewer": "app_viewer",
    "operator": "app_operator",
    "reviewer": "app_reviewer",
    "admin": "app_admin",
}


def _disable_rls_role_switch() -> bool:
    return os.getenv("DASHBOARD_DISABLE_RLS_ROLE_SWITCH", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def get_db_with_role(
    user: "CurrentUser" = None,  # type: ignore[assignment]  -- filled by Depends
) -> Iterator[Session]:
    """Yield a session with `SET LOCAL ROLE app_<role>` applied.

    The role switch is scoped to the surrounding transaction so it is
    automatically reverted on commit/rollback (`SET LOCAL` semantics). This
    is the entry point for any route that should be subject to RLS.

    Set `DASHBOARD_DISABLE_RLS_ROLE_SWITCH=1` (default in tests + on the
    DB-lite container that has no app_* roles) to fall back to a normal
    session.
    """
    from sqlalchemy import text

    if _SessionLocal is None:
        init_engine()
    assert _SessionLocal is not None
    session = _SessionLocal()
    try:
        if user is not None and not _disable_rls_role_switch():
            pg_role = _PG_ROLE_BY_APP_ROLE.get(user.role)
            if pg_role:
                # Begin a transaction so SET LOCAL has scope.
                session.execute(text(f"SET LOCAL ROLE {pg_role}"))
                # Identity GUC consumed by RLS policies on audit_log_actions.
                # Use parameter binding to defeat any quoting attack on actor.
                session.execute(
                    text("SELECT set_config('app.current_actor', :actor, true)"),
                    {"actor": user.actor},
                )
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db_for(user_dep):
    """Build a get_db dep that resolves `user` via the supplied dependency.

    Usage:
        db: Session = Depends(get_db_for(require_role('operator','admin')))
    """

    def _dep(
        user: "CurrentUser" = Depends(user_dep),
    ) -> Iterator[Session]:
        yield from get_db_with_role(user)

    return _dep


# ── RBAC ───────────────────────────────────────────────────────────────
class CurrentUser:
    """Identity resolved from the X-Role header (v0 trust-the-header model)."""

    __slots__ = ("role", "actor")

    def __init__(self, role: str, actor: str) -> None:
        self.role = role
        self.actor = actor


def get_current_user(
    request: Request,
    x_role: str | None = Header(default=None, alias="X-Role"),
    x_actor: str | None = Header(default=None, alias="X-Actor"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> CurrentUser:
    """Resolve identity from a Bearer JWT, falling back to X-Role/X-Actor.

    Precedence:
      1. `Authorization: Bearer <jwt>` -> claims override headers entirely.
      2. `proline_session` cookie + `X-CSRF-Token` (state-changing methods
         only) -> claims used; CSRF mismatch -> 403.
      3. `X-Role` / `X-Actor` -- legacy M1 trust-the-header path. Kept on so
         existing tests and internal tooling keep working through M2.
    """
    # 1. JWT path (Authorization header)
    if authorization and authorization.lower().startswith("bearer "):
        from app.security.auth import AuthError, decode_token

        token = authorization.split(" ", 1)[1].strip()
        try:
            claims = decode_token(token)
        except AuthError as e:
            raise AppError(
                error_code="UNAUTHORIZED",
                message=e.message,
                status_code=status.HTTP_401_UNAUTHORIZED,
            ) from e
        if claims.role not in ROLES:
            raise AppError(
                error_code="UNAUTHORIZED",
                message=f"Token role '{claims.role}' is not a known role.",
                status_code=status.HTTP_401_UNAUTHORIZED,
            )
        return CurrentUser(role=claims.role, actor=claims.sub[:200])

    # 2. Cookie session path
    cookie_token = request.cookies.get("proline_session")
    if cookie_token:
        from app.security.auth import AuthError, decode_token
        from app.security.cookies import CSRF_COOKIE, CSRF_HEADER, verify_csrf_token

        try:
            claims = decode_token(cookie_token)
        except AuthError as e:
            raise AppError(
                error_code="UNAUTHORIZED",
                message=e.message,
                status_code=status.HTTP_401_UNAUTHORIZED,
            ) from e
        if claims.role not in ROLES:
            raise AppError(
                error_code="UNAUTHORIZED",
                message=f"Token role '{claims.role}' is not a known role.",
                status_code=status.HTTP_401_UNAUTHORIZED,
            )
        # CSRF check: required for state-changing methods. Safe methods
        # (GET/HEAD/OPTIONS) are exempt -- same-origin policy + SameSite=Lax
        # already protects them from cross-site reads.
        if request.method.upper() not in ("GET", "HEAD", "OPTIONS"):
            csrf_cookie = request.cookies.get(CSRF_COOKIE, "")
            csrf_header = request.headers.get(CSRF_HEADER, "")
            if not csrf_cookie or csrf_cookie != csrf_header:
                raise AppError(
                    error_code="FORBIDDEN",
                    message="CSRF token missing or mismatched.",
                    status_code=status.HTTP_403_FORBIDDEN,
                )
            if not verify_csrf_token(csrf_cookie, claims.sub):
                raise AppError(
                    error_code="FORBIDDEN",
                    message="CSRF token failed signature verification.",
                    status_code=status.HTTP_403_FORBIDDEN,
                )
        return CurrentUser(role=claims.role, actor=claims.sub[:200])

    # 2. Legacy header path
    if not x_role:
        raise AppError(
            error_code="UNAUTHORIZED",
            message="Missing X-Role header.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    role = x_role.strip().lower()
    if role not in ROLES:
        raise AppError(
            error_code="UNAUTHORIZED",
            message=f"Unknown role '{x_role}'.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    # Actor identity defaults to the role name itself in dev; production should
    # always send X-Actor (e.g. an email or service account id).
    return CurrentUser(role=role, actor=(x_actor or role).strip()[:200])


def require_role(*allowed: str):
    """Dependency factory: 403 unless the caller's role is in `allowed`."""
    allowed_set = frozenset(r.lower() for r in allowed)
    if not allowed_set.issubset(set(ROLES)):
        raise ValueError(f"require_role got unknown roles: {allowed_set - set(ROLES)}")

    def _dep(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role not in allowed_set:
            raise AppError(
                error_code="FORBIDDEN",
                message=f"Role '{user.role}' is not permitted for this action.",
                status_code=status.HTTP_403_FORBIDDEN,
            )
        return user

    return _dep


# ── Killswitch ────────────────────────────────────────────────────────
def killswitch_gate() -> None:
    """Dependency: 503 when DASHBOARD_KILLSWITCH=true.

    Apply at router level on /dashboard/* only -- /healthz /metrics MUST stay up
    so platform monitoring still works during maintenance.
    """
    if os.getenv("DASHBOARD_KILLSWITCH", "").strip().lower() in ("1", "true", "yes"):
        raise KillswitchActive()
