"""Smoke tests: /healthz is open, /readyz needs DB, error envelope shape."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient


def test_healthz_is_public(client: TestClient) -> None:
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_healthz_bypasses_killswitch(monkeypatch, app_factory) -> None:
    monkeypatch.setenv("DASHBOARD_KILLSWITCH", "true")
    app = app_factory()
    with TestClient(app) as c:
        r = c.get("/healthz")
        assert r.status_code == 200


@pytest.mark.db_fixture
def test_readyz_when_db_present(client: TestClient) -> None:
    if not os.environ.get("POSTGRES_DSN"):
        pytest.skip("POSTGRES_DSN not set")
    r = client.get("/readyz")
    assert r.status_code == 200
    assert r.json() == {"status": "ready"}


def test_404_uses_envelope(client: TestClient) -> None:
    r = client.get("/no-such-route")
    assert r.status_code == 404
    body = r.json()
    assert set(body.keys()) == {"error_code", "message", "mcp_context_id", "retryable"}
    assert body["error_code"] == "NOT_FOUND"
    assert body["retryable"] is False
