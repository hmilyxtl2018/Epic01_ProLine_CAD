# CLAUDE.md

Single source of truth for repo conventions. Read fully before any non-trivial
change. Deep details live in linked satellite docs; this file stays scannable.

> **Status**: ParseAgent v1.0 GA in progress. `spikes/` is reference-only;
> new work happens in `agents/` and `shared/`.

---

## 1. Project Overview

ProLine CAD — AI-driven aerospace production-line planning. Pipeline:
floor-plan parse → process constraints → auto layout → simulation → feasibility
report. **MCP** is the only inter-agent channel.

- **Stack**: Python 3.11+, TypeScript 5+; FastAPI + Pydantic v2 + SQLAlchemy 2.0
  + Alembic; Next.js 14 + React 18 + Three.js + Tailwind; PostgreSQL 16 +
  PostGIS + TimescaleDB + Redis + MinIO + NATS; Temporal (post-spike).
- **Architecture**: 5 agents (Parse / Constraint / Layout / Simulation / Report),
  each a standalone MCP server, dispatched by an Orchestrator. No agent-to-agent
  HTTP. Diagram: [docs/architecture.md](docs/architecture.md).
- **Key dirs**: `agents/<name>/` (services) | `shared/` (Pydantic + MCP) |
  `db/migrations/` (Alembic) | `scripts/` (eval, drift, dev_up) | `ExcPlan/` +
  `PRD/` (Chinese design) | `docs/adr/` | `tests/data/` (fixtures) | `spikes/`
  (frozen PoCs).

---

## 2. Build and Test Commands

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[parse,constraint,layout,dev]"

pytest agents/parse_agent/tests/test_h5_validator.py::test_r3_keyword_chinese_substring -q
pytest agents/parse_agent/tests/ -q

ruff check . ; ruff format . ; mypy agents/ shared/
python scripts/gold_eval.py                 # L1 gold regression
python scripts/check_schema_drift.py        # Pydantic <-> DDL drift
python scripts/check_agent_isolation.py     # No cross-agent imports

