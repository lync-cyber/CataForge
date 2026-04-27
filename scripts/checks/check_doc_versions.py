#!/usr/bin/env python3
"""Anti-rot guard: hard-coded version numbers in docs are not behind reality.

Watches a small set of documents that historically embedded a stale
``"version": "0.1.X"`` example or "v0.X+" promise. Fails (exit 1) if
any of them references a 0.1.x version number that is BELOW the current
``cataforge.__version__``.

It does not check forward versions (e.g. "v0.2 planned") to avoid
flagging legitimate roadmap text. The narrow scope is deliberate:
enforcing "every X.Y.Z mention <= __version__" repo-wide would catch
CHANGELOG entries that legitimately describe past versions.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Embed-style cases — `"version": "0.1.x"` blocks in JSON examples.
# Each entry: (path, regex with one numbered capture group).
WATCHED: list[tuple[Path, re.Pattern[str]]] = [
    (
        REPO_ROOT / "docs" / "reference" / "configuration.md",
        re.compile(r'"version"\s*:\s*"(0\.1\.\d+)"'),
    ),
]


def installed_version() -> tuple[int, int, int] | None:
    sys.path.insert(0, str(REPO_ROOT / "src"))
    try:
        from cataforge import __version__ as v
    except Exception:  # noqa: BLE001
        return None
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)", v)
    if m is None:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def main() -> int:
    pkg = installed_version()
    if pkg is None:
        print("ERROR: could not import cataforge.__version__", file=sys.stderr)
        return 1
    fails: list[str] = []
    for path, pattern in WATCHED:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for m in pattern.finditer(text):
            v = m.group(1)
            tup = tuple(int(x) for x in v.split("."))
            if tup < pkg:
                rel = path.relative_to(REPO_ROOT)
                pkg_v = ".".join(str(x) for x in pkg)
                fails.append(f"{rel}: example uses v{v}, package is v{pkg_v}")

    if fails:
        print("Anti-rot: documented example version is stale", file=sys.stderr)
        for f in fails:
            print(f"  {f}", file=sys.stderr)
        print(
            '\nFix: bump the example to the current version, or replace the literal '
            'with a placeholder like "0.0.0-template" that is resolved at read time.',
            file=sys.stderr,
        )
        return 1

    print(f"OK: doc version examples track package v{'.'.join(str(x) for x in pkg)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
