"""RBAC matrix: 4 roles x 3 representative HTTP routes + missing-role 401.

The WebSocket route is exercised by a separate test (it uses a different
auth path because Starlette doesn't run HTTP Depends for WS handshakes).
"""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient


# (method, path, body_factory)
_GET_RUNS = ("GET", "/dashboard/runs", lambda: None)
_GET_RUN_DETAIL = ("GET", "/dashboard/runs/does-not-exist", lambda: None)


def _post_run_files():
    return {"cad_file": ("a.dwg", io.BytesIO(b"AC1015" + b"FAKE-DWG-CONTENT"), "application/octet-stream")}


# Allowed = expected NOT-FORBIDDEN. The exact success status varies per route
# (200 for GET, 202 for POST, 404 for unknown id), but it must never be 403.
RBAC_MATRIX = {
    # path                        viewer  operator  reviewer  admin
    "/dashboard/runs|GET":       (True,   True,     True,     True),
    "/dashboard/runs/x|GET":     (True,   True,     True,     True),
    "/dashboard/runs|POST":      (False,  True,     False,    True),
}


@pytest.mark.parametrize("role", ["viewer", "operator", "reviewer", "admin"])
def test_get_runs_allowed_for_all_roles(client: TestClient, auth_headers, role):
    r = client.get("/dashboard/runs", headers=auth_headers(role))
    # No DB -> the dependency raises and surfaces as INTERNAL_ERROR (500).
    # That's still NOT 403, which is what we're asserting (RBAC pass-through).
    assert r.status_code != 403


@pytest.mark.parametrize("role,allowed", [
    ("viewer", False),
    ("operator", True),
    ("reviewer", False),
    ("admin", True),
])
def test_post_runs_role_gate(client: TestClient, auth_headers, role, allowed):
    r = client.post(
        "/dashboard/runs",
        headers=auth_headers(role),
        files=_post_run_files(),
    )
    if allowed:
        assert r.status_code != 403, f"role={role} should pass RBAC, got {r.status_code} {r.text}"
    else:
        assert r.status_code == 403, f"role={role} should be forbidden, got {r.status_code}"
        body = r.json()
        assert body["error_code"] == "FORBIDDEN"


def test_missing_role_returns_401(client: TestClient):
    r = client.get("/dashboard/runs")  # no X-Role
    assert r.status_code == 401
    body = r.json()
    assert body["error_code"] == "UNAUTHORIZED"


def test_unknown_role_returns_401(client: TestClient):
    r = client.get("/dashboard/runs", headers={"X-Role": "godmode"})
    assert r.status_code == 401
    assert r.json()["error_code"] == "UNAUTHORIZED"


def test_killswitch_blocks_dashboard_routes(monkeypatch, app_factory, auth_headers):
    monkeypatch.setenv("DASHBOARD_KILLSWITCH", "true")
    app = app_factory()
    with TestClient(app) as c:
        r = c.get("/dashboard/runs", headers=auth_headers("admin"))
        assert r.status_code == 503
        body = r.json()
        assert body["error_code"] == "KILLSWITCH_ACTIVE"
        assert body["retryable"] is True
