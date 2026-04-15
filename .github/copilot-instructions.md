# ProLine CAD — Workspace Instructions

> AI-driven aerospace production line planning platform. PoC/Spike phase with 10 independent experiments.
> For full project overview, architecture, and domain concepts see [CLAUDE.md](../CLAUDE.md).

## Build & Test

```bash
# All tests (from repo root)
cd spikes && python -m pytest

# Single spike
cd spikes && python -m pytest spike_03_collision/tests/

# By priority or spike marker
cd spikes && python -m pytest -m p0
cd spikes && python -m pytest -m spike3
cd spikes && python -m pytest -m "not slow"
```

- Python 3.11, venv at `.venv/` — activate with `.venv\Scripts\activate` (Windows CMD)
- Pytest config: `spikes/pytest.ini` — addopts: `-v --tb=short --strict-markers`
- Markers: `p0`/`p1`/`p2` (priority), `spike1`–`spike10`, `slow`, `integration`, `gpu`

## Code Conventions

### Language
- **Identifiers & API names**: English
- **Docstrings, comments, PRD docs, test descriptions**: Chinese
- Section separators in source: `# ════════════════ 标题 ════════════════`

### Spike Module Pattern
Each spike lives in `spikes/spike_NN_<name>/` with `src/`, `tests/`, `test_data/`.

Source modules follow this pattern:
```python
from dataclasses import dataclass, field
from pathlib import Path

@dataclass
class ResultType:
    """Chinese docstring describing the return type."""
    field_name: type = default

class ServiceClass:
    """Chinese docstring with spec reference (e.g. §2.4)."""
    def method(self, ...) -> ResultType:
        raise NotImplementedError   # TDD RED phase — stub only
```

### Test Pattern
```python
import pytest
from conftest import Thresholds

@pytest.mark.p0
@pytest.mark.spike1
class TestFeatureName:
    """S1-TC01: Chinese description of test scenario — Go/No-Go criteria."""
    def test_specific_case(self, fixture_arg):
        result = service.method(...)
        assert result.metric <= Thresholds.S1_THRESHOLD_NAME
```

- All Go/No-Go thresholds live in `spikes/conftest.py::Thresholds` — always assert against these, never hardcode values
- Test case IDs (e.g. `S1-TC01`) map to the verification plan in `PRD/关键技术验证计划.md`
- Use `@pytest.mark.parametrize` for matrix testing across tiers/sizes

## Architecture Decisions

- **MCP-First**: All inter-module communication uses Model Context Protocol. No direct DB coupling between agents.
- **Context traceability**: Every operation carries `mcp_context_id`
- **5 Agent Services**: Parse → Constraint → Layout → Simulation → Report (each is an MCP Server)
- **Ontology model**: `AeroOntology-v1.0` with Objects, Links, Provenance, Trust, Actions
- **Trust Gate pattern**: CP-A through CP-E checkpoints gate data flow between stages
- See `PRD/PRD全局附录_数据模型与接口规范.md` for data model and API specs

## Key Domain Terms

| Term | Meaning |
|------|---------|
| SiteModel | Single source of truth for parsed floor plans (site_guid: SM-xxx) |
| Asset | Equipment with MDI (Master Device ID), Footprint, Ports |
| CP-A Token | Trust gate token — SiteModel must pass all preconditions before layout stage |
| TRAVERSE_PROHIBITED | Auto-generated constraint for ground pits — highest priority, non-overridable |

## Pitfalls

- **Working directory**: Always `cd spikes` before running pytest — tests use relative paths from `spikes/`
- **Stub-only sources**: All `src/` modules raise `NotImplementedError`. Implement the stub body when making a spike pass, don't restructure the class.
- **Thresholds are law**: Never weaken a threshold to make a test pass. If a spike can't meet a threshold, that's a No-Go finding.
- **Test data tiers**: Spike-1 has tiered DXF files (tier1/tier2/tier3) with increasing complexity. `real_world/` contains production-scale files — handle memory carefully.
- **No dependency manifest**: There's no requirements.txt yet. When adding dependencies for a spike, document them in the spike's README or a local requirements file.
- **HTML prototypes**: Located in `PRD/` as standalone files (Tailwind CDN, no build step). Open directly in browser.

## PRD Documents

All in `PRD/`, all in Chinese:
- `PRD-1` through `PRD-5` (v3.0) — one per pipeline stage
- `PRD全局附录_数据模型与接口规范.md` — data model & API reference
- `关键技术验证计划.md` — spike acceptance criteria (maps to `Thresholds`)
- `航空制造领域测试数据方案.md` — test data specification
- `技术方案文档.md` — technical architecture
- `step4...原型设计执行计划 v3.0.md` — prototype design execution plan
