#!/usr/bin/env python3
"""Anti-rot guard: forbid vague marketing adverbs in user-facing docs.

The doc style guide bans words that mean "obviously / easily / just" — both
because they convey no information to a stuck reader and because they lend
docs a sales-deck tone.

Banned (Chinese):  一键 / 智能(?!体) / 只需 / 最简单 / 轻松
Banned (English):  simply / just / obviously / easily

Scope:
    - README.md
    - docs/**/*.md
    - .cataforge/skills/**/SKILL.md
    - .cataforge/agents/**/AGENT.md

Whitelist:
    - "智能体" (legitimate technical term, exempted by negative lookahead)
    - Lines containing the marker "<!-- allow-marketing-words: ... -->"
      (escape hatch for quotation / historical reference)

Exit:
    0 — clean
    1 — at least one violation
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Reconfigure stdio to UTF-8 so Chinese characters in error messages don't
# crash on Windows cp1252 terminals. Inline (rather than importing
# cataforge.utils.common.ensure_utf8_stdio) so this script works in CI
# before the editable install runs.
for _stream_name in ("stdout", "stderr"):
    _stream = getattr(sys, _stream_name)
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parents[2]

SCAN_GLOBS: list[tuple[Path, str]] = [
    (REPO_ROOT, "README.md"),
    (REPO_ROOT / "docs", "**/*.md"),
    (REPO_ROOT / ".cataforge" / "skills", "**/SKILL.md"),
    (REPO_ROOT / ".cataforge" / "agents", "**/AGENT.md"),
]

# Each pattern is paired with a short label printed on hit.
FORBIDDEN: list[tuple[str, re.Pattern[str]]] = [
    ("一键", re.compile(r"一键")),
    ("智能(non-体)", re.compile(r"智能(?!体)")),
    ("只需", re.compile(r"只需")),
    ("最简单", re.compile(r"最简单")),
    ("轻松", re.compile(r"轻松")),
    ("simply", re.compile(r"\bsimply\b", re.IGNORECASE)),
    ("just", re.compile(r"(?<![\-\w])just\s+(?!a\s+moment)", re.IGNORECASE)),
    ("obviously", re.compile(r"\bobviously\b", re.IGNORECASE)),
    ("easily", re.compile(r"\beasily\b", re.IGNORECASE)),
]

ALLOW_MARKER = re.compile(r"<!--\s*allow-marketing-words")
# A line that is *only* an HTML comment (typical for our `<!-- 变更原因：... -->`
# meta-doc annotations). Such lines explain WHY a word was removed and may
# legitimately quote the banned word; they are not user-facing prose.
PURE_COMMENT = re.compile(r"^\s*<!--.*-->\s*$")


def is_whitelisted(line: str) -> bool:
    if ALLOW_MARKER.search(line):
        return True
    return bool(PURE_COMMENT.match(line))


def iter_files() -> list[Path]:
    files: list[Path] = []
    for root, pattern in SCAN_GLOBS:
        if not root.exists():
            continue
        if root.is_file():
            files.append(root)
            continue
        files.extend(p for p in root.glob(pattern) if p.is_file())
    return files


def main() -> int:
    fails: list[str] = []
    scanned = 0
    for path in iter_files():
        scanned += 1
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if is_whitelisted(line):
                continue
            for label, pattern in FORBIDDEN:
                if pattern.search(line):
                    rel = path.relative_to(REPO_ROOT)
                    fails.append(f"{rel}:{lineno}: [{label}] {line.strip()}")

    if fails:
        print("Anti-rot: marketing-word regression in user-facing docs", file=sys.stderr)
        for f in fails:
            print(f"  {f}", file=sys.stderr)
        print(
            "\nFix: rewrite without vague adverbs. If the line is a quotation "
            "or historical reference, append '<!-- allow-marketing-words: <reason> -->' "
            "to the same line as an explicit escape hatch.",
            file=sys.stderr,
        )
        return 1

    print(f"OK: scanned {scanned} files, no marketing-word violations")
    return 0


if __name__ == "__main__":
    sys.exit(main())