alembic upgrade head
alembic downgrade -1 ; alembic upgrade head # round-trip smoke
.\scripts\dev_up.ps1                        # PG + MinIO + agents + dashboard
```

Pytest config in `pyproject.toml`. Markers: `p0|p1|p2`, `slow`, `integration`,
`gpu`. CI order — any red blocks the PR:
`schema-check -> unit -> integration -> gold-regression`.

---

## 3. Code Conventions

- **Named exports only**. No TS default exports; no `from x import *`.
- **Interfaces**: Python `typing.Protocol`; TS `IXxx` prefix.
- **Typed errors**. Domain exceptions only (`H4BudgetExceeded`); never bare `except:`.
- **Imports**: 3 blocks (stdlib / third-party / local), `from __future__ import
  annotations` first.
- **Public API**: full type hints + docstring. Private `_helpers` may skip.
- **Logging**: `log = logging.getLogger(__name__)`. No `print()` in services.
- **Naming**: `snake_case` Py, `camelCase` TS vars, `PascalCase` types,
  `SCREAMING_SNAKE_CASE` constants. Files: `snake_case.py`, `kebab-case.tsx`.
- **Tests**: `<module>/tests/test_<topic>.py`; one assert family per test;
  `pytest.mark.parametrize` for tables.
- **Pydantic v2 only**: `model_config = ConfigDict(...)`, never `class Config:`.

---

## 4. Things to Avoid

Enforced by lint, CI, or review. Format: `BAD -> GOOD`.

```python
# Any                  : def parse(p: Any) -> Any            -> def parse(p: ParseRequest) -> SiteModel
# Bare except          : try: f() except: log.error("x")    -> except FooParseError as exc: log.error(...); raise
# print in services    : print(f"loaded {n}")                -> log.info("loaded", extra={"count": n, "mcp_context_id": ctx.id})
# Cross-agent import   : from agents.layout_agent.service ... -> client.invoke("layout.solve", payload, parent_context_id=ctx.id)
# Edit committed migr  : vim db/migrations/versions/0003_*.py -> alembic revision -m "add embedding to asset_geometries"
# requirements.txt     : echo "requests==2.31.0" >> requirements.txt -> edit pyproject.toml, then pip install -e .
# Secrets in repo      : OPENAI_API_KEY = "sk-..."            -> api_key = os.environ["OPENAI_API_KEY"]   # via .env.local
# Deprecated stdlib    : import pkg_resources, imp            -> import importlib.resources, importlib.util
# Emoji anywhere       : log.info("\u2705 done")              -> log.info("done")
```

---

## 5. Agent Collaboration Rules

MCP-only is non-negotiable; violations break traceability and audit.

- No `from agents.<other> import` — enforced by `scripts/check_agent_isolation.py`.
- Every public op accepts and emits `mcp_context_id`; produced objects link
  back to their parent context.
- Sub-task dispatch goes through the Orchestrator (Temporal), never agent-to-agent HTTP.
- An agent's `tools/registry.py` callables are local functions registered in
  `agent.json`, **not** sub-agents.
- Cross-agent data is requested via MCP and returned as a snapshot; never
  query another agent's tables directly.

---

## 6. Memory and Skills Protocol

Consult repo and session memory **before** non-trivial work.

- Start with `memory view /memories/repo/` and `memory view /memories/session/`.
- If a SKILL applies, **read its `SKILL.md` first** — do not just reference it.
- Use `runSubagent Explore (quick|medium|thorough)` for multi-step searches
  instead of chaining many small reads.
- Memory entries are single-line bullets, ≤120 chars. Update or delete stale
  notes in the same change. New files only when existing ones are off-topic.

---

## 7. Testing Pyramid

ParseAgent §7.5 defines the canonical ratios; new agents follow the same shape.

| Tier | Purpose | Per-agent floor | Tooling |
|---|---|---|---|
| **L0** Schema/Contract | agent.json, Pydantic round-trip, API envelope | ≥ 30 | pytest, jsonschema |
| **L1** Gold Regression | Frozen input → expected output | ≥ 10 | `scripts/gold_eval.py` |
| **L2** Silver | Synthetic edge cases | ad-hoc, `slow` mark | pytest |
| **L3** LLM-Judge | Rubric-scored quality on real DWG | nightly only | `scripts/quality_matrix_llm.py` |

Every PR introducing a new module shows **L0 + L1 coverage in the description**.

---

## 8. Commits, PRs, Secrets

- **Commits**: Conventional Commits, English, imperative mood. Examples:
  `feat(parse): add H5 evidence validator`, `fix(layout): clamp negative footprint`.
- **PR template** (`.github/pull_request_template.md`) is mandatory; three required bars:
  - **Risk** — blast radius (single-agent / cross-agent / DB / public API / security).
  - **Rollback** — exact step (revision id, env flag, wheel tag).
  - **Test plan** — commands run + new tests + gold delta.
- **Secrets**: never in code, commits, logs, comments. Use `.env.local`. Required
  env keys: `OPENAI_API_KEY`, `POSTGRES_DSN`, `MINIO_ACCESS_KEY`,
  `MINIO_SECRET_KEY`, `JWT_SIGNING_KEY`, `MCP_BEARER_TOKEN`.
- **Killswitch**: `DASHBOARD_KILLSWITCH=true` → 503 from all `/dashboard/*`.
  Incident use only; never a release gate.

---

## 9. Domain Concepts

- **SiteModel** — parsed floor plan: `assets`, `links`,
  `geometry_integrity_score`, `mcp_context_id`.
- **Asset** — `asset_guid`, `type` (AssetType enum), `coords`, `footprint`,
  `confidence`, `classifier_kind`.
- **AssetType** — closed enum: `Equipment | Conveyor | LiftingPoint | Zone |
  Annotation | Wall | Door | Pipe | Column | Window | CncMachine |
  ElectricalPanel | StorageRack | Other | Unknown`.
- **ConstraintSet / ProcessGraph** — process constraints from SOPs.
- **LayoutCandidate / Placement** — layout proposals + score breakdown.
- **SimRunResult** — DES output (JPH, OEE, bottleneck stations).
- **FeasibilityReport** — final deliverable with ROI and MCP trace links.
- **mcp_context_id** — spine of observability and audit; every produced
  object links back to its upstream context.

Go/No-Go thresholds live in `spikes/conftest.py::Thresholds` and each agent's
`agent.json::evaluation.baseline`.

---

## 10. Engineering Philosophy: Palantir Ontology-Driven Computation

- **Object-centric, not table-centric**. Design around domain objects + links.
  ER lives in `docs/data_architecture.md`.
- **Actions over CRUD**. Mutations are domain actions ("heal collision",
  "approve term") carrying intent, validation, audit — not raw row updates.
- **Linked context**. Every object carries `mcp_context_id`; produced objects
  link back to inputs through the ontology graph.
- **Computation on the ontology**. Analytics and optimisation are ontology-in /
  ontology-out — composable and auditable.

When Pydantic models and DDL diverge, Pydantic wins; the migration catches up.

---

## 11. UI/UX Conventions

- **No emoji** anywhere (UI, icons, logs, commits, comments). Use text labels or
  heroicons-outline SVG.
- **Visual**: clean, airy, lightweight; cool-white + soft-gray base; accents
  `#2563eb` blue, `#14b8a6` teal. No dark or saturated aggressive backgrounds.
- **Three states** for every list / chart / table: empty, loading skeleton,
  error (with retry + copyable `mcp_context_id`).
- **A11y**: keyboard-reachable, ARIA-labeled, color-blind safe. axe-core in CI;
  Lighthouse Accessibility ≥ 95 is the gate.
- **i18n**: zh-CN default (PRD, comments, test descriptions, UI copy). English
  keys as placeholders. Identifiers, API names, type names, commit messages
  stay English.
