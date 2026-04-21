"""DB-touching tests for /dashboard/runs (POST + GET round-trip).

Skipped when POSTGRES_DSN is unset.
"""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text


pytestmark = [pytest.mark.db_fixture, pytest.mark.timeout(60)]


def _files():
    # Prefix with a valid DWG magic so upload-validator accepts it.
    return {"cad_file": ("smoke.dwg", io.BytesIO(b"AC1015" + b"hello-cad-world"), "application/octet-stream")}


def test_create_run_then_fetch(client: TestClient, auth_headers, db_session, monkeypatch):
    # This test asserts the M1 row-only contract (status stays PENDING right
    # after POST). Disable the inline worker so it doesn't auto-promote to
    # SUCCESS before our GET. End-to-end behaviour is covered in test_runs_e2e.
    monkeypatch.setenv("DASHBOARD_DISABLE_INLINE_WORKER", "1")
    r = client.post(
        "/dashboard/runs",
        headers=auth_headers("operator", actor="alice@example.com"),
        files=_files(),
    )
    assert r.status_code == 202, r.text
    body = r.json()
    run_id = body["run_id"]
    assert body["mcp_context_id"] == run_id
    assert body["status"] == "PENDING"

    detail = client.get(
        f"/dashboard/runs/{run_id}",
        headers=auth_headers("viewer"),
    )
    assert detail.status_code == 200, detail.text
    d = detail.json()
    assert d["mcp_context_id"] == run_id
    assert d["status"] == "PENDING"
    assert d["agent"] == "ParseAgent"

    # Verify audit_log_actions row was written by the API session
    # (use an out-of-band raw connection so we don't deadlock with db_session).
    import os
    import psycopg2

    raw = os.environ["POSTGRES_DSN"].replace("postgresql+psycopg2://", "postgresql://")
    conn = psycopg2.connect(raw, connect_timeout=10)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT actor, actor_role, action FROM audit_log_actions "
                "WHERE target_id = %s AND action = 'run.create'",
                (run_id,),
            )
            row = cur.fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row[0] == "alice@example.com"
    assert row[2] == "run.create"

    # Cleanup -- raw connection again (audit row has FK to mcp_contexts).
    conn = psycopg2.connect(raw, connect_timeout=10)
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM audit_log_actions WHERE target_id = %s", (run_id,))
            cur.execute("DELETE FROM mcp_contexts WHERE mcp_context_id = %s", (run_id,))
        conn.commit()
    finally:
        conn.close()


def test_get_run_404_envelope(client: TestClient, auth_headers):
    r = client.get(
        "/dashboard/runs/does-not-exist-xyz",
        headers=auth_headers("admin"),
    )
    assert r.status_code == 404
    body = r.json()
    assert body["error_code"] == "NOT_FOUND"
    assert body["mcp_context_id"] == "does-not-exist-xyz"


def test_empty_upload_rejected(client: TestClient, auth_headers):
    r = client.post(
        "/dashboard/runs",
        headers=auth_headers("admin"),
        files={"cad_file": ("empty.dwg", io.BytesIO(b""), "application/octet-stream")},
    )
    assert r.status_code == 400
    assert r.json()["error_code"] == "EMPTY_UPLOAD"
