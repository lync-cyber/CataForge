"""B4 — bare numeric literals that should reference framework constants."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

from cataforge.core.paths import ProjectPaths

from .._framework_data import build_constant_literals
from .._types import Report


def _iter_md_files(scan_roots: tuple[Path, ...]) -> Iterator[tuple[Path, str]]:
    for base in scan_roots:
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.md")):
            try:
                text = path.read_text()
            except OSError:
                continue
            yield path, text


def _rel_display(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def _flag_line_literals(
    line: str,
    line_outside_inline_code: str,
    constant_literals: tuple[tuple[str, str, str], ...],
    rel: str,
    lineno: int,
    report: Report,
) -> None:
    for const_name, pattern, hint in constant_literals:
        if const_name in line:
            continue
        if re.search(pattern, line_outside_inline_code):
            report.add(
                "B4_hardcoded_constants",
                "WARN",
                f"{rel}:{lineno}",
                f"裸数值 {hint!r} 未引用常量名 {const_name}",
            )


def check_b4_hardcoded_constants(root: Path, report: Report) -> None:
    """B4-α: bare numeric literals that should reference constants."""
    paths = ProjectPaths(root)
    constant_literals = build_constant_literals(root)
    scan_roots = (paths.agents_dir, paths.skills_dir, paths.rules_dir)
    for path, text in _iter_md_files(scan_roots):
        rel = _rel_display(path, root)
        in_code_block = False
        for lineno, line in enumerate(text.splitlines(), start=1):
            stripped = line.lstrip()
            if stripped.startswith("```"):
                in_code_block = not in_code_block
                continue
            # Skip fenced code and markdown table rows: the former quotes
            # examples, the latter defines the constant value itself
            # (e.g. ``| MAX_QUESTIONS_PER_BATCH | 3 |``).
            if in_code_block or stripped.startswith("|"):
                continue
            # Strip backtick-wrapped spans: quoted examples (e.g. "`≤3 问`"
            # describing the rule), not literal usage.
            line_outside_inline_code = re.sub(r"`[^`]*`", "", line)
            _flag_line_literals(
                line, line_outside_inline_code, constant_literals, rel, lineno, report
            )
