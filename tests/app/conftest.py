"""Pytest fixtures shared by all app/* test modules.

Provides:
  - `client`: TestClient with a fresh app instance + DB-engine bypass when
    POSTGRES_DSN is unset (DB-touching tests opt in via `db_fixture`).
  - `auth_headers(role)`: helper to build `X-Role` + `X-Actor` headers.
"""

from __future__ import annotations

import os
from typing import Iterator
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app_factory(monkeypatch):
    """Return a fresh FastAPI app each call so middleware state is isolated."""
    # Force JSON renderer so log assertions are deterministic.
    monkeypatch.setenv("DEV", "0")
    monkeypatch.setenv("OTEL_TRACES_EXPORTER", "none")
    # Keep the DB-gauge refresh loop out of unit tests -- otherwise every
    # client fixture would spawn a 30-s polling task.
    monkeypatch.setenv("DASHBOARD_DISABLE_GAUGE_LOOP", "1")
    # Skip per-request `SET LOCAL ROLE` -- the test DB (db-lite container)
    # does not provision the app_* roles that 0008 creates. Integration
    # environments that have run the full migration chain can clear this.
    monkeypatch.setenv("DASHBOARD_DISABLE_RLS_ROLE_SWITCH", "1")

    def _make():
        # Import inside the factory so env vars are applied first.
        from app.deps import dispose_engine, get_db
        from app.main import create_app

        dispose_engine()  # reset between tests
        app = create_app()

        # When POSTGRES_DSN is unset (non-DB tests), override get_db with a
        # MagicMock session so route validation/RBAC paths still work without
        # a live database. db_fixture-marked tests can clear the override.
        if not os.environ.get("POSTGRES_DSN"):
            def _fake_db():
                yield MagicMock()
            app.dependency_overrides[get_db] = _fake_db

        return app

    return _make


@pytest.fixture
def client(app_factory) -> Iterator[TestClient]:
    app = app_factory()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_headers():
    def _hdrs(role: str = "viewer", actor: str = "tester@example.com"):
        return {"X-Role": role, "X-Actor": actor}

    return _hdrs
