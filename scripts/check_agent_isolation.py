"""Agent isolation check — fails CI if any agent imports another agent's namespace.

CLAUDE.md §5: agents must communicate only through MCP. Direct Python imports
across `agents/<X>/` boundaries break traceability and the killswitch story.

Usage:
    python scripts/check_agent_isolation.py          # whole repo
    python scripts/check_agent_isolation.py path/    # restricted scan

Exit codes:
    0  no violations
    1  one or more cross-agent imports detected
    2  invocation error (bad path, etc.)
"""

from __future__ import annotations

import argparse
import ast
import sys
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
AGENTS_ROOT = REPO_ROOT / "agents"

# Modules that any agent is allowed to import; everything else under
# `agents.<other>` is forbidden.
_ALLOWED_SHARED_PREFIXES = ("shared", "scripts", "db")


@dataclass(frozen=True)
class Violation:
    file: Path
    line: int
    own_agent: str
    imported: str

    def render(self) -> str:
        rel = self.file.relative_to(REPO_ROOT)
        return (
            f"{rel}:{self.line}: agent '{self.own_agent}' imports "
            f"forbidden module '{self.imported}'"
        )


def _agent_of(path: Path) -> str | None:
    try:
        rel = path.relative_to(AGENTS_ROOT)
    except ValueError:
        return None
    parts = rel.parts
    if not parts:
        return None
    return parts[0]


def _iter_python_files(roots: Iterable[Path]) -> Iterator[Path]:
    for root in roots:
        if root.is_file() and root.suffix == ".py":
            yield root
            continue
        if not root.is_dir():
            continue
        for path in root.rglob("*.py"):
            if any(part in {"__pycache__", ".venv", "venv"} for part in path.parts):
                continue
            yield path


def _imports_from(node: ast.AST) -> Iterator[str]:
    for child in ast.walk(node):
        if isinstance(child, ast.Import):
            for alias in child.names:
                yield alias.name
        elif isinstance(child, ast.ImportFrom):
            if child.level:
                # relative imports stay within the package; not cross-agent.
                continue
            if child.module:
                yield child.module


def _is_forbidden(own_agent: str, imported: str) -> bool:
    if not imported.startswith("agents."):
        return False
    parts = imported.split(".")
    if len(parts) < 2:
        return False
    other_agent = parts[1]
    if other_agent in _ALLOWED_SHARED_PREFIXES:
        return False
    return other_agent != own_agent


def scan(paths: Iterable[Path]) -> list[Violation]:
    violations: list[Violation] = []
    for file in _iter_python_files(paths):
        own_agent = _agent_of(file)
        if own_agent is None:
            continue
        try:
            tree = ast.parse(file.read_text(encoding="utf-8"), filename=str(file))
        except SyntaxError as exc:
            print(f"warning: skip {file}: {exc}", file=sys.stderr)
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            for imported in _imports_from(node):
                if _is_forbidden(own_agent, imported):
                    violations.append(
                        Violation(
                            file=file,
                            line=node.lineno,
                            own_agent=own_agent,
                            imported=imported,
                        )
                    )
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        default=[AGENTS_ROOT],
        help="paths to scan (default: agents/)",
    )
    args = parser.parse_args(argv)

    resolved: list[Path] = []
    for raw in args.paths:
        path = raw if raw.is_absolute() else (REPO_ROOT / raw)
        if not path.exists():
            print(f"error: path not found: {raw}", file=sys.stderr)
            return 2
        resolved.append(path)

    violations = scan(resolved)
    if not violations:
        print("agent-isolation: OK (no cross-agent imports)")
        return 0

    print(f"agent-isolation: {len(violations)} violation(s)", file=sys.stderr)
    for violation in violations:
        print(violation.render(), file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
