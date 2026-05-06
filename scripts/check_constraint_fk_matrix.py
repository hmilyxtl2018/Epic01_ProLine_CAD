"""Constraint subsystem FK matrix gate.

Asserts that the live database FK topology for the 6 constraint tables
matches the matrix in
[docs/constraint_subsystem_data_model.md §2](
    ../docs/constraint_subsystem_data_model.md#2-\u4e3b\u5916\u952e\u77e9\u9635).

CI exit codes:
  0  matches blueprint
  1  drift detected (CI-blocking)
  2  internal error (DB unreachable, etc.)

Usage:
  $env:POSTGRES_DSN = "postgresql+psycopg2://proline:proline_dev@127.0.0.1:5434/proline_cad"
  python scripts/check_constraint_fk_matrix.py
  python scripts/check_constraint_fk_matrix.py --json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


# Each entry: (table, column) -> (referenced_table, referenced_column).
# Source of truth: docs/constraint_subsystem_data_model.md §2.
_EXPECTED_FKS: frozenset[tuple[str, str, str, str]] = frozenset(
    {
        ("constraint_sets", "site_model_id", "site_models", "site_model_id"),
        ("constraint_sets", "mcp_context_id", "mcp_contexts", "mcp_context_id"),
        ("process_constraints", "constraint_set_id", "constraint_sets", "id"),
        ("process_constraints", "site_model_id", "site_models", "site_model_id"),
        ("process_constraints", "mcp_context_id", "mcp_contexts", "mcp_context_id"),
        ("process_graphs", "constraint_set_id", "constraint_sets", "id"),
        (
            "constraint_citations",
            "process_constraint_id",
            "process_constraints",
            "id",
        ),
        ("constraint_citations", "source_id", "constraint_sources", "source_id"),
        (
            "constraint_source_version_events",
            "source_id",
            "constraint_sources",
            "source_id",
        ),
    }
)


_FK_QUERY = """
SELECT  tc.table_name,
        kcu.column_name,
        ccu.table_name  AS referenced_table,
        ccu.column_name AS referenced_column
  FROM  information_schema.table_constraints  tc
  JOIN  information_schema.key_column_usage   kcu
        ON tc.constraint_name = kcu.constraint_name
       AND tc.table_schema    = kcu.table_schema
  JOIN  information_schema.constraint_column_usage ccu
        ON ccu.constraint_name = tc.constraint_name
       AND ccu.table_schema    = tc.table_schema
 WHERE  tc.constraint_type = 'FOREIGN KEY'
   AND  tc.table_schema    = 'public'
   AND  tc.table_name IN (
            'constraint_sets',
            'process_constraints',
            'process_graphs',
            'constraint_sources',
            'constraint_citations',
            'constraint_source_version_events'
        )
 ORDER BY tc.table_name, kcu.column_name;
"""


@dataclass(frozen=True)
class _Drift:
    kind: str  # "missing" | "unexpected"
    fk: tuple[str, str, str, str]


def _fetch_actual_fks(dsn: str) -> set[tuple[str, str, str, str]]:
    import sqlalchemy as sa

    engine = sa.create_engine(dsn, future=True)
    try:
        with engine.connect() as conn:
            rows = conn.execute(sa.text(_FK_QUERY)).all()
    finally:
        engine.dispose()
    return {(r[0], r[1], r[2], r[3]) for r in rows}


def _diff(actual: set[tuple[str, str, str, str]]) -> list[_Drift]:
    findings: list[_Drift] = []
    for fk in _EXPECTED_FKS - actual:
        findings.append(_Drift(kind="missing", fk=fk))
    for fk in actual - _EXPECTED_FKS:
        findings.append(_Drift(kind="unexpected", fk=fk))
    return findings


def _format_human(findings: list[_Drift]) -> str:
    if not findings:
        return "constraint subsystem FK matrix matches blueprint (9 edges)."
    lines = ["constraint subsystem FK drift:"]
    for d in findings:
        t, c, rt, rc = d.fk
        marker = "MISSING " if d.kind == "missing" else "UNEXPECTED"
        lines.append(f"  [{marker}] {t}.{c} -> {rt}.{rc}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit JSON for CI")
    args = parser.parse_args(argv)

    dsn = os.environ.get("POSTGRES_DSN", "").strip()
    if not dsn:
        msg = "POSTGRES_DSN not set; skipping FK matrix check."
        print(msg, file=sys.stderr)
        return 0  # treat as soft-skip in non-DB envs (mirrors db_fixture mark)

    try:
        actual = _fetch_actual_fks(dsn)
    except Exception as exc:  # pragma: no cover - DB connectivity errors
        print(f"FK matrix check internal error: {exc}", file=sys.stderr)
        return 2

    findings = _diff(actual)

    if args.json:
        print(
            json.dumps(
                {
                    "ok": not findings,
                    "drift": [
                        {"kind": d.kind, "fk": list(d.fk)} for d in findings
                    ],
                },
                indent=2,
            )
        )
    else:
        print(_format_human(findings))

    return 0 if not findings else 1


if __name__ == "__main__":
    raise SystemExit(main())
