"""PostToolUse Hook: Validate <agent-result> schema from Agent tool returns.

Matcher: Agent
Warning-only (exit 0) — agent-dispatch already has fallback logic.
"""

import json
import re
import sys

from cataforge.core.paths import ProjectPaths
from cataforge.hook.base import (
    hook_main,
    matches_capability,
    matches_script_filters,
    read_hook_input,
)

_schemas_dir = ProjectPaths().schemas_dir
_schema_path = _schemas_dir / "agent-result.schema.json"
try:
    _schema = json.loads(_schema_path.read_text(encoding="utf-8"))
    VALID_STATUSES: set[str] = set(_schema["properties"]["status"]["enum"])
except (OSError, KeyError, json.JSONDecodeError):
    VALID_STATUSES = {
        "completed",
        "needs_input",
        "blocked",
        "approved",
        "approved_with_notes",
        "needs_revision",
        "rolled-back",
    }


def _warn(msg: str) -> None:
    print(f"[WARN] agent-result schema: {msg}", file=sys.stderr)


@hook_main
def main() -> None:
    data = read_hook_input()

    if not data or not matches_capability(data, "agent_dispatch"):
        sys.exit(0)

    if not matches_script_filters(data, "validate_agent_result"):
        sys.exit(0)

    result = data.get("tool_result") or data.get("result") or data.get("tool_output")
    if not result:
        sys.exit(0)

    result = str(result)

    if "<agent-result>" not in result:
        _warn("missing <agent-result> tag")
        sys.exit(0)

    for field in ("status", "outputs", "summary"):
        if not re.search(rf"<{field}>[\s\S]*?</{field}>", result):
            _warn(f"missing <{field}> field")

    m = re.search(r"<status>\s*(.*?)\s*</status>", result)
    if m:
        status = m.group(1).strip()
        if status not in VALID_STATUSES:
            _warn(
                f"invalid status='{status}', expected: {'|'.join(sorted(VALID_STATUSES))}"
            )

        if status == "needs_input":
            for field in ("questions", "completed-steps", "resume-guidance"):
                if f"<{field}>" not in result:
                    _warn(f"status=needs_input but missing <{field}>")

    sys.exit(0)


if __name__ == "__main__":
    main()
