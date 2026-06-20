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
`.pre-commit-config.yaml`, plus the two whole-tree static gates CI runs
outside pre-commit — `ruff format --check` and `mypy --strict` — so a
green local run matches CI for static analysis (only the pytest matrices
and per-file hooks remain CI-only). Per-file hooks like `workflow-yaml-parse`
(needs file args) are skipped — they're cheap on the affected commit
but expensive on the whole repo, so CI keeps them.

Checks invoked as `python -m <module>` (ruff, mypy) skip gracefully when
the module is absent — e.g. a clone without `[dev]` extras installed — so
the wrapper still runs its stdlib-only guards there; install dev extras
or rely on CI to cover the skipped ones.

Run before every commit:

    uv run --extra dev python scripts/checks/run_local.py

Or via the canonical pre-commit if installed:

    uv run pre-commit run --all-files
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Each entry: (label, argv, requires_module). argv is invoked under the current
# Python interpreter so a venv-local ruff is preferred over any global one.
# `requires_module` (or None) names the import the check needs; when it is not
# importable the check is skipped gracefully instead of failing with a
# ModuleNotFoundError, mirroring the FileNotFoundError skip for missing binaries.
CHECKS: list[tuple[str, list[str], str | None]] = [
    (
        "ruff (lint)",
        [sys.executable, "-m", "ruff", "check", "src", "tests", "scripts", ".cataforge"],
        "ruff",
    ),
    (
        "ruff (format check)",
        [
            sys.executable,
            "-m",
            "ruff",
            "format",
            "--check",
            "src",
            "tests",
            "scripts",
            ".cataforge",
        ],
        "ruff",
    ),
    (
        "no design-phase residue",
        [sys.executable, str(REPO_ROOT / "scripts" / "checks" / "check_no_design_residue.py")],
        None,
    ),
    (
        "no language coupling",
        [sys.executable, str(REPO_ROOT / "scripts" / "checks" / "check_no_language_coupling.py")],
        None,
    ),
    (
        "doc structure hygiene",
        [sys.executable, str(REPO_ROOT / "scripts" / "checks" / "check_doc_structure.py")],
        None,
    ),
    (
        "prompt ↔ CLI verb drift",
        [sys.executable, str(REPO_ROOT / "scripts" / "checks" / "check_prompt_cli_drift.py")],
        None,
    ),
    (
        "layered dependency direction",
        [sys.executable, str(REPO_ROOT / "scripts" / "checks" / "check_layer_dependencies.py")],
        None,
    ),
    # import-linter's declarative layer contract ([tool.importlinter] in
    # pyproject) as a second, belt-and-braces architecture gate alongside the
    # custom check above. CI runs the same `lint-imports`; skipped gracefully
    # when import-linter isn't installed (clone without [dev] extras).
    (
        "import-linter contract",
        [sys.executable, "-m", "importlinter.cli", "lint-imports"],
        "importlinter",
    ),
    (
        "no QueryBoolean == True",
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "checks" / "check_no_query_boolean_eq_true.py"),
        ],
        None,
    ),
    (
        "schema ↔ python mirror parity",
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "checks" / "check_schema_python_parity.py"),
        ],
        None,
    ),
    # Enforced: every src/cataforge/ subprocess.run / Popen / call must
    # either go through cataforge.utils.run_subprocess.run or carry an
    # inline `# allow-raw-subprocess: <reason>` exemption.
    (
        "no raw subprocess outside the wrapper",
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "checks" / "check_no_raw_subprocess.py"),
        ],
        None,
    ),
    (
        "no error output to stdout",
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "checks" / "check_echo_err_for_errors.py"),
        ],
        None,
    ),
    # Enforced: file I/O under src/cataforge/ relies on the process-wide
    # UTF-8 Mode contract; no redundant `encoding="utf-8"` on open / read_text
    # / write_text outside the boundary layer.
    (
        "no redundant encoding on file I/O",
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "checks" / "check_no_redundant_encoding.py"),
        ],
        None,
    ),
    # KG codegen output (_generated/*_pydantic.py + subclass_axioms.ttl) is
    # checked in; regenerating from schemas/*.yaml must produce no diff. The
    # nondeterministic SHACL shapes are excluded. Skipped when linkml is absent.
    (
        "kg codegen freshness",
        [sys.executable, str(REPO_ROOT / "scripts" / "checks" / "check_codegen_fresh.py")],
        None,
    ),
    # Repo-content anti-rot guards CI runs in its guards bash block but
    # pre-commit's no-arg hooks don't: deterministic, env-independent reads of
    # checked-in files. Omitting them let release-time CHANGELOG / version drift
    # (link table, doc versions) pass local and fail CI. The git-diff guards
    # (changelog fragments, dev-branch refs) stay CI-only — they depend on
    # BASE_REF and behave differently outside a PR context.
    (
        "skill count parity",
        [sys.executable, str(REPO_ROOT / "scripts" / "checks" / "check_skill_count.py")],
        None,
    ),
    (
        "CHANGELOG link table",
        [sys.executable, str(REPO_ROOT / "scripts" / "checks" / "check_changelog_link_table.py")],
        None,
    ),
    (
        "doc version stamps",
        [sys.executable, str(REPO_ROOT / "scripts" / "checks" / "check_doc_versions.py")],
        None,
    ),
    (
        "profile.yaml keys",
        [sys.executable, str(REPO_ROOT / "scripts" / "checks" / "check_profile_yaml_keys.py")],
        None,
    ),
    (
        "hooks.yaml schema",
        [sys.executable, str(REPO_ROOT / "scripts" / "checks" / "check_hooks_yaml_schema.py")],
        None,
    ),
    # mypy --strict over the whole tree: CI gates it (`[tool.mypy] strict`),
    # pre-commit does not, so without it here a type error passes local but
    # fails CI. `--no-incremental` matches the CI invocation exactly.
    (
        "mypy (strict)",
        [sys.executable, "-m", "mypy", "src/cataforge", "--no-incremental"],
        "mypy",
    ),
    # `uv lock --check` is not in .pre-commit-config.yaml (it needs the uv
    # binary, which is not pip-installable), but CI runs it and a stale
    # lockfile fails the build. Keep it in this wrapper to close the loop.
    # Skipped gracefully when uv is not on PATH so the wrapper still works
    # on Python-only contributor setups.
    ("uv lockfile freshness", ["uv", "lock", "--check"], None),
]


