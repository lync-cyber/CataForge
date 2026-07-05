#!/usr/bin/env python3
"""Anti-rot guard: doc-producing agent cards must express the kg-first authoring flow.

A role card that produces an SDLC document (prd / arch / ui-spec / dev-plan /
test-report / deploy-spec) authors it through the ``cataforge context`` facade
and exports the human-review Markdown with ``cataforge context finalize`` — the
graph is the source of truth, the Markdown file is a derived view. A card whose
Output Contract only says "produce ``docs/<doc>.md``" has regressed to
Markdown-first authoring: it bypasses the graph backend and re-introduces the
drift the kg-first inversion removed, with no guard to catch it.

Scope — a card is in scope when its Output Contract instantiates a doc template
(``通过 context 调用 <doc_type> 模板``); review / retro / code cards carry no such
line and are ignored. Every in-scope card's Output Contract must reference
``finalize`` — the export step unique to the kg-first flow.

Escape hatch: append ``<!-- allow-doc-authoring: <reason> -->`` to a line in the
Output Contract section.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Iterator
from pathlib import Path

from _common import ensure_utf8, iter_asset_files, make_escape_hatch

ensure_utf8()

REPO_ROOT = Path(__file__).resolve().parents[2]

SCAN_GLOBS: list[tuple[Path, str]] = [
    (REPO_ROOT / ".cataforge" / "agents", "**/AGENT.md"),
]

SECTION_HEADING = re.compile(r"^##\s+(?P<title>.+?)\s*$")
OUTPUT_CONTRACT_TITLE = "Output Contract"
# Marks a doc-producing card: its Output Contract instantiates a doc template.
TEMPLATE_SIGNATURE = re.compile(r"通过\s*context\s*调用.*模板")
# The kg-first export step every doc-producing card must route through.
FINALIZE_TOKEN = re.compile(r"\bfinalize\b")
ALLOW = make_escape_hatch("allow-doc-authoring")


def _output_contract_lines(text: str) -> Iterator[str]:
    """Yield the lines inside the ``## Output Contract`` section (heading excluded)."""
    in_section = False
    for line in text.splitlines():
        heading = SECTION_HEADING.match(line)
        if heading:
            in_section = heading.group("title").strip() == OUTPUT_CONTRACT_TITLE
            continue
        if in_section:
            yield line


def main() -> int:
    fails: list[str] = []
    scanned = 0
    for path in iter_asset_files(SCAN_GLOBS):
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        section = list(_output_contract_lines(text))
        body = "\n".join(section)
        if not TEMPLATE_SIGNATURE.search(body):
            continue  # not a doc-producing card
        scanned += 1
        if any(ALLOW.search(line) for line in section):
            continue
        if not FINALIZE_TOKEN.search(body):
            rel = path.relative_to(REPO_ROOT)
            fails.append(
                f"{rel}: Output Contract instantiates a doc template but never routes "
                f"through `cataforge context finalize` — Markdown-first authoring drift"
            )

    if fails:
        print("Anti-rot: doc-producing agent cards bypass kg-first authoring", file=sys.stderr)
        for f in fails:
            print(f"  {f}", file=sys.stderr)
        print(
            "\nFix: state that the document is authored via `cataforge context` authoring "
            "and exported with `cataforge context finalize` (the graph is the source of "
            "truth, the Markdown file a derived view); or, if intentional, append "
            "`<!-- allow-doc-authoring: <reason> -->` to a line in the section.",
            file=sys.stderr,
        )
        return 1

    print(f"OK: {scanned} doc-producing agent cards route through kg-first finalize")
    return 0


if __name__ == "__main__":
    sys.exit(main())
