"""Alembic environment — wires SQLAlchemy metadata + DSN resolution.

Reads POSTGRES_DSN from env (CLAUDE.md §8: secrets via env only). Falls back to
a local dev DSN useful for `alembic check` smoke runs.
"""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Make `shared.*` importable when alembic is invoked from repo root.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from shared.db_schemas import metadata as target_metadata  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

_DEFAULT_LOCAL_DSN = "postgresql+psycopg2://proline:proline@localhost:5432/proline_cad"
_dsn = os.environ.get("POSTGRES_DSN", _DEFAULT_LOCAL_DSN)
config.set_main_option("sqlalchemy.url", _dsn)


def _include_object(obj, name, type_, reflected, compare_to):  # type: ignore[no-untyped-def]
    """Skip extension-owned objects (postgis, timescaledb, vector tables)."""
    if type_ == "table" and name in {"spatial_ref_sys"}:
        return False
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=_dsn,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=_include_object,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=_include_object,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
