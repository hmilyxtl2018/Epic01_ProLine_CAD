"""Schema drift gate -- Pydantic enums vs SQLAlchemy CHECK / source-tuple mirror.

Today this enforces a single contract: `shared.models.AssetType` must equal
`shared.db_schemas.ASSET_TYPES`. Future enums register via the `_DRIFT_PAIRS`
table below.

Exit codes:
  0  no drift
  1  drift detected (CI-blocking)
  2  internal error / import failure

Usage:
  python scripts/check_schema_drift.py
  python scripts/check_schema_drift.py --json   # for CI annotations
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

# Make the repo root importable when invoked as a plain script (CI does this).
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


@dataclass(frozen=True)
class _DriftPair:
    """One Pydantic enum mirrored by one DB-side tuple of allowed values."""
    name: str
    pydantic_path: str   # "module:Symbol"
    db_path: str         # "module:Symbol"


_DRIFT_PAIRS: tuple[_DriftPair, ...] = (
    _DriftPair(
        name="AssetType",
        pydantic_path="shared.models:AssetType",
        db_path="shared.db_schemas:ASSET_TYPES",
    ),
    # Future:
    #   _DriftPair("WorkflowState", "shared.models:WorkflowState",
    #              "shared.db_schemas:WORKFLOW_STATES"),
)


def _import_symbol(path: str):
    module_name, _, symbol = path.partition(":")
    if not symbol:
        raise ValueError(f"path missing :Symbol -- got {path!r}")
    import importlib
    module = importlib.import_module(module_name)
    return getattr(module, symbol)


def _values_of(obj) -> set[str]:
    """Coerce either an Enum class or a tuple/list/set of strings to a set."""
    try:
        # Enum-like
        return {str(v.value) for v in obj}
    except AttributeError:
        return set(obj)


def check() -> list[dict]:
    findings: list[dict] = []
    for pair in _DRIFT_PAIRS:
        try:
            py_obj = _import_symbol(pair.pydantic_path)
            db_obj = _import_symbol(pair.db_path)
        except Exception as exc:
            findings.append(
                {"name": pair.name, "kind": "import_error", "detail": str(exc)}
            )
            continue
        py = _values_of(py_obj)
        db = _values_of(db_obj)
        if py == db:
            findings.append({"name": pair.name, "kind": "ok"})
            continue
        findings.append(
            {
                "name": pair.name,
                "kind": "drift",
                "only_in_pydantic": sorted(py - db),
                "only_in_db": sorted(db - py),
            }
        )
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args()

    try:
        findings = check()
    except Exception as exc:  # pragma: no cover -- defensive
        print(f"check_schema_drift: internal error -- {exc}", file=sys.stderr)
        return 2

    drift = [f for f in findings if f["kind"] != "ok"]

    if args.json:
        print(json.dumps({"findings": findings, "drift_count": len(drift)}, indent=2))
    else:
        for f in findings:
            if f["kind"] == "ok":
                print(f"  OK    {f['name']}")
            elif f["kind"] == "drift":
                print(f"  FAIL  {f['name']}")
                if f["only_in_pydantic"]:
                    print(f"        only in Pydantic: {f['only_in_pydantic']}")
                if f["only_in_db"]:
                    print(f"        only in DB:       {f['only_in_db']}")
            else:
                print(f"  ERR   {f['name']}: {f['detail']}")

    return 1 if drift else 0


if __name__ == "__main__":
    sys.exit(main())
