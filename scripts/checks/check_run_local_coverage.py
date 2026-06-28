#!/usr/bin/env python3
"""Meta-guard: every deterministic full-tree check is wired into run_local.py.

`scripts/checks/run_local.py` is the one command a contributor (or agent)
runs to match CI's static gates locally. If a new `check_*.py` lands in CI
but not in run_local, "green local" stops meaning "green CI" — exactly the
drift that lets a ruff F401 slip through to CI. This guard fails when a
check script is neither referenced by run_local nor on the documented
CI-only allowlist, and when an allowlist entry goes stale.

CI-only checks (legitimately absent from run_local because they are not a
static read of checked-in files):
  - check_changelog_fragments.py — diffs the PR against BASE_REF; behaves
    differently outside a PR context.
  - check_profile_version_tested.py — reads profile git-history age (>180
    days); a time-dependent weekly sweep, not a per-commit static gate.
"""

from __future__ import annotations

import sys

from _common import REPO_ROOT, ensure_utf8

ensure_utf8()

CHECKS_DIR = REPO_ROOT / "scripts" / "checks"
RUN_LOCAL = CHECKS_DIR / "run_local.py"

# name -> reason it is legitimately CI-only (not a static checked-in-file scan).
CI_ONLY: dict[str, str] = {
    "check_changelog_fragments.py": "diffs the PR against BASE_REF — PR-context dependent",
    "check_profile_version_tested.py": "git-history age (>180d) — time-dependent weekly sweep",
}


def main() -> int:
    run_local_text = RUN_LOCAL.read_text(encoding="utf-8")
    check_scripts = sorted(p.name for p in CHECKS_DIR.glob("check_*.py"))

    fails: list[str] = []
    for name in check_scripts:
        in_run_local = name in run_local_text
        in_ci_only = name in CI_ONLY
        if not in_run_local and not in_ci_only:
            fails.append(
                f"{name}: deterministic check not wired into run_local.py and "
                f"not on the CI-only allowlist — add it to run_local CHECKS, or "
                f"document a CI-only reason in this guard's CI_ONLY map"
            )
        elif in_run_local and in_ci_only:
            fails.append(
                f"{name}: on the CI-only allowlist yet also referenced by "
                f"run_local.py — drop the CI_ONLY entry (it has a local surface)"
            )

    for name in CI_ONLY:
        if not (CHECKS_DIR / name).is_file():
            fails.append(f"{name}: on the CI-only allowlist but the script no longer exists")

    if fails:
        print("Anti-rot: run_local.py coverage drift", file=sys.stderr)
        for f in fails:
            print(f"  {f}", file=sys.stderr)
        return 1

    local = [n for n in check_scripts if n not in CI_ONLY]
    print(
        f"OK: {len(local)} deterministic checks all wired into run_local.py "
        f"({len(CI_ONLY)} CI-only)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
