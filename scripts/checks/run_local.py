#!/usr/bin/env python3
"""One-stop local pre-commit gate.

Runs the same static checks that `.pre-commit-config.yaml` wires to
git hooks, but **without requiring the `pre-commit` package itself
to be installed**. Useful in two cases:

* freshly-cloned environments where `pre-commit install` hasn't run yet
* automated agents (Claude Code, scheduled tasks) that don't always
  install dev extras before touching code

Returns 0 iff every check exits 0; otherwise returns 1.

The set of checks mirrors the no-arg / repo-wide hooks declared in
`.pre-commit-config.yaml`. Per-file hooks like `workflow-yaml-parse`
(needs file args) are skipped — they're cheap on the affected commit
but expensive on the whole repo, so CI keeps them.

Run before every commit:

    python scripts/checks/run_local.py

Or via the canonical pre-commit if installed:

    pre-commit run --all-files
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Each entry: (label, argv). argv is invoked under the current Python
# interpreter so a venv-local ruff is preferred over any global one.
CHECKS: list[tuple[str, list[str]]] = [
    ("ruff (lint)", [sys.executable, "-m", "ruff", "check", "src", "tests", "scripts"]),
    (
        "no marketing adverbs",
        [sys.executable, str(REPO_ROOT / "scripts" / "checks" / "check_no_marketing_words.py")],
    ),
    (
        "no design-phase residue",
        [sys.executable, str(REPO_ROOT / "scripts" / "checks" / "check_no_design_residue.py")],
    ),
    (
        "no language coupling",
        [sys.executable, str(REPO_ROOT / "scripts" / "checks" / "check_no_language_coupling.py")],
    ),
    (
        "doc structure hygiene",
        [sys.executable, str(REPO_ROOT / "scripts" / "checks" / "check_doc_structure.py")],
    ),
    (
        "no QueryBoolean == True",
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "checks" / "check_no_query_boolean_eq_true.py"),
        ],
    ),
    (
        "schema ↔ python mirror parity",
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "checks" / "check_schema_python_parity.py"),
        ],
    ),
]


def main() -> int:
    # UTF-8 stdio so Chinese diagnostic messages do not crash on
    # Windows cp1252 terminals.
    for _stream_name in ("stdout", "stderr"):
        _stream = getattr(sys, _stream_name)
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="replace")

    failed: list[str] = []
    for label, argv in CHECKS:
        print(f"\n=== {label} ===", flush=True)
        result = subprocess.run(argv, cwd=REPO_ROOT, check=False)  # noqa: S603
        if result.returncode != 0:
            failed.append(label)

    print("\n" + "=" * 60)
    if failed:
        print(f"FAIL: {len(failed)} check(s) failed:", file=sys.stderr)
        for label in failed:
            print(f"  - {label}", file=sys.stderr)
        return 1
    print(f"OK: {len(CHECKS)} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