def main() -> int:
    # UTF-8 stdio so Chinese diagnostic messages do not crash on
    # Windows cp1252 terminals.
    for _stream_name in ("stdout", "stderr"):
        _stream = getattr(sys, _stream_name)
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="replace")

    failed: list[str] = []
    skipped: list[str] = []
    for label, argv, requires_module in CHECKS:
        print(f"\n=== {label} ===", flush=True)
        if requires_module is not None and importlib.util.find_spec(requires_module) is None:
            print(
                f"  (skipped — `{requires_module}` not importable; install dev "
                f"extras or rely on CI to cover this check)",
                flush=True,
            )
            skipped.append(label)
            continue
        try:
            result = subprocess.run(argv, cwd=REPO_ROOT, check=False)  # noqa: S603
        except FileNotFoundError:
            print(
                f"  (skipped — `{argv[0]}` not on PATH; install it or run "
                f"via CI to cover this check)",
                flush=True,
            )
            skipped.append(label)
            continue
        if result.returncode != 0:
            failed.append(label)

    print("\n" + "=" * 60)
    if failed:
        print(f"FAIL: {len(failed)} check(s) failed:", file=sys.stderr)
        for label in failed:
            print(f"  - {label}", file=sys.stderr)
        return 1
    ran = len(CHECKS) - len(skipped)
    suffix = f" ({len(skipped)} skipped)" if skipped else ""
    print(f"OK: {ran} checks passed{suffix}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
