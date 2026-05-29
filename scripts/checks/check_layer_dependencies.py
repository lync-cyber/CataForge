"""Guard: enforce the layered dependency direction inside ``src/cataforge``.

Direction (a layer may import only itself or layers to its right):

    interface → application → {runtime, domain} → adapter → core → utils

Each top-level package directly under ``cataforge/`` belongs to one layer.
A module may import ``cataforge.<layer>...`` only when the target layer is at
the same depth or more foundational (higher rank). An upward **static**
(module-level) import (e.g. ``core`` importing ``interface``) inverts the
dependency graph / creates an import cycle and is a FAIL.

Scope: only module-level imports are checked — this is the invariant that
keeps the static graph acyclic (no lower layer statically depends on an upper
one). Function-local (lazy) imports are the sanctioned escape valve for
occasional upward orchestration calls and are intentionally exempt;
``if TYPE_CHECKING:`` imports are exempt for the same reason. Per-line
``# allow-layer-dep: <reason>`` opts a specific module-level line out.

Wired into pre-commit, ``scripts/checks/run_local.py``, and per-PR CI.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

# Reconfigure stdio to UTF-8 (the arrow glyphs below are non-ASCII) so the
# script works under CI / Windows cp1252 without a UnicodeEncodeError.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PKG_ROOT = REPO_ROOT / "src" / "cataforge"

# Layer rank: lower number = higher in the stack (more "driving").
# A layer may depend only on layers with rank >= its own.
LAYER_RANK = {
    "interface": 0,
    "application": 1,
    "runtime": 2,
    "domain": 2,
    "adapter": 3,
    "core": 4,
    "utils": 5,
}

ALLOW_MARKER = "# allow-layer-dep:"


def _target_layer(module: str) -> str | None:
    """Return the cataforge layer a dotted module belongs to, else None."""
    parts = module.split(".")
    if len(parts) < 2 or parts[0] != "cataforge":
        return None
    return parts[1] if parts[1] in LAYER_RANK else None


def _typecheck_only_lines(tree: ast.AST) -> set[int]:
    """Line numbers of imports nested under ``if TYPE_CHECKING:`` blocks."""
    guarded: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        test = node.test
        is_tc = (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
            isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
        )
        if not is_tc:
            continue
        for child in ast.walk(node):
            if isinstance(child, (ast.Import, ast.ImportFrom)):
                guarded.add(child.lineno)
    return guarded


def _function_body_lines(tree: ast.AST) -> set[int]:
    """Line numbers of imports nested inside any (async) function body."""
    lazy: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for child in ast.walk(node):
            if isinstance(child, (ast.Import, ast.ImportFrom)):
                lazy.add(child.lineno)
    return lazy


def _imports(tree: ast.AST) -> list[tuple[int, str]]:
    """Yield ``(lineno, dotted_module)`` for every import statement."""
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.append((node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            out.append((node.lineno, node.module))
    return out


def main() -> int:
    violations: list[str] = []
    for path in sorted(PKG_ROOT.rglob("*.py")):
        rel = path.relative_to(PKG_ROOT)
        if not rel.parts or rel.parts[0] not in LAYER_RANK:
            continue  # top-level __init__/__main__ etc. are not in a layer
        src_layer = rel.parts[0]
        src_rank = LAYER_RANK[src_layer]

        try:
            text = path.read_text(encoding="utf-8")
            tree = ast.parse(text)
        except (OSError, SyntaxError):
            continue
        lines = text.splitlines()
        exempt = _typecheck_only_lines(tree) | _function_body_lines(tree)

        for lineno, module in _imports(tree):
            if lineno in exempt:
                continue
            tgt = _target_layer(module)
            if tgt is None or tgt == src_layer:
                continue
            if LAYER_RANK[tgt] < src_rank:
                # Honor the marker on the import line or the line directly above
                # it (long imports keep the rationale on its own comment line).
                context = lines[max(0, lineno - 2) : lineno]
                if any(ALLOW_MARKER in ln for ln in context):
                    continue
                violations.append(
                    f"{path.relative_to(REPO_ROOT)}:{lineno}: "
                    f"{src_layer} (rank {src_rank}) imports {tgt} "
                    f"(rank {LAYER_RANK[tgt]}) — upward dependency: {module}"
                )

    if violations:
        print("FAIL: layered dependency direction violated:")
        for v in violations:
            print(f"  {v}")
        print(
            "\nAllowed direction: interface → application → "
            "{runtime, domain} → adapter → core → utils.\n"
            "Move the shared code down, invert via a Protocol defined in the "
            "consumer, or append `# allow-layer-dep: <reason>` if intentional."
        )
        return 1

    print(f"OK: layered dependency direction clean ({len(LAYER_RANK)} layers)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
