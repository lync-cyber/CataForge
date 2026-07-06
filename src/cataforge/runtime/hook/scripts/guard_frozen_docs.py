"""PreToolUse Hook: block edits to frozen upstream docs under the unattended loop.

Active only when the building-loop set ``CATAFORGE_UNATTENDED``; a no-op in
normal interactive sessions. The loop must never touch the frozen planning docs
(PRD / ARCH / UI-SPEC / DEV-PLAN, plus the agile-prototype BRIEF) — those are the
frozen task sources, and planning stays a human daytime activity. §5 of the
proposal requires this at the *tool* layer, not PROMPT text alone (an autonomous
agent can ignore prose it doesn't take to heart).

Best-effort path match against the ``docs/{type}/`` convention — a speed-bump,
not a sandbox; the real guarantee is the sandbox + human morning review.

Test:
  echo '{"tool_name":"Edit","tool_input":{"file_path":"docs/dev-plan/dev-plan.md"}}' \
    | CATAFORGE_UNATTENDED=1 python -m cataforge.runtime.hook.scripts.guard_frozen_docs
  Expected: exit 2, stderr shows block reason
"""

from __future__ import annotations

import os
import re
import sys

from cataforge.runtime.hook.base import matches_capability, read_hook_input

# A path is a frozen upstream doc when it sits under docs/<type>/ or is the flat
# docs/<type>(-lite).md, for the four standard planning doc types plus the
# agile-prototype brief. Anchored on a path boundary so docs/dev-planner/ or
# docs/brief-notes.md are NOT false-matched.
_FROZEN_DOC_RE = re.compile(
    r"(?:^|/)docs/(?:prd|arch|ui-spec|dev-plan|brief)(?:-lite)?(?:/|\.md|$)"
)


def _block(path: str) -> None:
    print(
        "BLOCKED: 无人值守禁止修改冻结上游文档 (PRD/ARCH/UI-SPEC/DEV-PLAN/BRIEF)",
        file=sys.stderr,
    )
    print(f"Path: {path}", file=sys.stderr)
    print("Suggestion: 无人循环只 building；planning 是冻结质量锚，留人工白天修改", file=sys.stderr)
    sys.exit(2)


def main() -> None:
    if os.environ.get("CATAFORGE_UNATTENDED") != "1":
        sys.exit(0)

    data = read_hook_input()
    if not matches_capability(data, "file_edit"):
        sys.exit(0)

    tool_input = data.get("tool_input") or {}
    raw = tool_input.get("file_path") or tool_input.get("path") or ""
    if not raw:
        sys.exit(0)

    if _FROZEN_DOC_RE.search(str(raw).replace("\\", "/")):
        _block(str(raw))

    sys.exit(0)


if __name__ == "__main__":
    main()
