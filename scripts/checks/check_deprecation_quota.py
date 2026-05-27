#!/usr/bin/env python3
"""Anti-rot guard: cap the number of deprecated shim call sites.

The ``cataforge.kg._shim`` module exposes 8 backward-compatible wrappers
scheduled for removal in 0.6.0.  New production code must use the typed
``KnowledgeGraph`` API instead.

This script scans ``src/`` (excluding ``_shim.py`` itself) for direct
imports or calls of the deprecated shim functions.  If the count exceeds
the hard-coded quota, the script exits non-zero so CI blocks the PR.

Exit:
    0 — within quota
    1 — quota exceeded (new shim usage detected)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

for _stream_name in ("stdout", "stderr"):
    _stream = getattr(sys, _stream_name)
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "src"

SHIM_FUNCTIONS = (
    "extract",
    "extract_batch",
    "extract_with_body",
    "plan_load",
    "build_full_index",
    "resolve_deps",
    "legacy_validate_report",
    "source_section",
)

QUOTA = 0

_IMPORT_PAT = re.compile(r"from\s+cataforge\.kg\._shim\s+import\s")
_CALL_PAT = re.compile(
    r"cataforge\.kg\._shim\.(?:" + "|".join(SHIM_FUNCTIONS) + r")\b"
)


def _scan() -> list[str]:
    hits: list[str] = []
    for py in sorted(SRC_DIR.rglob("*.py")):
        if py.name == "_shim.py":
            continue
        try:
            text = py.read_text(encoding="utf-8")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if _IMPORT_PAT.search(line) or _CALL_PAT.search(line):
                rel = py.relative_to(REPO_ROOT)
                hits.append(f"  {rel}:{i}: {line.strip()}")
    return hits


def main() -> int:
    hits = _scan()
    if len(hits) <= QUOTA:
        print(
            f"OK: {len(hits)} shim call site(s) in src/ "
            f"(quota={QUOTA})"
        )
        return 0
    print(
        f"FAIL: {len(hits)} shim call site(s) in src/ exceed "
        f"quota ({QUOTA}):"
    )
    for h in hits:
        print(h)
    print(
        "\nMigrate to the typed KnowledgeGraph API "
        "(kg.query / kg.trace / kg.transaction) "
        "or raise the quota in this script if the call is intentional."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
