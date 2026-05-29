#!/usr/bin/env python3
"""Anti-rot guard: no `query(...ASK...) == True` antipatterns under cataforge.domain.kg.

pyoxigraph 0.5.x returns a `QueryBoolean` from `Store.query()` for ASK
queries. `QueryBoolean == True` silently evaluates False even when the
answer is True (spike-2 §2.2, issue #142). Every ASK consumer in the KG
layer must go through `cataforge.domain.kg._ask.ask(store, sparql) -> bool`.

This guard rejects `.query(...) == True` / `... == True` / `is True`
patterns when they appear in `src/cataforge/domain/kg/**.py` so the bug cannot
sneak back via a copy-paste from external SPARQL examples.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))
from cataforge.utils.common import ensure_utf8  # noqa: E402

ensure_utf8()

SCAN_DIRS = [REPO_ROOT / "src" / "cataforge" / "domain" / "kg"]

QUERY_EQ_TRUE = re.compile(
    r"\.query\s*\([^)]*\)\s*(==|is)\s*True\b",
    re.DOTALL,
)
QUERY_EQ_FALSE = re.compile(
    r"\.query\s*\([^)]*\)\s*(==|is)\s*False\b",
    re.DOTALL,
)


def _is_inside_docstring_or_quoted(line: str, match_start: int) -> bool:
    """Heuristic: match occurs inside a backtick-quoted span or a string literal.

    Sub-PR 2's `_ask.py` discusses the antipattern in its module docstring;
    the docstring uses ` ``query(...) == True`` ` formatting, so detecting
    backtick spans is the cheap correct filter.
    """
    head = line[:match_start]
    # Inside a backtick-delimited span (markdown code formatting in docstring).
    if head.count("`") % 2 == 1:
        return True
    # Inside a single- or double-quoted string literal that starts on the same line.
    # (Not bullet-proof for multi-line strings, but check_no_design_residue
    # / check_no_marketing_words use the same line-scoped heuristic.)
    return head.count('"') % 2 == 1 or head.count("'") % 2 == 1


def main() -> int:
    offenders: list[str] = []
    for scan_dir in SCAN_DIRS:
        if not scan_dir.is_dir():
            continue
        for path in sorted(scan_dir.rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            for line_no, line in enumerate(text.splitlines(), start=1):
                stripped = line.lstrip()
                if stripped.startswith("#"):
                    continue
                match = QUERY_EQ_TRUE.search(line) or QUERY_EQ_FALSE.search(line)
                if match and not _is_inside_docstring_or_quoted(line, match.start()):
                    rel = path.relative_to(REPO_ROOT).as_posix()
                    offenders.append(f"{rel}:{line_no}: {line.strip()}")

    if offenders:
        print(
            "FAIL: `query(...) == True` antipattern detected under "
            "src/cataforge/domain/kg/ (spike-2 §2.2 / issue #142). pyoxigraph "
            "returns QueryBoolean for ASK; `== True` silently always "
            "evaluates False. Route all ASK consumption through "
            "`cataforge.domain.kg._ask.ask(store, sparql) -> bool`.",
            file=sys.stderr,
        )
        for offender in offenders:
            print(f"  {offender}", file=sys.stderr)
        return 1

    print(f"OK: scanned {sum(1 for d in SCAN_DIRS if d.is_dir())} dirs, no "
          f"QueryBoolean == True antipatterns")
    return 0


if __name__ == "__main__":
    sys.exit(main())
