"""Top-level pytest fixtures -- DB session for tests marked `db_fixture`.

Tests that need a live PostGIS+Timescale database opt in via:

    @pytest.mark.db_fixture
    def test_something(db_session): ...

The fixture assumes:
- POSTGRES_DSN env var points at a running cluster (see db/docker-compose.db.yml).
- `alembic upgrade head` has already run against that DSN.
- db/fixtures/seed.sql has been loaded (or will be on first use).

If POSTGRES_DSN is unset, db_fixture-marked tests are skipped, not failed,
so unit-only contributors are not blocked.

Windows note: prefer `127.0.0.1` over `localhost` in the DSN. With Docker port
forwarding on 5434, `localhost` resolves to ::1 first and the IPv6 attempt
stalls 5-10 s before falling back to IPv4 — a single test run becomes minutes.
Example (lite stack): `postgresql+psycopg2://proline:proline_dev@127.0.0.1:5434/proline_cad`.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parent
_SEED_SQL = _REPO_ROOT / "db" / "fixtures" / "seed.sql"


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "db_fixture: requires a live PostGIS+Timescale database "
        "(POSTGRES_DSN env var). Skipped otherwise.",
    )


@pytest.fixture(scope="session")
def _db_dsn() -> str:
    dsn = os.environ.get("POSTGRES_DSN", "").strip()
    if not dsn:
        pytest.skip("POSTGRES_DSN not set -- db_fixture tests skipped")
    return dsn


@pytest.fixture(scope="session")
def _db_engine(_db_dsn):
    sa = pytest.importorskip("sqlalchemy")
    engine = sa.create_engine(_db_dsn, future=True)
    # Apply seed once per session. psycopg2 happily executes a multi-statement
    # script in a single `execute()` call as long as no bind parameters are used,
    # so we hand the whole file to the driver instead of brittle ";"-splitting
    # (which mishandled inline `-- section header` comments).
    if _SEED_SQL.exists():
        seed_sql = _SEED_SQL.read_text(encoding="utf-8").strip()
        if seed_sql:
            with engine.begin() as conn:
                conn.exec_driver_sql(seed_sql)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(_db_engine):
    """Per-test transactional session -- always rolled back."""
    sa_orm = pytest.importorskip("sqlalchemy.orm")
    connection = _db_engine.connect()
    trans = connection.begin()
    session = sa_orm.Session(bind=connection)
    try:
        yield session
    finally:
        session.close()
        trans.rollback()
        connection.close()
