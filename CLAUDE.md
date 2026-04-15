# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ProLine CAD is an AI-driven production line lifecycle planning platform for aerospace manufacturing. It covers five stages: floor plan parsing → process constraints → auto layout → simulation optimization → feasibility reports. All inter-module communication uses MCP (Model Context Protocol) as the sole context exchange channel.

The project is currently in the PoC/Spike phase — 10 independent spike experiments validating core technology feasibility before MVP.

## Repository Structure

- `PRD/` — Product requirements (PRD-1 through PRD-5), technical architecture doc, data model appendix, spike verification plan, and aerospace test data spec. All in Chinese.
- `spikes/` — 10 independent spike experiments, each in `spike_NN_<name>/` with `src/`, `tests/`, and `test_data/` subdirectories. Most source modules are stubs (`raise NotImplementedError`); tests are written TDD-style (red phase).
- `spikes/conftest.py` — Shared pytest fixtures and `Thresholds` class containing Go/No-Go acceptance thresholds from the spike plan.
- `.venv/` — Python virtual environment (Python 3.x).

## Spikes

| ID | Directory | Domain |
|----|-----------|--------|
| 1 | `spike_01_dwg_parse` | DWG/DXF floor plan parsing (ezdxf, ODA converter) |
| 2 | `spike_02_mcp_e2e` | MCP protocol end-to-end communication |
| 3 | `spike_03_collision` | Spatial collision detection & auto-healing (R-Tree) |
| 4 | `spike_04_des_sim` | Discrete event simulation (SimPy) |
| 5 | `spike_05_llm_extract` | LLM process constraint extraction |
| 6 | `spike_06_temporal` | Temporal workflow orchestration |
| 7 | `spike_07_3d_render` | 3D rendering & real-time interaction (Three.js) |
| 8 | `spike_08_pinn` | Physics-Informed Neural Network surrogate model |
| 9 | `spike_09_rag` | RAG knowledge retrieval (vector store) |
| 10 | `spike_10_report` | PDF/Word/Excel report generation |

## Commands

```bash
# Activate venv
source .venv/Scripts/activate   # Windows Git Bash
.venv\Scripts\activate          # Windows CMD

# Run all spike tests (from repo root)
cd spikes && python -m pytest

# Run a single spike's tests
cd spikes && python -m pytest spike_01_dwg_parse/tests/

# Run tests by marker (priority or spike)
cd spikes && python -m pytest -m p0          # P0 critical tests only
cd spikes && python -m pytest -m spike3      # Spike-3 only
cd spikes && python -m pytest -m "not slow"  # Skip slow tests

# Run a single test
cd spikes && python -m pytest spike_01_dwg_parse/tests/test_dwg_parser.py::TestDWGParse::test_name
```

Pytest config is in `spikes/pytest.ini`. Default addopts: `-v --tb=short --strict-markers`.

## Test Markers

Defined in `spikes/pytest.ini`: `p0`, `p1`, `p2` (priority), `spike1`–`spike10`, `slow`, `integration`, `gpu`.

## Architecture (Target System)

The full system (post-spike) follows this layered architecture:

- **Presentation**: React + Three.js + Monaco Editor, Zustand state management
- **Gateway/BFF**: FastAPI + WebSocket
- **Orchestration**: Temporal Server + Workers
- **Agent Services (MCP Servers)**: 5 independent agents (Parse, Constraint, Layout, Simulation, Report) — each is an MCP Server
- **Capabilities**: FreeCAD/OCC (CAD kernel), GPT-4o/vLLM (LLM), Milvus (vector search), SimPy (simulation), R-Tree (spatial)
- **Data**: PostgreSQL + PostGIS, Redis, NATS JetStream, MinIO, TimescaleDB

Core design principles: MCP-First (no direct DB coupling between agents), context traceability via `mcp_context_id`, independent agent deployment, orchestration decoupled from agents.

## Key Domain Concepts

- **SiteModel**: Single source of truth for parsed floor plans — contains Assets, Obstacles, ExclusionZones
- **Asset**: Parameterized equipment with Footprint, Ports, and `asset_guid`
- **ConstraintSet / ProcessGraph**: Process constraints extracted from SOP documents
- **LayoutCandidate / Placement**: Auto-generated layout proposals with scoring
- **SimRunResult**: DES simulation output (JPH, OEE, bottleneck analysis)
- **FeasibilityReport**: Final deliverable with ROI tables and MCP trace links

## Acceptance Thresholds

All Go/No-Go thresholds are codified in `spikes/conftest.py::Thresholds`. Reference these when implementing spike source code — tests assert against them.

## UI/UX Conventions

- No emoji icons anywhere in the UI — use text labels, semantic icons (SVG/icon font), or subtle visual indicators instead.
- Visual style: clean, airy, lightweight. Generous whitespace, restrained use of borders and shadows. The interface should feel precise and intelligent without being heavy or oppressive.
- Color palette: light and uplifting base tones (cool whites, soft grays), accented with calm blues and teals to convey intelligence and rigor. Avoid dark/saturated backgrounds or high-contrast aggressive palettes. Think clinical clarity, not dashboard darkness.

## Engineering Philosophy: Palantir Ontology-Driven Computation

This project follows the Palantir Ontology engineering philosophy — all domain entities (SiteModel, Asset, Constraint, LayoutCandidate, SimRunResult, etc.) are first-class ontology objects with typed properties, bidirectional links, and action semantics. Key principles:

- **Object-centric, not table-centric**: Design around domain objects and their relationships, not database schemas. The ERD in `PRD/PRD全局附录_数据模型与接口规范.md` defines the ontology graph.
- **Actions over CRUD**: Mutations are expressed as domain actions (e.g., "heal collision", "run simulation", "extract constraints") that carry intent, validation, and audit trails — not raw create/update/delete.
- **Linked context propagation**: Every object carries `mcp_context_id` for full traceability. When an action produces a new object, it links back to its inputs through the ontology graph, enabling root-cause analysis across the entire pipeline.
- **Computation on the ontology**: Analytics, scoring, and optimization operate on the ontology graph directly. Functions take ontology objects as inputs and produce ontology objects as outputs — keeping computation composable and auditable.

## Language

PRD documents, code comments, and test descriptions are in Chinese. Code identifiers and API names are in English.
