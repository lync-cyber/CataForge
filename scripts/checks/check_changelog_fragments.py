#!/usr/bin/env python3
"""Anti-rot guard: every PR with user-visible changes must add a changelog fragment.

Workflow (post PR #85):
  - User-visible PR → add ``changelog.d/{PR#}.{category}.md`` fragment(s)
  - Pure docs / CI / test refactor → opt out via ``[skip-changelog]``
    token in any commit message on the branch

Fails (exit 1) when:
  - The PR diff vs the base ref touches user-facing code
    (``src/`` / ``.cataforge/`` excluding test/docs/scripts) AND
  - No new ``changelog.d/*.md`` fragment was added (excluding README and
    template files) AND
  - No commit message on the branch contains ``[skip-changelog]``

Local invocation:

    BASE_REF=origin/main python scripts/checks/check_changelog_fragments.py

CI invocation: same; ``BASE_REF`` defaults to ``origin/main``. Run from
the repo root.

The diff is taken from the merge-base to the *working tree* (plus
untracked fragments), so the check gives the same verdict before and
after committing — run_local can gate a session before the commit
exists. ``--soft-missing-base`` downgrades an unresolvable base ref to
a skip (exit 0) for clones that never fetched the default branch; CI
omits the flag so a broken fetch still fails loudly.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

# Reconfigure stdio to UTF-8 so emoji / arrows / Chinese in error messages
# don't crash on Windows cp1252 terminals (mirrors cataforge.utils.common
# .ensure_utf8 inline — script must not depend on cataforge being
# importable since it runs in CI before editable install).
for _stream_name in ("stdout", "stderr"):
    _stream = getattr(sys, _stream_name)
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parents[2]
FRAGMENTS_DIR = REPO_ROOT / "changelog.d"
SKIP_TOKEN = "[skip-changelog]"

# A change to any file matching one of these prefixes is considered
# "user-visible" and therefore demands a fragment. Tightening this set
# makes the gate more permissive (fewer required fragments); loosening
# makes it stricter (more PRs need fragments).
USER_VISIBLE_PREFIXES: tuple[str, ...] = (
    "src/cataforge/",
    ".cataforge/",
    "pyproject.toml",
)

# Subpaths under USER_VISIBLE_PREFIXES that don't on their own count as
# user-visible (test fixtures, internal docs, build glue).
EXEMPT_SUBPATHS: tuple[str, ...] = (
    # nothing here yet — add as the codebase evolves
)

# Fragment files that exist for documentation / templating only and
# don't count toward the "added a fragment" check.
META_FRAGMENT_NAMES: frozenset[str] = frozenset(
    {
        "README.md",
        ".template.md.j2",
        ".gitkeep",
    }
)

# Fragment filename pattern: {PR#}.md (or any-id.md). scriv's default
# is `{timestamp}_{branch}.md`; CataForge convention is to rename to
# `{PR#}.md`. We accept both shapes — anything that's a .md file under
# changelog.d/ and not in META_FRAGMENT_NAMES counts.
FRAGMENT_RE = re.compile(r"^[^/]+\.md$")


def _git(*args: str) -> str:
    """Run a git command; return stripped stdout. Raises on non-zero."""
    result = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return result.stdout.strip()


def _changed_files(merge_base: str) -> list[str]:
    """Return relative posix paths changed from *merge_base* to the working
    tree — committed, staged and unstaged alike, so the verdict is the same
    before and after ``git commit``."""
    raw = _git("diff", "--name-only", merge_base)
    return [line for line in raw.splitlines() if line]


def _added_files(merge_base: str) -> list[str]:
    """Return relative posix paths newly added from *merge_base* to the
    working tree, plus untracked files under ``changelog.d/`` — a fragment
    written but not yet ``git add``-ed still counts."""
    raw = _git("diff", "--name-only", "--diff-filter=A", merge_base)
    added = [line for line in raw.splitlines() if line]
    untracked = _git("ls-files", "--others", "--exclude-standard", "--", "changelog.d")
    added.extend(line for line in untracked.splitlines() if line)
    return added


def _commit_messages(base_ref: str) -> list[str]:
    """Return commit messages on the branch since *base_ref*."""
    raw = _git("log", "--format=%B", f"{base_ref}..HEAD")
    return raw.splitlines() if raw else []


def _is_user_visible(path: str) -> bool:
    p = path.replace("\\", "/")
    if not any(p.startswith(prefix) for prefix in USER_VISIBLE_PREFIXES):
        return False
    return not any(p.startswith(exempt) for exempt in EXEMPT_SUBPATHS)


def _is_real_fragment(path: str) -> bool:
    p = Path(path.replace("\\", "/"))
    if p.parts[:1] != ("changelog.d",):
        return False
    if p.name in META_FRAGMENT_NAMES:
        return False
    return bool(FRAGMENT_RE.match(p.name))


def main() -> int:
    base_ref = os.environ.get("BASE_REF", "origin/main")
    soft_missing_base = "--soft-missing-base" in sys.argv[1:]

    # Tolerate detached / shallow CI checkouts where the base ref is
    # missing — surface the failure clearly rather than letting `git
    # diff` crash with a confusing error.
    try:
        _git("rev-parse", "--verify", base_ref)
        merge_base = _git("merge-base", base_ref, "HEAD")
    except subprocess.CalledProcessError:
        if soft_missing_base:
            print(f"SKIP: base ref {base_ref!r} not resolvable locally — CI will cover this check.")
            return 0
        print(
            f"ERROR: base ref {base_ref!r} not resolvable; "
            f"in CI ensure `git fetch origin {base_ref}` ran first.",
            file=sys.stderr,
        )
        return 1

    try:
        changed = _changed_files(merge_base)
    except subprocess.CalledProcessError as exc:
        print(f"ERROR: git diff failed: {exc.stderr}", file=sys.stderr)
        return 1

    if not changed:
        print(f"OK: no files changed vs {base_ref} — nothing to check.")
        return 0

    user_visible = [f for f in changed if _is_user_visible(f)]
    if not user_visible:
        print(
            f"OK: {len(changed)} file(s) changed but none are user-visible "
            f"(touched paths exempt from changelog requirement)."
        )
        return 0

    # Skip-token short-circuit.
    messages = _commit_messages(base_ref)
    if any(SKIP_TOKEN in msg for msg in messages):
        print(
            f"OK: {SKIP_TOKEN} found in commit message(s) — changelog fragment requirement waived."
        )
        return 0

    added_fragments = [f for f in _added_files(merge_base) if _is_real_fragment(f)]
    if added_fragments:
        print(
            f"OK: {len(added_fragments)} changelog fragment(s) added: " + ", ".join(added_fragments)
        )
        return 0

    # Fail — user-visible changes without fragment or skip token.
    print("FAIL: user-visible changes require a changelog fragment.", file=sys.stderr)
    print("", file=sys.stderr)
    print(
        f"This PR touches {len(user_visible)} user-visible file(s) under "
        f"{', '.join(USER_VISIBLE_PREFIXES)}",
        file=sys.stderr,
    )
    print(
        "but did not add any new changelog.d/*.md fragment.",
        file=sys.stderr,
    )
    print("", file=sys.stderr)
    print("Fix one of:", file=sys.stderr)
    print(
        "  1. Add a fragment: changelog.d/{PR#}.md "
        "(content uses ### Added / ### Changed / ### Fixed sections)",
        file=sys.stderr,
    )
    print(
        "     (see changelog.d/README.md for the format)",
        file=sys.stderr,
    )
    print(
        f"  2. Add {SKIP_TOKEN} to any commit message on this branch "
        f"(for pure refactor / CI-only / docs PRs)",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
