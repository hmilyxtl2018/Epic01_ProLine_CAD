"""RBAC + validation tests for /dashboard/quarantine.

These mirror the style of test_rbac.py: we don't need a real DB row for
the FORBIDDEN assertions because RBAC runs before the route body. Tests
that *would* exercise the DB are skipped when POSTGRES_DSN is unset.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient


# ── GET /dashboard/quarantine ──────────────────────────────────────────


@pytest.mark.parametrize("role", ["viewer", "operator", "reviewer", "admin"])
def test_list_quarantine_open_to_viewer_plus(client: TestClient, auth_headers, role):
    r = client.get("/dashboard/quarantine", headers=auth_headers(role))
    # Without a real DB the call may surface as 500 INTERNAL_ERROR; that's
    # still RBAC pass-through. We only assert the gate doesn't reject.
    assert r.status_code != 403, f"role={role} should pass RBAC: {r.status_code} {r.text}"


def test_list_quarantine_rejects_unknown_status_filter(client: TestClient, auth_headers):
    r = client.get(
        "/dashboard/quarantine",
        headers=auth_headers("viewer"),
        params={"status": "bogus"},
    )
    assert r.status_code == 400
    assert r.json()["error_code"] == "VALIDATION_ERROR"


# ── POST /dashboard/quarantine/{id}/decide ─────────────────────────────


@pytest.mark.parametrize("role,allowed", [
    ("viewer", False),
    ("operator", False),
    ("reviewer", True),
    ("admin", True),
])
def test_decide_quarantine_role_gate(client: TestClient, auth_headers, role, allowed):
    r = client.post(
        "/dashboard/quarantine/00000000-0000-0000-0000-000000000000/decide",
        headers=auth_headers(role),
        json={"decision": "approve"},
    )
    if allowed:
        assert r.status_code != 403, f"role={role} should pass RBAC, got {r.status_code} {r.text}"
    else:
        assert r.status_code == 403, f"role={role} should be forbidden, got {r.status_code}"
        assert r.json()["error_code"] == "FORBIDDEN"


def test_decide_validates_payload(client: TestClient, auth_headers):
    r = client.post(
        "/dashboard/quarantine/anything/decide",
        headers=auth_headers("reviewer"),
        json={"decision": "weird-value"},
    )
    assert r.status_code == 422  # pydantic Literal mismatch
