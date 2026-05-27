#!/usr/bin/env python3
"""Advisory inventory of raw ``subprocess.run`` / ``subprocess.Popen``
call sites under ``src/cataforge/``.

Background: the project's ~46 raw ``subprocess.run`` invocations each
made independent decisions about timeout, ``check=True`` vs
``check=False``, ``capture_output=True`` vs explicit ``stdout=PIPE``,
text mode + encoding. A Codex shell-out and a git probe ended up
handling errors in subtly different ways even when both "just wanted
to capture stdout."

The unified wrapper at :mod:`cataforge.utils.run_subprocess` exists to
collapse that policy surface to one entry point. Migration is gradual
(each call site has its own subtle reasons), so this guard is
**advisory only** today: it reports the current count and exits 0.

Once the migration is far enough along that the remaining call sites
genuinely need exemption (and have ``# allow-raw-subprocess: <reason>``
inline comments), flip the ``ADVISORY_MODE`` constant below to
``False`` and the guard will start enforcing.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))
from cataforge.utils.common import ensure_utf8_stdio  # noqa: E402

ensure_utf8_stdio()

SCAN_DIR = REPO_ROOT / "src" / "cataforge"
EXEMPT_PATHS = (
    # The wrapper itself is the only legitimate raw call site.
    "src/cataforge/utils/run_subprocess.py",
)

# Match ``subprocess.run(`` / ``subprocess.Popen(`` / ``subprocess.call(``
# regardless of leading whitespace. Doesn't match strings inside literals
# because each line is checked separately and lines starting with a
# string-quote prefix or a comment are skipped before the regex runs.
RAW_RE = re.compile(r"\bsubprocess\.(run|Popen|call|check_output|check_call)\s*\(")
ALLOW_MARKER = "# allow-raw-subprocess"

ADVISORY_MODE = True


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
            if not RAW_RE.search(line):
                continue
            if ALLOW_MARKER in line:
                continue
            offenders.append(f"{rel}:{line_no}: {line.strip()}")

    if not offenders:
        print("OK: no raw subprocess calls outside the wrapper")
        return 0

    if ADVISORY_MODE:
        print(
            f"ADVISORY: {len(offenders)} raw subprocess call(s) remain under "
            f"src/cataforge/. Migration to "
            f"cataforge.utils.run_subprocess.run is gradual — see the helper's "
            f"docstring for the per-site pattern. Add `{ALLOW_MARKER}: <reason>` "
            f"on the same line to silence individual exempt sites."
        )
        for offender in offenders[:10]:
            print(f"  {offender}")
        if len(offenders) > 10:
            print(f"  ... and {len(offenders) - 10} more (full list with --verbose).")
        if "--verbose" in sys.argv[1:]:
            for offender in offenders[10:]:
                print(f"  {offender}")
        return 0

    print(
        f"FAIL: {len(offenders)} raw subprocess call(s) outside the wrapper. "
        f"Use cataforge.utils.run_subprocess.run, or add "
        f"`{ALLOW_MARKER}: <reason>` inline.",
        file=sys.stderr,
    )
    for offender in offenders:
        print(f"  {offender}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
