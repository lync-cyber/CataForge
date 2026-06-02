#!/usr/bin/env python3
"""Enforced guard against redundant ``encoding="utf-8"`` on file I/O under
``src/cataforge/``.

The process runs in Python UTF-8 Mode end to end — ``ensure_utf8`` re-execs
every entry point under ``PYTHONUTF8=1`` (and the test session does the same
via ``tests/conftest.py``). So ``open()`` / ``Path.read_text()`` /
``Path.write_text()`` already default to UTF-8; an explicit
``encoding="utf-8"`` on those calls is noise that invites drift back toward
per-callsite encoding plumbing.

The UTF-8 decision lives in the boundary layer instead — those modules keep
their explicit encoding and are exempt below. A genuine non-UTF-8 read (a
legacy fixture, a binary-adjacent codec) names that codec and is not matched
here. Reach for an inline ``# allow-explicit-encoding: <reason>`` only when a
call must pin ``utf-8`` for a reason the boundary layer can't carry.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))
from cataforge.utils.common import ensure_utf8  # noqa: E402

ensure_utf8()

SCAN_DIR = REPO_ROOT / "src" / "cataforge"
EXEMPT_PATHS = (
    # The boundary layer that defines/guards the UTF-8 contract.
    "src/cataforge/utils/run_subprocess.py",
    "src/cataforge/utils/atomic_write.py",
    "src/cataforge/utils/common.py",
    "src/cataforge/core/io.py",
)

# A text-mode file open: builtin ``open(`` / ``Path.open(`` / ``read_text(`` /
# ``write_text(``. ``\bopen`` deliberately excludes ``Popen``/``urlopen``
# (subprocess + network boundaries keep their own encoding).
IO_RE = re.compile(r"\bopen\s*\(|\b(?:read|write)_text\s*\(")
ENCODING_RE = re.compile(r"""encoding\s*=\s*['"]utf-?8['"]""")
ALLOW_MARKER = "# allow-explicit-encoding"


def main() -> int:
    if not SCAN_DIR.is_dir():
        print(f"OK: {SCAN_DIR} not present, nothing to scan")
        return 0

    offenders: list[str] = []
    for path in sorted(SCAN_DIR.rglob("*.py")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel in EXEMPT_PATHS:
            continue
        text = path.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), start=1):
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            if not IO_RE.search(line) or not ENCODING_RE.search(line):
                continue
            if ALLOW_MARKER in line:
                continue
            offenders.append(f"{rel}:{line_no}: {line.strip()}")

    if not offenders:
        print('OK: no redundant encoding="utf-8" on file I/O')
        return 0

    print(
        f'FAIL: {len(offenders)} redundant encoding="utf-8" on file I/O under '
        f"src/cataforge/. The process runs in UTF-8 Mode — drop the argument, or "
        f"add `{ALLOW_MARKER}: <reason>` inline.",
        file=sys.stderr,
    )
    for offender in offenders:
        print(f"  {offender}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
