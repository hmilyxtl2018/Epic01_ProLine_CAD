"""End-to-end: POST /dashboard/runs upload triggers worker -> SUCCESS visible.

Skipped without POSTGRES_DSN.
"""

from __future__ import annotations

import io
import time

import psycopg2
import pytest
from fastapi.testclient import TestClient


pytestmark = [pytest.mark.db_fixture, pytest.mark.timeout(60)]


def _purge(_db_dsn) -> None:
    raw = _db_dsn.replace("postgresql+psycopg2://", "postgresql://")
    conn = psycopg2.connect(raw, connect_timeout=10)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM audit_log_actions "
                "WHERE mcp_context_id IN ("
                "  SELECT mcp_context_id FROM mcp_contexts "
                "  WHERE agent='ParseAgent' AND status IN ('PENDING','RUNNING','SUCCESS','ERROR')"
                ")"
            )
            cur.execute(
                "DELETE FROM mcp_contexts "
                "WHERE agent='ParseAgent' AND status IN ('PENDING','RUNNING','SUCCESS','ERROR')"
            )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture(autouse=True)
def _clean(_db_dsn):
    _purge(_db_dsn)
    yield
    _purge(_db_dsn)


def test_upload_then_worker_drives_to_success(
    client: TestClient, auth_headers, _db_dsn
):
    payload = b"AC1015" + b"end-to-end-payload"
    files = {"cad_file": ("e2e.dwg", io.BytesIO(payload), "application/octet-stream")}
    r = client.post(
        "/dashboard/runs",
        headers=auth_headers("operator", actor="ci@example.com"),
        files=files,
    )
    assert r.status_code == 202, r.text
    run_id = r.json()["run_id"]

    # BackgroundTasks runs *after* the response is sent. The TestClient context
    # manager already triggers task drain on response close, but the worker
    # opens its own session, so poll a few times to absorb commit latency.
    final_status = None
    for _ in range(20):
        d = client.get(f"/dashboard/runs/{run_id}", headers=auth_headers("viewer"))
        assert d.status_code == 200, d.text
        final_status = d.json()["status"]
        if final_status in ("SUCCESS", "SUCCESS_WITH_WARNINGS", "ERROR"):
            break
        time.sleep(0.1)

    assert final_status == "SUCCESS", f"final_status={final_status}"

    # Latency was captured.
    detail = client.get(f"/dashboard/runs/{run_id}", headers=auth_headers("viewer")).json()
    assert detail["output_payload"].get("bytes_read") == len(payload)
