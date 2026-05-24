"""PostToolUse Hook: Auto-ingest edited markdown back into the KG.

Matcher: Edit|Write on ``docs/**/*.md``

When the user (or an LLM) modifies a markdown file under ``docs/``, this
hook quietly re-ingests the file so the KG stays the source of truth
without the user having to remember ``cataforge kg ingest --file ...``.

Quiet-fail by design (R-16):

* runs through ``cataforge kg ingest --auto --file <path>`` which
  applies the kg-wins strategy and writes any disagreement to
  ``docs/.doc-graph/conflicts/`` instead of bouncing the edit
* swallows every non-zero exit so a transient ingest error never
  blocks the LLM mid-task — ``cataforge doctor`` surfaces accumulated
  conflicts after the fact
* skips files outside the project ``docs/`` tree (templates, snapshots,
  test fixtures) so an Edit deep in ``.cataforge/`` doesn't trigger ingest

Always exits 0.
"""

from __future__ import annotations

import contextlib
import os
import subprocess
import sys

from cataforge.hook.base import hook_main, matches_script_filters, read_hook_input


def _is_markdown_under_docs(file_path: str) -> bool:
    """True for project ``docs/**/*.md`` files; False for everything else."""
    norm = file_path.replace("\\", "/")
    if not norm.endswith(".md"):
        return False
    # ``.doc-graph`` lives under docs/ but is the KG store itself; ingesting
    # the store back into itself would deadlock the merge.
    if "/.doc-graph/" in norm:
        return False
    # Templates and skill assets are not consumer-edited docs.
    if "/.cataforge/" in norm:
        return False
    return "/docs/" in norm or norm.startswith("docs/")


@hook_main
def main() -> None:
    data = read_hook_input()

    # v2 schema opt-in: honour matcher_file_pattern etc. from hooks.yaml
    # before doing any work. Scripts keep backwards compatibility — if the
    # user hasn't added filters, this always returns True.
    if not matches_script_filters(data, "kg_auto_ingest"):
        sys.exit(0)

    file_path = (data.get("tool_input") or {}).get("file_path")
    if not file_path:
        file_path = (data.get("tool_input") or {}).get("path")
    if not file_path:
        sys.exit(0)

    if not _is_markdown_under_docs(file_path):
        sys.exit(0)

    if not os.path.isfile(file_path):
        sys.exit(0)

    # Subprocess so a malformed markdown / KG state can't drag the hook
    # runtime down. 30-second timeout matches lint_format — same risk
    # class. Quiet-fail per R-16: the user discovers issues via
    # `cataforge doctor` or `cataforge kg conflicts`.
    with contextlib.suppress(
        FileNotFoundError, subprocess.TimeoutExpired, Exception,
    ):
        subprocess.run(
            [
                sys.executable, "-m", "cataforge.cli.main",
                "kg", "ingest", "--auto", "--file", file_path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

    sys.exit(0)


if __name__ == "__main__":
    main()
