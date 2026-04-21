# GitHub Copilot Instructions — ProLine CAD

> Slim mirror of [CLAUDE.md](../CLAUDE.md). For domain depth, conventions, and
> rationale, read CLAUDE.md. This file is the fast lane for Copilot suggestions.

## Project at a glance

AI-driven aerospace production line planning. Five MCP-based agents: Parse →
Constraint → Layout → Simulation → Report, driven by an Orchestrator. Python 3.11+
backend (FastAPI, Pydantic v2, SQLAlchemy 2.0, Alembic), Next.js 14 frontend,
PostgreSQL 16 + PostGIS + TimescaleDB + Redis + MinIO + NATS for data.

## Hard rules (do not deviate)

1. **MCP-only between agents**. Never `from agents.<other> import ...`. Use the
   Orchestrator and pass `mcp_context_id` on every call.
2. **No emoji** anywhere — UI, logs, commits, comments, code.
3. **Pydantic v2 only** (`model_config = ConfigDict(...)`); no `class Config:`.
4. **Named exports only** in TS; no `from x import *` in Python.
5. **No `Any`, no bare `except:`, no `print()`** in services. Use specific types,
   typed exceptions, `log = logging.getLogger(__name__)`.
6. **Secrets via env** (`OPENAI_API_KEY`, `POSTGRES_DSN`, `JWT_SIGNING_KEY`,
   `MCP_BEARER_TOKEN`, `MINIO_*`). Never literals; never in commits or logs.
7. **Alembic-managed migrations**. Never edit a committed revision; always
   `alembic revision -m "..."`.
8. **Pyproject managed deps**. Never append to `requirements.txt` by hand.

## Code shape

- Imports in three blocks (stdlib → third-party → local), with
  `from __future__ import annotations` first.
- Public API: docstring + full type hints. Domain errors inherit from a base
  exception (`ParseError`, `H4BudgetExceeded`).
- TS interfaces use `IXxx` prefix. Python interfaces use `typing.Protocol`.
- Files: `snake_case.py`, `kebab-case.tsx`. Identifiers: English. Comments,
  docstrings, PRD, UI copy: Chinese (zh-CN).
- Tests in `<module>/tests/test_<topic>.py`; one assert family per test;
  table-driven with `pytest.mark.parametrize`.

## Test pyramid (per agent minimums)

- **L0 schema/contract** ≥ 30 — agent.json, Pydantic round-trip, API envelope.
- **L1 gold regression** ≥ 10 — frozen input → expected output (`scripts/gold_eval.py`).
- **L2 silver** — synthetic edge cases, marked `slow`.
- **L3 LLM-judge** — nightly only.

CI gates run in order: `schema-check → unit → integration → gold-regression`.
A failed stage blocks the PR.

## Common commands (PowerShell)

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[parse,constraint,layout,dev]"

pytest agents/parse_agent/tests/ -q
ruff check . ; ruff format . ; mypy agents/ shared/
python scripts/gold_eval.py
python scripts/check_schema_drift.py
python scripts/check_agent_isolation.py
alembic upgrade head
.\scripts\dev_up.ps1
```

## When generating code

- **Suggest typed signatures** even for short helpers; never `def f(x):`.
- **Reach for the existing model**: `shared/models.py` is the source of truth.
  Extend enums there before introducing parallel types in an agent.
- **Pass `mcp_context_id` through**. Any new function that produces a domain
  object must accept and propagate it.
- **Reuse `tools/registry.py` patterns** (ParseAgent) when adding agent-local
  callable tools — register in `agent.json`, do not introduce a new framework.
- **Migrations**: when changing a Pydantic model that maps to DDL, also draft an
  Alembic revision in the same PR; CI runs `check_schema_drift.py`.

## What not to suggest

- `from agents.X import ...` from another agent's namespace.
- Direct DB access into a different agent's tables.
- `requests` in async paths — use `httpx.AsyncClient`.
- `pkg_resources`, `imp`, `distutils` — use `importlib.*`.
- Storing or printing API keys, JWTs, DSNs.
- Emoji in any output, including completion comments and log strings.
- New top-level directories without an ADR (`docs/adr/`).

## UI/UX guidance

- Three states for every list/table/chart: empty, loading skeleton, error
  with retry plus copyable `mcp_context_id`.
- Light, airy palette; cool whites and soft grays; accents `#2563eb` blue and
  `#14b8a6` teal. No dark, saturated, or aggressive backgrounds.
- Keyboard-reachable, ARIA-labeled, color-blind safe. axe-core runs in CI;
  Lighthouse Accessibility ≥ 95 is the gate.
