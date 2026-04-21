"""End-to-end test for promote_taxonomy_terms.py --db dual-write.

Validates the full producer -> aggregator -> quarantine_terms flow:
  1. Synthetic jsonl producer (mimics propose_taxonomy_term output).
  2. Aggregation script run with --db.
  3. Verify rows in quarantine_terms table.
  4. Re-run with new evidence -> verify pending row is updated, count grows.
  5. Mark a row as 'approve' -> re-run -> verify approved row is NOT clobbered.

Catches: schema drift between Pydantic Aggregated <-> DB columns,
ON CONFLICT WHERE clause behavior, decision-preservation invariant.

Note on timeouts: psycopg2.connect() takes ~5-10s on Windows when another
SQLAlchemy/psycopg2 connection is already open in the same process (IPv6
fallback through Docker Desktop port-forward). On Linux CI it is sub-second.
Tests therefore set pytest.mark.timeout(120) explicitly to tolerate the
Windows dev-loop slowness.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest
import psycopg2
from sqlalchemy import text

from scripts import promote_taxonomy_terms as ptt


pytestmark = [
    pytest.mark.db_fixture,
    pytest.mark.timeout(120),
]


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


def _raw_dsn(_db_dsn: str) -> str:
    """psycopg2 wants libpq form, not SQLAlchemy URL."""
    return _db_dsn.replace("postgresql+psycopg2://", "postgresql://", 1)


def test_promote_dual_write_inserts_and_updates(tmp_path, db_session, _db_dsn):
    """First run inserts; second run with more evidence updates count + last_seen."""
    quarantine_dir = tmp_path / "quarantine"
    csv_out = tmp_path / "review.csv"

    # Use a unique term per test run to avoid cross-test interference (the
    # script commits via its own connection so db_session's rollback won't
    # clean up).
    unique = f"e2e_widget_{int(time.time() * 1000)}"

    # ── Round 1: 2 evidences for one term ──
    _write_jsonl(quarantine_dir / "run_001.jsonl", [
        {"term": unique, "asset_type": "Equipment",
         "evidence": ["block:WIDGET_A"], "ts": 1700000000.0},
        {"term": unique, "asset_type": "Equipment",
         "evidence": ["block:WIDGET_B"], "ts": 1700000100.0},
    ])

    aggregated = ptt.aggregate(quarantine_dir)
    ins, upd = ptt.upsert_quarantine_db(aggregated, _raw_dsn(_db_dsn))
    assert ins >= 1 and upd == 0

    # Verify row landed (use a fresh transaction since the script committed
    # outside db_session's connection).
    db_session.commit()
    row = db_session.execute(
        text(
            "SELECT count, decision, jsonb_array_length(evidence) AS ev_len "
            "FROM quarantine_terms WHERE term_normalized = :n"
        ),
        {"n": unique},
    ).one()
    assert row.count == 2
    assert row.decision is None
    assert row.ev_len == 2

    # ── Round 2: 1 new evidence, total 3 ──
    _write_jsonl(quarantine_dir / "run_002.jsonl", [
        {"term": unique, "asset_type": "Equipment",
         "evidence": ["block:WIDGET_C"], "ts": 1700000200.0},
    ])
    aggregated = ptt.aggregate(quarantine_dir)
    ins2, upd2 = ptt.upsert_quarantine_db(aggregated, _raw_dsn(_db_dsn))
    assert upd2 >= 1

    db_session.commit()
    row2 = db_session.execute(
        text("SELECT count, jsonb_array_length(evidence) AS ev_len "
             "FROM quarantine_terms WHERE term_normalized = :n"),
        {"n": unique},
    ).one()
    assert row2.count == 3
    assert row2.ev_len == 3

    # ── Cleanup: remove the test row so re-runs stay deterministic ──
    db_session.execute(
        text("DELETE FROM quarantine_terms WHERE term_normalized = :n"),
        {"n": unique},
    )
    db_session.commit()


def test_promote_dual_write_preserves_human_decision(tmp_path, db_session, _db_dsn):
    """After reviewer marks 'approve', subsequent runs MUST NOT overwrite it."""
    quarantine_dir = tmp_path / "quarantine"
    unique = f"e2e_decided_{int(time.time() * 1000)}"

    # Round 1 -- pending insert
    _write_jsonl(quarantine_dir / "r1.jsonl", [
        {"term": unique, "asset_type": "Equipment",
         "evidence": ["block:X"], "ts": 1700000000.0},
    ])
    aggregated = ptt.aggregate(quarantine_dir)
    ptt.upsert_quarantine_db(aggregated, _raw_dsn(_db_dsn))

    # Reviewer commits a decision out-of-band. We MUST NOT use db_session for
    # this -- the conftest fixture wraps it in an outer transaction, so any
    # row lock acquired here would block the script's INSERT...ON CONFLICT
    # below. Use a separate raw connection that fully commits and closes.
    _conn = psycopg2.connect(_raw_dsn(_db_dsn), connect_timeout=10)
    try:
        with _conn.cursor() as _cur:
            _cur.execute(
                "UPDATE quarantine_terms "
                "SET decision='approve', count=999, reviewer='alice', reviewed_at=NOW() "
                "WHERE term_normalized = %s",
                (unique,),
            )
        _conn.commit()
    finally:
        _conn.close()

    # Round 2 -- script tries to update with new evidence
    _write_jsonl(quarantine_dir / "r2.jsonl", [
        {"term": unique, "asset_type": "Equipment",
         "evidence": ["block:Y", "block:Z"], "ts": 1700000300.0},
    ])
    aggregated = ptt.aggregate(quarantine_dir)
    ins, upd = ptt.upsert_quarantine_db(aggregated, _raw_dsn(_db_dsn))
    # The script's RETURNING clause yields nothing for the WHERE-blocked row,
    # so neither inserted nor updated counters tick.
    assert ins == 0 and upd == 0

    db_session.commit()
    row = db_session.execute(
        text("SELECT count, decision, reviewer FROM quarantine_terms "
             "WHERE term_normalized = :n"),
        {"n": unique},
    ).one()
    # Decision + reviewer + count stay exactly as the human left them.
    assert row.decision == "approve"
    assert row.reviewer == "alice"
    assert row.count == 999

    db_session.execute(
        text("DELETE FROM quarantine_terms WHERE term_normalized = :n"),
        {"n": unique},
    )
    db_session.commit()
