#!/usr/bin/env python3
"""Anti-rot guard: markdown links in deployed prompt assets resolve.

`.cataforge/agents/**/AGENT.md`, `.cataforge/skills/**/SKILL.md`, the
`*PROTOCOLS*.md`, and per-skill `references/*.md` are deployed verbatim
(junction / symlink on each platform). A relative markdown link inside them
must point at a file that exists in the `.cataforge/` tree under that
layout, or a reader (human or LLM following the link) lands on nothing.

Link offloading (moving language detail into `references/`) is only safe if
the back-links stay valid; nothing checked that until now. This guard
resolves every relative `[text](path)` target and fails on a dangling one.

Resolution:
  - External (`http(s)://`, `mailto:`) and pure-anchor (`#section`) links
    are skipped.
  - A target starting with a repo-root prefix (`.cataforge/`, `docs/`, …)
    resolves from the repository root.
  - Any other target resolves relative to the linking file's directory.
  - A trailing `#anchor` and an optional `"title"` are stripped first.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from _common import (
    REPO_ROOT,
    ensure_utf8,
    iter_asset_files,
    iter_scannable_lines,
)

ensure_utf8()

SCAN_GLOBS = [
    (REPO_ROOT / ".cataforge" / "agents", "**/AGENT.md"),
    (REPO_ROOT / ".cataforge" / "agents", "**/*PROTOCOLS*.md"),
    (REPO_ROOT / ".cataforge" / "skills", "**/SKILL.md"),
    (REPO_ROOT / ".cataforge" / "skills", "**/references/*.md"),
]

LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
REPO_ROOT_PREFIXES = (".cataforge/", "docs/", ".github/", "src/", "tests/", "scripts/")


def link_target_path(raw: str) -> Path | None:
    """Return the path for a markdown link target — absolute when repo-root
    anchored, relative otherwise (the caller resolves it against the file
    dir) — or None for external / anchor-only links."""
    if raw.startswith(("http://", "https://", "mailto:")) or raw.startswith("#"):
        return None
    # Drop an optional `"title"` after the path, then a trailing #anchor.
    path = raw.split()[0].split("#", 1)[0].strip()
    if not path:
        return None
    if path.startswith(REPO_ROOT_PREFIXES):
        return REPO_ROOT / path
    return Path(path)


def main() -> int:
    fails: list[str] = []
    scanned = 0
    links = 0
    for path in iter_asset_files(SCAN_GLOBS):
        scanned += 1
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in iter_scannable_lines(text):
            for m in LINK.finditer(line):
                target = link_target_path(m.group(1).strip())
                if target is None:
                    continue
                links += 1
                resolved = target if target.is_absolute() else (path.parent / target)
                if not resolved.exists():
                    rel = path.relative_to(REPO_ROOT)
                    fails.append(f"{rel}:{lineno}: [{m.group(1).strip()}] → {resolved}")

    if fails:
        print("Anti-rot: dangling markdown links in deployed prompt assets", file=sys.stderr)
        for f in fails:
            print(f"  {f}", file=sys.stderr)
        print(
            "\nFix: point the link at a file that exists in the .cataforge/ "
            "tree under the deployed layout, or remove the link.",
            file=sys.stderr,
        )
        return 1

    print(f"OK: scanned {scanned} files, {links} relative links all resolve")
    return 0


if __name__ == "__main__":
    sys.exit(main())
