#!/usr/bin/env python3
"""Anti-rot guard: no design-phase residue in long-term prompt assets.

`.cataforge/agents/**`, `.cataforge/skills/**` (bodies, references and
templates), `.cataforge/rules/**` and `docs/reference/**` are markdown that
either loads into the LLM context at runtime or stands as long-term repo
reference. Change-narrative — `<!-- 变更原因：... -->`, `issue #NNN`,
`v1.2.3 起`, `原方案 X 改为 Y` — belongs in PR descriptions / commit
messages / CHANGELOG, not these assets, where it bloats context and rots.

This guard blocks the regression: it scans those trees for known
design-phase markers and fails CI if any are found.

Whitelist: append `<!-- allow-design-residue: <reason> -->` to the
offending line if you have a deliberate reason (e.g. a template placeholder
that gets replaced at deploy time).
"""

from __future__ import annotations

import re
import sys

from _common import (
    REPO_ROOT,
    ensure_utf8,
    is_whitelisted_for,
    iter_asset_files,
    iter_scannable_lines,
    make_escape_hatch,
)

ensure_utf8()

SCAN_GLOBS = [
    (REPO_ROOT / ".cataforge" / "agents", "**/*.md"),
    (REPO_ROOT / ".cataforge" / "skills", "**/*.md"),
    (REPO_ROOT / ".cataforge" / "rules", "**/*.md"),
    (REPO_ROOT / "docs" / "reference", "**/*.md"),
]

# Markers that almost always indicate design-phase residue carried over
# into long-term assets. Tight by design — if you need to add another
# pattern, write a test case first.
#
# Three groups:
#   - HTML-comment markers (the original tight scope)
#   - Inline citation / version-milestone markers anchored on hard tokens
#     (`#NNN`, `vX.Y.Z 起`, …) so they skip state-machine narration
#   - Chinese 对比叙事 anchors — residue-specific phrasings ("原方案 X 改
#     为 Y", "收紧自 N", "不再使用 X") that never legitimately describe
#     current state; the bare verb 改为 is intentionally absent (it fires
#     on "由 draft 改为 approved" and teaching examples)
FORBIDDEN: list[tuple[str, re.Pattern[str]]] = [
    ("变更原因", re.compile(r"<!--\s*变更原因[：:]")),
    ("diagnostic-id", re.compile(r"<!--\s*diagnostic\s*#\d+", re.IGNORECASE)),
    ("TODO-marker", re.compile(r"<!--\s*TODO\s*[:：]")),
    ("FIXME-marker", re.compile(r"<!--\s*FIXME\s*[:：]")),
    ("prompt-version", re.compile(r"<!--\s*prompt-version", re.IGNORECASE)),
    ("last-regenerated", re.compile(r"<!--\s*last-regenerated", re.IGNORECASE)),
    ("issue-citation", re.compile(r"\bissue\s*#\s*\d+", re.IGNORECASE)),
    ("PR-citation", re.compile(r"(?:^|[\s（(])PR\s*#\s*\d+")),
    ("closes-fixes", re.compile(r"\b(?:closes|fixes|closeout)\s*#?\s*\d+", re.IGNORECASE)),
    ("landed-in", re.compile(r"\blanded\s+in\b", re.IGNORECASE)),
    ("version-milestone", re.compile(r"v\d+\.\d+\.\d+\s*(?:起|新增|前后)")),
    ("pre-version", re.compile(r"\bpre-v\d+\.\d+\.\d+")),
    ("narrative-原方案", re.compile(r"原方案")),
    ("narrative-收紧自", re.compile(r"收紧自")),
    ("narrative-不再使用", re.compile(r"不再[使采](?:用)")),
    ("narrative-重命名为", re.compile(r"重命名为")),
]

ALLOW = make_escape_hatch("allow-design-residue")


def main() -> int:
    fails: list[str] = []
    scanned = 0
    for path in iter_asset_files(SCAN_GLOBS):
        scanned += 1
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in iter_scannable_lines(text):
            if is_whitelisted_for(line, ALLOW):
                continue
            for label, pattern in FORBIDDEN:
                if pattern.search(line):
                    rel = path.relative_to(REPO_ROOT)
                    fails.append(f"{rel}:{lineno}: [{label}] {line.strip()}")

    if fails:
        print(
            "Anti-rot: design-phase residue in long-term prompt assets",
            file=sys.stderr,
        )
        for f in fails:
            print(f"  {f}", file=sys.stderr)
        print(
            "\nFix: this narrative is loaded into LLM context at runtime or "
            "stands as long-term reference. Move design rationale to the PR "
            "description or commit message; remove it from the asset.",
            file=sys.stderr,
        )
        return 1

    print(f"OK: scanned {scanned} files, no design-phase residue")
    return 0


if __name__ == "__main__":
    sys.exit(main())
