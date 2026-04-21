"""DB-touching tests for the ParseAgent worker (PENDING -> SUCCESS / ERROR loop).

Skipped when POSTGRES_DSN is unset.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import select

from app.workers.parse_agent_worker import (
    PARSE_AGENT_NAME,
    STATUS_ERROR,
    STATUS_PENDING,
    STATUS_RUNNING,
    STATUS_SUCCESS,
    process_one,
)
from shared.db_schemas import McpContext


pytestmark = [pytest.mark.db_fixture, pytest.mark.timeout(60)]


@pytest.fixture(autouse=True)
def _purge_pending(_db_dsn):
    """Drop any leftover PENDING ParseAgent rows so worker tests start clean.

    Out-of-band psycopg2 connection -- avoids row-lock contention with the
    transactional db_session fixture.
    """
    import psycopg2
    raw = _db_dsn.replace("postgresql+psycopg2://", "postgresql://")

    def _purge():
        conn = psycopg2.connect(raw, connect_timeout=10)
        try:
            with conn.cursor() as cur:
                # FK: audit_log_actions.mcp_context_id -> mcp_contexts(mcp_context_id).
                # Delete audit rows first, then the parent mcp_contexts rows.
                cur.execute(
                    "DELETE FROM audit_log_actions WHERE mcp_context_id IN ("
                    "  SELECT mcp_context_id FROM mcp_contexts "
                    "  WHERE agent = %s AND status IN ('PENDING','RUNNING')"
                    ")",
                    (PARSE_AGENT_NAME,),
                )
                cur.execute(
                    "DELETE FROM mcp_contexts "
                    "WHERE agent = %s AND status IN ('PENDING','RUNNING')",
                    (PARSE_AGENT_NAME,),
                )
            conn.commit()
        finally:
            conn.close()

    _purge()
    yield
    _purge()


def _seed_pending(db, *, upload_path: str, filename: str = "test.dwg") -> str:
    run_id = uuid.uuid4().hex
    db.add(
        McpContext(
            mcp_context_id=run_id,
            agent=PARSE_AGENT_NAME,
            agent_version="v1.0",
            input_payload={
                "upload_path": upload_path,
                "filename": filename,
                "size_bytes": 0,
                "submitted_by": "tester@example.com",
            },
            timestamp=datetime.now(tz=timezone.utc),
            status=STATUS_PENDING,
        )
    )
    db.commit()
    return run_id


def _cleanup(_db_dsn, run_id: str) -> None:
    """Out-of-band cleanup -- mirrors the pattern in test_runs_api."""
    import psycopg2
    raw = _db_dsn.replace("postgresql+psycopg2://", "postgresql://")
    conn = psycopg2.connect(raw, connect_timeout=10)
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM mcp_contexts WHERE mcp_context_id = %s", (run_id,))
        conn.commit()
    finally:
        conn.close()


def test_process_one_no_pending(db_session):
    """When no PENDING ParseAgent rows exist, returns None cleanly."""
    # Make sure there is no leftover -- we don't insert anything.
    # (Other tests may have left rows; only PENDING ones matter.)
    result = process_one(db_session)
    assert result is None


def test_process_one_success(db_session, _db_dsn, tmp_path):
    upload = tmp_path / "good.dwg"
    upload.write_bytes(b"fake-cad-bytes-OK")

    run_id = _seed_pending(db_session, upload_path=str(upload))

    try:
        # Use a fresh session so the worker's commit path is realistic.
        result = process_one(db_session)
        assert result == run_id

        row = db_session.scalar(
            select(McpContext).where(McpContext.mcp_context_id == run_id)
        )
        db_session.refresh(row)
        assert row.status == STATUS_SUCCESS
        assert row.error_message is None
        assert (row.output_payload or {}).get("bytes_read") == len(b"fake-cad-bytes-OK")
        assert isinstance(row.latency_ms, int) and row.latency_ms >= 0
    finally:
        _cleanup(_db_dsn, run_id)


def test_process_one_missing_file_marks_error(db_session, _db_dsn):
    bogus = "/nonexistent/path/should/not/exist.dwg"
    run_id = _seed_pending(db_session, upload_path=bogus)

    try:
        result = process_one(db_session)
        assert result == run_id

        row = db_session.scalar(
            select(McpContext).where(McpContext.mcp_context_id == run_id)
        )
        db_session.refresh(row)
        assert row.status == STATUS_ERROR
        assert row.error_message is not None
        assert "not found" in row.error_message.lower()
        assert isinstance(row.latency_ms, int)
    finally:
        _cleanup(_db_dsn, run_id)
