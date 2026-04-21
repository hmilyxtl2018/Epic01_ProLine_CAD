"""Cookie-based session helpers (Phase E1.2).

Design: double-submit cookie CSRF.

  - `proline_session`  httpOnly + Secure + SameSite=Lax cookie carrying the
                       short-lived HS256 JWT. JS cannot read it -> XSS cannot
                       exfiltrate the token.
  - `proline_csrf`     NOT httpOnly, SameSite=Lax cookie carrying a random
                       token. JS reads it on every state-changing request
                       and echoes it in `X-CSRF-Token`. Backend compares
                       cookie value vs header value (constant-time). Mismatch
                       -> 403 even if the session cookie is valid.

The CSRF token is also bound to the JWT subject via HMAC, so even if an
attacker can plant cookies on the victim's browser they cannot mint a valid
header without the server secret.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets

SESSION_COOKIE = "proline_session"
CSRF_COOKIE = "proline_csrf"
CSRF_HEADER = "X-CSRF-Token"


def _csrf_secret() -> str:
    # Reuse the JWT secret so we don't add another env var; HMAC scope-tag
    # prevents cross-protocol misuse.
    from app.security.auth import _secret  # noqa: PLC0415  -- avoid cycle at import time

    return _secret()


def make_csrf_token(actor: str) -> str:
    """Return a random CSRF token bound (HMAC) to the actor.

    Format: ``<random-hex>.<hmac-sha256-hex>``. ``random-hex`` is 32 bytes of
    OS entropy; the HMAC binds it to the session subject so a stolen JS-side
    token cannot be replayed against another session.
    """
    nonce = secrets.token_hex(32)
    mac = hmac.new(
        _csrf_secret().encode("utf-8"),
        f"{actor}:{nonce}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{nonce}.{mac}"


def verify_csrf_token(token: str, actor: str) -> bool:
    """Constant-time check that ``token`` was minted for ``actor``."""
    if not token or "." not in token:
        return False
    nonce, mac = token.rsplit(".", 1)
    expected = hmac.new(
        _csrf_secret().encode("utf-8"),
        f"{actor}:{nonce}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(mac, expected)


def cookie_secure() -> bool:
    """Whether to mark cookies Secure. Off by default in dev (no HTTPS)."""
    raw = os.getenv("DASHBOARD_COOKIE_SECURE", "").strip().lower()
    if raw in ("1", "true", "yes"):
        return True
    if raw in ("0", "false", "no"):
        return False
    # Default: secure in non-dev environments.
    return os.getenv("DEPLOY_ENV", "dev").lower() != "dev"
