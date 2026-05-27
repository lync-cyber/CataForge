#!/usr/bin/env python3
"""Guard: error-toned ``click.echo`` / ``click.secho`` lines under
``src/cataforge/cli/`` must route to stderr via ``err=True``.

Rule: when the first argument to ``click.echo(...)`` / ``click.secho(...)``
starts with one of the error-marker prefixes below, the call must
also pass ``err=True`` somewhere in the same call. Otherwise scripts
that pipe a command's success output (``cataforge … | jq``) lose the
error message into stdout where the consumer expects only the
happy-path payload.

Error-marker prefixes — chosen to catch the user-facing tone without
flagging structured stdout reports:

    Error: / ERROR: / Cannot / Could not / Refused / Invalid / Failed

Notably **not** flagged:

* ``cli/doctor/**`` — the whole doctor subtree IS a structured stdout
  report; FAIL / MISSING rows there are intentional stdout content
  (the exit code carries pass/fail semantics).
* Generic ``"fail"`` / ``"error"`` substrings anywhere in the message
  (too noisy — matches success-summary lines like ``f"  errors: {n}"``).

Per-call exemption: add ``# allow-stdout-echo: <reason>`` on the same
line. Use sparingly; the explicit comment turns "code smell" into
"documented contract".
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))
from cataforge.utils.common import ensure_utf8  # noqa: E402

ensure_utf8()

SCAN_DIR = REPO_ROOT / "src" / "cataforge" / "cli"
EXEMPT_SUBTREES = (
    # Doctor produces a structured stdout report by design — FAIL /
    # MISSING rows there are part of the report, not error messages
    # that should be redirected.
    "src/cataforge/cli/doctor",
)

# Match ``click.echo(...)`` or ``click.secho(...)`` whose first positional
# arg is a string literal starting with an error-marker prefix.
# Group 1: the literal's body so we can check the prefix.
ECHO_CALL_RE = re.compile(
    r"""click\.(?:echo|secho)\(\s*               # the call
        (?:f?r?)["']                              # opening quote (f"..." also accepted)
        ([^"']*)                                  # first-arg body (no inner quote)
    """,
    re.VERBOSE,
)

ERROR_PREFIXES = (
    "Error:",
    "ERROR:",
    "Cannot ",
    "Could not ",
    "Refused",
    "Invalid ",
    "Failed",
    "FAIL:",
)

ALLOW_MARKER = "# allow-stdout-echo"


def _has_err_kwarg(call_text: str) -> bool:
    """``err=True`` (any whitespace) anywhere in the call's surface text."""
    return re.search(r"\berr\s*=\s*True\b", call_text) is not None


def _extract_full_call(text: str, start_offset: int) -> str:
    """Return the substring from ``start_offset`` up to (and including)
    the closing ``)`` that balances the opening ``(`` at the call site.

    Handles nested parens within string literals naively — adequate for
    the click call shapes used in this repo (no f-string expressions
    contain unbalanced parens in our cli/ code)."""
    depth = 0
    for i in range(start_offset, len(text)):
        ch = text[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return text[start_offset:i + 1]
    return text[start_offset:]  # unterminated — caller will see it


def main() -> int:
    if not SCAN_DIR.is_dir():
        print(f"OK: {SCAN_DIR} not present, nothing to scan")
        return 0

    offenders: list[str] = []
    files_scanned = 0
    for path in sorted(SCAN_DIR.rglob("*.py")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        if any(rel.startswith(exempt) for exempt in EXEMPT_SUBTREES):
            continue
        files_scanned += 1
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        for line_no, line in enumerate(lines, start=1):
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            if ALLOW_MARKER in line:
                continue
            m = ECHO_CALL_RE.search(line)
            if not m:
                continue
            body = m.group(1)
            if not any(body.startswith(p) for p in ERROR_PREFIXES):
                continue
            # Locate the opening ``(`` of this click.echo call and grab
            # the full call text — the closing ``)`` may live on a later
            # line (multi-line calls), so we walk over the joined tail
            # to check for err=True there too.
            opening_paren = text.find("(", text.find(m.group(0), 0))
            full_call = _extract_full_call(text, opening_paren)
            if _has_err_kwarg(full_call):
                continue
            offenders.append(f"{rel}:{line_no}: {line.strip()}")

    if offenders:
        print(
            f"FAIL: {len(offenders)} error-toned click.echo / click.secho "
            f"call(s) under src/cataforge/cli/ are missing err=True. Errors "
            f"belong on stderr so scripts piping success output ("
            f"`cataforge … | jq`) don't lose them into stdout. Add err=True "
            f"to the call, or `{ALLOW_MARKER}: <reason>` on the same line "
            f"if the message genuinely belongs in the structured stdout "
            f"output (rare).",
            file=sys.stderr,
        )
        for offender in offenders:
            print(f"  {offender}", file=sys.stderr)
        return 1

    print(
        f"OK: scanned {files_scanned} cli file(s), no error-toned echoes "
        f"miss err=True"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
