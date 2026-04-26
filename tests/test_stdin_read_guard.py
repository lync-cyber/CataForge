"""Static guard: ``sys.stdin.read()`` (and friends) is banned outside
``cataforge.core.io``.

Python's text-mode stdin decodes incoming bytes through the platform
locale — cp936 on a Chinese Windows install, cp1252 on Western Windows,
UTF-8 on most Linux. When a tool pipes UTF-8 in (shell heredocs, IDE
hook payloads, MCP/agent input) the locale mismatch corrupts multi-byte
characters into either a hard ``UnicodeDecodeError`` or, under
``errors='surrogateescape'``, silent ``\\udcXX`` surrogates that explode
later when re-encoded as UTF-8.

:func:`cataforge.core.io.read_stdin_utf8` is the single approved entry
point — it reads raw bytes from ``sys.stdin.buffer`` and decodes them
as UTF-8 itself, sidestepping the locale entirely. Every other call
site MUST go through it (or :func:`cataforge.hook.base.read_hook_input`,
which wraps it).

This test parses ``src/cataforge/`` with ``ast`` so docstrings and
comments that *mention* the bad pattern (like this one) are not false
positives — only actual call expressions trip the guard.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src" / "cataforge"

# Files allowed to call ``sys.stdin.read*`` directly. Keep this list
# minimal — every entry is a place where the locale trap could resurface,
# so additions need a justification in the call site itself.
ALLOWED: frozenset[str] = frozenset({
    # The helper that everyone else delegates to.
    "core/io.py",
})

_FORBIDDEN_METHODS: frozenset[str] = frozenset({"read", "readline", "readlines"})


class _StdinReadFinder(ast.NodeVisitor):
    """Collect ``sys.stdin.<method>()`` call sites for the forbidden methods."""

    def __init__(self) -> None:
        self.hits: list[tuple[int, str]] = []

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802 — ast API
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr in _FORBIDDEN_METHODS
            and isinstance(func.value, ast.Attribute)
            and func.value.attr == "stdin"
            and isinstance(func.value.value, ast.Name)
            and func.value.value.id == "sys"
        ):
            self.hits.append((node.lineno, func.attr))
        self.generic_visit(node)


def test_finder_catches_forbidden_and_skips_buffer() -> None:
    """Sanity check on the AST matcher itself — a vacuous guard (one that
    never fires) would silently let regressions through. Pin the contract:
    forbidden patterns are flagged, and ``sys.stdin.buffer.read()`` is not.
    """
    sample = (
        "import sys\n"
        "a = sys.stdin.read()\n"            # line 2 — flagged
        "b = sys.stdin.readline()\n"        # line 3 — flagged
        "c = sys.stdin.readlines()\n"       # line 4 — flagged
        "d = sys.stdin.buffer.read()\n"     # line 5 — OK
        "e = my_stdin.read()\n"             # line 6 — OK (different object)
    )
    finder = _StdinReadFinder()
    finder.visit(ast.parse(sample))
    assert finder.hits == [(2, "read"), (3, "readline"), (4, "readlines")]


def test_no_text_mode_stdin_read_outside_core_io() -> None:
    violations: list[str] = []

    for path in sorted(SRC_DIR.rglob("*.py")):
        rel = path.relative_to(SRC_DIR).as_posix()
        if rel in ALLOWED:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:
            # Scaffold templates can intentionally contain placeholders that
            # don't parse — those live under _assets/ and ship as files, not
            # imported modules. Skip them; the guard targets real code only.
            continue

        finder = _StdinReadFinder()
        finder.visit(tree)
        for lineno, method in finder.hits:
            violations.append(f"{rel}:{lineno}: sys.stdin.{method}(...)")

    assert not violations, (
        "Use cataforge.core.io.read_stdin_utf8() (or "
        "cataforge.hook.base.read_hook_input() for hooks) instead of "
        "sys.stdin.read*(). Python's text-mode stdin decodes through the "
        "platform locale and corrupts UTF-8 payloads on non-UTF-8 systems "
        "(Windows cp936/cp1252 in particular).\n\nViolations:\n  - "
        + "\n  - ".join(violations)
    )
