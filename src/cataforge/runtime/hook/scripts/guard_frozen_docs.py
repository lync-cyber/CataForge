"""PreToolUse Hook: block edits to frozen upstream docs under the unattended loop.

Active only when the building-loop set ``CATAFORGE_UNATTENDED``; a no-op in
normal interactive sessions. The loop must never touch the frozen planning docs
(PRD / ARCH / UI-SPEC / DEV-PLAN, plus the agile-prototype BRIEF) — those are the
frozen task sources, and planning stays a human daytime activity. §5 of the
proposal requires this at the *tool* layer, not PROMPT text alone (an autonomous
agent can ignore prose it doesn't take to heart).

One mode-aware carve-out: under ``context.mode = markdown`` the doc itself is
the task-status source of truth (no graph backend), so a status-only Edit to a
task-carrying doc (dev-plan / brief) is the loop's only legal way to mark a card
done — that passes; every other change still blocks. Under ``graph`` status goes
through ``cataforge context update`` (not file_edit), so every file edit blocks.

Best-effort path match against the ``docs/{type}/`` convention — a speed-bump,
not a sandbox; the real guarantee is the sandbox + human morning review.

Test:
  echo '{"tool_name":"Edit","tool_input":{"file_path":"docs/dev-plan/dev-plan.md"}}' \
    | CATAFORGE_UNATTENDED=1 python -m cataforge.runtime.hook.scripts.guard_frozen_docs
  Expected: exit 2, stderr shows block reason
"""

from __future__ import annotations

import difflib
import os
import re
import sys
from pathlib import Path
from typing import Any

from cataforge.runtime.hook.base import (
    extract_edited_paths,
    matches_capability,
    read_hook_input,
)

# A path is a frozen upstream doc when it sits under docs/<type>/ or is the flat
# docs/<type>(-lite).md, for the four standard planning doc types plus the
# agile-prototype brief. Anchored on a path boundary so docs/dev-planner/ or
# docs/brief-notes.md are NOT false-matched. Case-insensitive: Windows / macOS
# default filesystems resolve docs/BRIEF.MD to the same file as docs/brief.md.
_FROZEN_DOC_RE = re.compile(
    r"(?:^|/)docs/(?:prd|arch|ui-spec|dev-plan|brief)(?:-lite)?(?:/|\.md|$)",
    re.IGNORECASE,
)

# Only these docs carry per-task execution status; the markdown-mode status
# carve-out never applies to PRD / ARCH / UI-SPEC.
_TASK_DOC_RE = re.compile(
    r"(?:^|/)docs/(?:dev-plan|brief)(?:-lite)?(?:/|\.md|$)",
    re.IGNORECASE,
)

# ``- status: done`` / ``- **status**: done`` style task-card field line.
_STATUS_LINE_RE = re.compile(r"^\s*[-*]\s*\**status\**\s*[:：]", re.IGNORECASE)

# A rewritten table cell longer than a status token is content, not state.
_MAX_STATUS_CELL_LEN = 32


def _status_pair_ok(old_line: str, new_line: str) -> bool:
    if _STATUS_LINE_RE.match(old_line) and _STATUS_LINE_RE.match(new_line):
        return True
    # Sprint-table row: exactly one cell changed, to a short status-like value.
    if old_line.lstrip().startswith("|") and new_line.lstrip().startswith("|"):
        old_cells = [c.strip() for c in old_line.split("|")]
        new_cells = [c.strip() for c in new_line.split("|")]
        if len(old_cells) != len(new_cells):
            return False
        diff = [(o, n) for o, n in zip(old_cells, new_cells, strict=True) if o != n]
        return len(diff) == 1 and len(diff[0][1]) <= _MAX_STATUS_CELL_LEN
    return False


def _is_status_only_change(old: str, new: str) -> bool:
    """True when *old*→*new* only rewrites task-status lines / cells in place."""
    old_lines = old.splitlines()
    new_lines = new.splitlines()
    matcher = difflib.SequenceMatcher(a=old_lines, b=new_lines, autojunk=False)
    changed = False
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        # Inserting / deleting lines is never a bare status transition.
        if tag != "replace" or (i2 - i1) != (j2 - j1):
            return False
        for o, n in zip(old_lines[i1:i2], new_lines[j1:j2], strict=True):
            if not _status_pair_ok(o, n):
                return False
        changed = True
    return changed


def _markdown_status_edit_allowed(data: dict[str, Any], norm_path: str) -> bool:
    if not _TASK_DOC_RE.search(norm_path):
        return False
    tool_input = data.get("tool_input") or {}
    old = tool_input.get("old_string")
    new = tool_input.get("new_string")
    # Only surgical Edits qualify — a full-file Write for a one-line status
    # flip is indistinguishable from a rewrite, so Write stays blocked.
    if not isinstance(old, str) or not isinstance(new, str):
        return False
    # Lazy imports: mode resolution reads framework.json; keep the common
    # (non-frozen-path) hook invocation import-light.
    from cataforge.core.paths import find_project_root_or_none

    cwd = data.get("cwd")
    start = Path(cwd) if isinstance(cwd, str) and cwd else None
    root = find_project_root_or_none(start)
    if root is None:
        return False  # fail-closed: unknown project → keep blocking

    from cataforge.domain.kg._dispatch import context_mode

    if context_mode(root) != "markdown":
        return False
    return _is_status_only_change(old, new)


def _block(path: str) -> None:
    print(
        "BLOCKED: 无人值守禁止修改冻结上游文档 (PRD/ARCH/UI-SPEC/DEV-PLAN/BRIEF)",
        file=sys.stderr,
    )
    print(f"Path: {path}", file=sys.stderr)
    print(
        "Suggestion: 无人循环只 building；planning 是冻结质量锚，留人工白天修改。"
        "任务卡 status：graph 模式走 cataforge context update；"
        "markdown 模式仅放行 status 字段/状态表单元格的最小 Edit",
        file=sys.stderr,
    )
    sys.exit(2)


def main() -> None:
    if os.environ.get("CATAFORGE_UNATTENDED") != "1":
        sys.exit(0)

    data = read_hook_input()
    if not matches_capability(data, "file_edit"):
        sys.exit(0)

    # apply_patch payloads carry no old_string/new_string, so the markdown
    # status carve-out cannot verify a status-only diff there — fail-closed.
    for raw in extract_edited_paths(data):
        norm = raw.replace("\\", "/")
        if _FROZEN_DOC_RE.search(norm):
            if _markdown_status_edit_allowed(data, norm):
                continue
            _block(raw)

    sys.exit(0)


if __name__ == "__main__":
    main()
