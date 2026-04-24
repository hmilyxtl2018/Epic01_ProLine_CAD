"""Process-constraint validator (Phase 2.4).

Pure functions over a list of `ProcessConstraint` rows — no DB access.
Two checks for the MVP:

1. **DAG cycle detection** on `predecessor` edges (DFS three-colour).
2. **Resource over-commit warning**: if a single `resource` group
   names more assets than its declared `capacity`, flag SOFT.
3. **Takt sanity** is enforced upstream by Pydantic (max_s >= min_s),
   but we double-check here in case rows pre-date that schema.

Returns a :class:`ValidationReport` with zero or more
:class:`ValidationIssue` rows. Callers typically expose this via
``GET /sites/{id}/constraints/validate``.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from app.schemas.constraints import ValidationIssue, ValidationReport


# Three-colour DFS markers.
_WHITE, _GRAY, _BLACK = 0, 1, 2


def _build_predecessor_graph(
    rows: Iterable[Any],
) -> tuple[dict[str, list[str]], dict[tuple[str, str], str]]:
    """Return (adjacency, edge_to_constraint_id)."""
    adj: dict[str, list[str]] = {}
    edge_owner: dict[tuple[str, str], str] = {}
    for r in rows:
        if r.kind != "predecessor" or not r.is_active:
            continue
        p = r.payload or {}
        # Pydantic uses alias "from"; raw JSON might come either way.
        a = p.get("from") or p.get("from_asset")
        b = p.get("to") or p.get("to_asset")
        if not (isinstance(a, str) and isinstance(b, str)):
            continue
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, [])
        edge_owner[(a, b)] = r.constraint_id
    return adj, edge_owner


def _find_cycle(adj: dict[str, list[str]]) -> list[str] | None:
    """Return one cycle as a list of node ids, or None."""
    color: dict[str, int] = {n: _WHITE for n in adj}
    parent: dict[str, str | None] = {n: None for n in adj}

    def dfs(start: str) -> list[str] | None:
        stack: list[tuple[str, int]] = [(start, 0)]
        while stack:
            node, idx = stack[-1]
            if idx == 0:
                color[node] = _GRAY
            children = adj.get(node, [])
            if idx < len(children):
                stack[-1] = (node, idx + 1)
                nxt = children[idx]
                if color.get(nxt, _WHITE) == _GRAY:
                    # Reconstruct cycle by walking parents from `node` to `nxt`.
                    cycle = [nxt, node]
                    cur = parent.get(node)
                    while cur is not None and cur != nxt:
                        cycle.append(cur)
                        cur = parent.get(cur)
                    cycle.reverse()
                    return cycle
                if color.get(nxt, _WHITE) == _WHITE:
                    parent[nxt] = node
                    color[nxt] = _GRAY
                    stack.append((nxt, 0))
            else:
                color[node] = _BLACK
                stack.pop()
        return None

    for n in list(adj):
        if color[n] == _WHITE:
            cyc = dfs(n)
            if cyc is not None:
                return cyc
    return None


def _check_resource_overcommit(rows: Iterable[Any]) -> list[ValidationIssue]:
    """Flag rows where len(asset_ids) > capacity (likely modelling mistake)."""
    issues: list[ValidationIssue] = []
    for r in rows:
        if r.kind != "resource" or not r.is_active:
            continue
        p = r.payload or {}
        ids = p.get("asset_ids") or []
        cap = p.get("capacity", 1)
        if isinstance(ids, list) and isinstance(cap, int) and len(ids) > cap:
            issues.append(
                ValidationIssue(
                    severity="warning",
                    code="resource_overcommit",
                    message=(
                        f"resource '{p.get('resource', '?')}' has capacity={cap} "
                        f"but {len(ids)} assets compete for it"
                    ),
                    constraint_ids=[r.constraint_id],
                    asset_ids=[a for a in ids if isinstance(a, str)],
                )
            )
    return issues


def _check_takt_sanity(rows: Iterable[Any]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for r in rows:
        if r.kind != "takt" or not r.is_active:
            continue
        p = r.payload or {}
        lo, hi = p.get("min_s"), p.get("max_s")
        if isinstance(lo, (int, float)) and isinstance(hi, (int, float)) and hi < lo:
            issues.append(
                ValidationIssue(
                    severity="error",
                    code="takt_inverted",
                    message=f"takt max_s ({hi}) < min_s ({lo})",
                    constraint_ids=[r.constraint_id],
                    asset_ids=[p.get("asset_id")] if isinstance(p.get("asset_id"), str) else [],
                )
            )
    return issues


def validate_constraints(site_model_id: str, rows: list[Any]) -> ValidationReport:
    """Validate a fully-loaded constraint set for one site model."""
    issues: list[ValidationIssue] = []

    adj, edge_owner = _build_predecessor_graph(rows)
    cycle = _find_cycle(adj)
    if cycle:
        # Walk consecutive pairs to collect constraint_ids that form the cycle.
        cids: list[str] = []
        for i in range(len(cycle) - 1):
            cid = edge_owner.get((cycle[i], cycle[i + 1]))
            if cid:
                cids.append(cid)
        # Close the loop edge.
        last = edge_owner.get((cycle[-1], cycle[0]))
        if last:
            cids.append(last)
        issues.append(
            ValidationIssue(
                severity="error",
                code="cycle",
                message="predecessor graph has a cycle: " + " -> ".join(cycle + [cycle[0]]),
                constraint_ids=cids,
                asset_ids=cycle,
            )
        )

    issues.extend(_check_resource_overcommit(rows))
    issues.extend(_check_takt_sanity(rows))

    return ValidationReport(
        site_model_id=site_model_id,
        ok=not any(i.severity == "error" for i in issues),
        checked_count=len(rows),
        issues=issues,
    )
