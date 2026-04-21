"""Validation + envelope shape tests."""

from __future__ import annotations

from fastapi.testclient import TestClient


_ENVELOPE_KEYS = {"error_code", "message", "mcp_context_id", "retryable"}


def test_envelope_shape_on_404(client: TestClient, auth_headers) -> None:
    r = client.get("/dashboard/no-such-thing", headers=auth_headers("admin"))
    assert r.status_code == 404
    body = r.json()
    assert set(body.keys()) == _ENVELOPE_KEYS


def test_validation_error_is_envelope(client: TestClient, auth_headers) -> None:
    # page=0 fails ge=1 -> 422 -> handler -> envelope
    r = client.get(
        "/dashboard/runs",
        headers=auth_headers("admin"),
        params={"page": 0},
    )
    assert r.status_code == 422
    body = r.json()
    assert set(body.keys()) == _ENVELOPE_KEYS
    assert body["error_code"] == "VALIDATION_ERROR"


def test_request_id_echoed_back(client: TestClient) -> None:
    r = client.get("/healthz", headers={"X-Request-ID": "fixed-rid-xyz"})
    assert r.status_code == 200
    assert r.headers.get("X-Request-ID") == "fixed-rid-xyz"
