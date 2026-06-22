"""Guard: enforce the layered dependency direction inside ``src/cataforge``.

Direction (a layer may import only itself or layers to its right):

    interface → application → {runtime, domain} → adapter → core → utils

Each top-level package directly under ``cataforge/`` belongs to one layer.
A module may import ``cataforge.<layer>...`` only when the target layer is at
the same depth or more foundational (higher rank). An upward **static**
(module-level) import (e.g. ``core`` importing ``interface``) inverts the
dependency graph / creates an import cycle and is a FAIL.

Function-local (lazy) imports and ``if TYPE_CHECKING:`` imports used for
upward orchestration are tracked against an explicit allowlist
(``UPWARD_IMPORT_ALLOWLIST`` below). An allowlisted entry is emitted as a
comment explaining the reason for the exception. Any *new* upward import that
is not in the allowlist is a FAIL — this prevents silent regression back to
the anti-patterns that were eliminated before this guard was tightened.

Module-level upward imports always FAIL (unless ``# allow-layer-dep:`` is
present), as they create static dependency cycles.

Per-line ``# allow-layer-dep: <reason>`` opts a specific module-level line out.

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

# Allowlist for upward imports that live in function bodies or TYPE_CHECKING
# blocks.  Each entry is a (src_file_suffix, target_module) pair where
# src_file_suffix is the path relative to PKG_ROOT using forward slashes.
# Entries here are *approved* upward dependencies — they are not silently
# ignored but explicitly acknowledged.  Any upward import NOT in this list
# that appears in a function body or TYPE_CHECKING block is a FAIL.
#
# Format: (src_file relative to src/cataforge/, imported module prefix)
# The module prefix is matched with str.startswith so both the exact module
# and any sub-module of it are covered.
UPWARD_IMPORT_ALLOWLIST: tuple[tuple[str, str], ...] = (
    # adapter platform adapters use TYPE_CHECKING-only imports of
    # runtime.deploy.manifest to type-annotate the DeployManifest parameter
    # without creating a runtime circular import.
    (
        "adapter/platform/cursor.py",
        "cataforge.runtime.deploy.manifest",
    ),
    (
        "adapter/platform/opencode.py",
        "cataforge.runtime.deploy.manifest",
    ),
    # runtime builtin uses lazy application-layer import to load feedback
    # constants / functions inside CLI entry points, avoiding a module-level
    # cycle between runtime.skill.builtins and application.
    (
        "runtime/skill/builtins/framework_feedback/framework_feedback.py",
        "cataforge.application.feedback",
    ),
    # skill runner lazily reads the application-layer doc_type→phase map to
    # attribute an auto-emitted event to the reviewed artifact's phase; the
    # SDLC phase policy stays cohesive in application.phase rather than being
    # duplicated down a layer.
    (
        "runtime/skill/runner.py",
        "cataforge.application.phase",
    ),
)


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


def _is_allowlisted(src_rel: str, module: str) -> bool:
    """Return True iff (src_rel, module) matches an allowlist entry."""
    for allowed_src, allowed_mod in UPWARD_IMPORT_ALLOWLIST:
        if src_rel == allowed_src and module.startswith(allowed_mod):
            return True
    return False


def main() -> int:
    violations: list[str] = []
    for path in sorted(PKG_ROOT.rglob("*.py")):
        rel = path.relative_to(PKG_ROOT)
        if not rel.parts or rel.parts[0] not in LAYER_RANK:
            continue  # top-level __init__/__main__ etc. are not in a layer
        src_layer = rel.parts[0]
        src_rank = LAYER_RANK[src_layer]
        # Normalise to forward-slash for cross-platform allowlist matching.
        src_rel = rel.as_posix()

        try:
            text = path.read_text(encoding="utf-8")
            tree = ast.parse(text)
        except (OSError, SyntaxError):
            continue
        lines = text.splitlines()
        tc_lines = _typecheck_only_lines(tree)
        fn_lines = _function_body_lines(tree)
        module_level_exempt = set[int]()  # only allow-marker can exempt module-level

        for lineno, module in _imports(tree):
            tgt = _target_layer(module)
            if tgt is None or tgt == src_layer:
                continue
            if LAYER_RANK[tgt] >= src_rank:
                continue  # allowed direction

            is_lazy = lineno in tc_lines or lineno in fn_lines

            if is_lazy:
                # Lazy / TYPE_CHECKING upward imports: check allowlist.
                if _is_allowlisted(src_rel, module):
                    continue
                violations.append(
                    f"{path.relative_to(REPO_ROOT)}:{lineno}: "
                    f"{src_layer} (rank {src_rank}) lazy-imports {tgt} "
                    f"(rank {LAYER_RANK[tgt]}) — not in upward allowlist: {module}\n"
                    f"  Add to UPWARD_IMPORT_ALLOWLIST in "
                    f"scripts/checks/check_layer_dependencies.py if intentional."
                )
            else:
                # Module-level upward import: FAIL unless allow-marker present.
                if lineno in module_level_exempt:
                    continue
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
            "consumer, or append `# allow-layer-dep: <reason>` if intentional.\n"
            "For function-body / TYPE_CHECKING upward imports add an entry to\n"
            "UPWARD_IMPORT_ALLOWLIST in scripts/checks/check_layer_dependencies.py."
        )
        return 1

    allowlist_count = len(UPWARD_IMPORT_ALLOWLIST)
    print(
        f"OK: layered dependency direction clean ({len(LAYER_RANK)} layers, "
        f"{allowlist_count} allowlisted lazy/TYPE_CHECKING upward import(s))"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
