"""Pure-unit tests for the JWT auth module + /auth/login route."""

from __future__ import annotations

import pytest

from app.security.auth import AuthError, decode_token, issue_token


# ── Module-level: issue_token / decode_token round-trip ────────────────


def test_round_trip_basic():
    token, exp_in = issue_token(actor="alice@example.com", role="operator")
    assert exp_in > 0
    claims = decode_token(token)
    assert claims.sub == "alice@example.com"
    assert claims.role == "operator"
    assert claims.exp > claims.iat


def test_decode_rejects_garbage():
    with pytest.raises(AuthError) as ei:
        decode_token("not-a-jwt")
    assert ei.value.code == "UNAUTHORIZED"


def test_decode_rejects_empty():
    with pytest.raises(AuthError):
        decode_token("")


def test_decode_rejects_expired():
    # Issue with negative TTL so the token is born already expired.
    token, _ = issue_token(actor="a@b.c", role="viewer", ttl_s=-10)
    with pytest.raises(AuthError):
        decode_token(token)


def test_decode_rejects_wrong_audience(monkeypatch):
    token, _ = issue_token(actor="a@b.c", role="viewer")
    monkeypatch.setenv("DASHBOARD_JWT_AUDIENCE", "different-aud")
    with pytest.raises(AuthError):
        decode_token(token)


# ── /auth/login route ─────────────────────────────────────────────────


def test_login_returns_token(client, monkeypatch):
    monkeypatch.setenv("DASHBOARD_DEV_PASSWORD", "s3cret")
    r = client.post(
        "/auth/login",
        json={"email": "alice@example.com", "password": "s3cret", "role": "operator"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["role"] == "operator"
    assert body["expires_in"] > 0
    claims = decode_token(body["access_token"])
    assert claims.sub == "alice@example.com"
    assert claims.role == "operator"


def test_login_wrong_password(client, monkeypatch):
    monkeypatch.setenv("DASHBOARD_DEV_PASSWORD", "s3cret")
    r = client.post(
        "/auth/login",
        json={"email": "x@y.z", "password": "WRONG", "role": "viewer"},
    )
    assert r.status_code == 401
    assert r.json()["error_code"] == "UNAUTHORIZED"


def test_login_unknown_role(client, monkeypatch):
    monkeypatch.setenv("DASHBOARD_DEV_PASSWORD", "s3cret")
    r = client.post(
        "/auth/login",
        json={"email": "x@y.z", "password": "s3cret", "role": "godmode"},
    )
    assert r.status_code == 400
    assert r.json()["error_code"] == "VALIDATION_ERROR"


def test_login_invalid_email(client):
    r = client.post(
        "/auth/login",
        json={"email": "not-an-email", "password": "s3cret", "role": "viewer"},
    )
    # FastAPI's pydantic validator returns 422 by default; we expect the same
    # envelope shape regardless of the chosen status.
    assert r.status_code in (400, 422)


# ── Bearer token accepted by RBAC dep (legacy header still works) ─────


def test_bearer_token_authorizes_request(client):
    token, _ = issue_token(actor="bob@example.com", role="viewer")
    # /dashboard/runs requires viewer+; without DB it'll 500 on the actual
    # query but should pass auth first. We assert it does NOT 401/403.
    r = client.get(
        "/dashboard/runs",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code not in (401, 403), r.text


def test_bearer_token_rejected_when_invalid(client):
    r = client.get(
        "/dashboard/runs",
        headers={"Authorization": "Bearer not.a.real.token"},
    )
    assert r.status_code == 401
    assert r.json()["error_code"] == "UNAUTHORIZED"


def test_legacy_x_role_header_still_works(client):
    r = client.get(
        "/dashboard/runs",
        headers={"X-Role": "viewer", "X-Actor": "carol@example.com"},
    )
    assert r.status_code not in (401, 403), r.text
