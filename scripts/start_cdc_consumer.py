"""CDC consumer placeholder -- creates / verifies a logical replication slot.

B5 deliverable: prove the wal_level=logical configuration is alive end-to-end
without committing a real consumer. A future revision will replace `_consume`
with debezium / pgoutput stream handling.

Usage:
    POSTGRES_DSN=postgresql+psycopg2://... python scripts/start_cdc_consumer.py
    POSTGRES_DSN=... python scripts/start_cdc_consumer.py --slot my_slot --create

Exit codes:
  0  slot exists / created OK
  1  configuration problem (DSN missing, wal_level wrong)
  2  database error
"""

from __future__ import annotations

import argparse
import os
import sys


_DEFAULT_SLOT = "proline_cdc_default"


def _check_wal_level(conn) -> str:
    cur = conn.cursor()
    cur.execute("SHOW wal_level")
    return cur.fetchone()[0]


def _slot_exists(conn, slot_name: str) -> bool:
    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM pg_replication_slots WHERE slot_name = %s", (slot_name,)
    )
    return cur.fetchone() is not None


def _create_slot(conn, slot_name: str) -> None:
    cur = conn.cursor()
    cur.execute(
        "SELECT pg_create_logical_replication_slot(%s, %s)", (slot_name, "pgoutput")
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slot", default=_DEFAULT_SLOT, help="logical slot name")
    parser.add_argument(
        "--create", action="store_true", help="create the slot if missing"
    )
    args = parser.parse_args()

    dsn = os.environ.get("POSTGRES_DSN", "").strip()
    if not dsn:
        print("POSTGRES_DSN not set", file=sys.stderr)
        return 1

    # Strip the SQLAlchemy driver prefix for psycopg2 native use.
    if dsn.startswith("postgresql+psycopg2://"):
        dsn = "postgresql://" + dsn[len("postgresql+psycopg2://") :]

    try:
        import psycopg2
    except ImportError:
        print("psycopg2 not installed -- pip install psycopg2-binary", file=sys.stderr)
        return 1

    try:
        with psycopg2.connect(dsn) as conn:
            conn.autocommit = True
            wal = _check_wal_level(conn)
            if wal != "logical":
                print(f"wal_level is {wal!r}, need 'logical'", file=sys.stderr)
                return 1
            print(f"wal_level=logical OK, target slot={args.slot!r}")
            if _slot_exists(conn, args.slot):
                print("slot already exists -- nothing to do")
                return 0
            if not args.create:
                print("slot missing; rerun with --create", file=sys.stderr)
                return 1
            _create_slot(conn, args.slot)
            print("slot created (no-op consumer; future revision will stream)")
            return 0
    except Exception as exc:  # pragma: no cover - defensive
        print(f"db error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
