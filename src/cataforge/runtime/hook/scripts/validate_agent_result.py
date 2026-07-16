"""PostToolUse Hook: Validate <agent-result> schema from Agent tool returns.

Matcher: Agent
Warning-only (exit 0) — agent-dispatch already has fallback logic.
"""

import re
import sys

from cataforge.core.errors import ConfigError
from cataforge.core.io import read_json
from cataforge.core.paths import ProjectPaths
from cataforge.core.types import AgentStatus
from cataforge.runtime.hook.base import (
    dispatch_result,
    hook_main,
    matches_capability,
    matches_script_filters,
    read_hook_input,
)


def _load_valid_statuses() -> set[str]:
    schemas_dir = ProjectPaths().schemas_dir
    schema_path = schemas_dir / "agent-result.schema.json"
    try:
        schema = read_json(schema_path)
        return set(schema["properties"]["status"]["enum"])
    except (ConfigError, KeyError):
        # Fallback derived from the AgentStatus enum (SSOT); kept in parity
        # with the schema JSON by the schema-python-parity guard.
        return {s.value for s in AgentStatus}


def _warn(msg: str) -> None:
    print(f"[WARN] agent-result schema: {msg}", file=sys.stderr)


@hook_main
def main() -> None:
    valid_statuses = _load_valid_statuses()
    data = read_hook_input()

    if not data or not matches_capability(data, "agent_dispatch"):
        sys.exit(0)

    if not matches_script_filters(data, "validate_agent_result"):
        sys.exit(0)

    result = dispatch_result(data)
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
        if status not in valid_statuses:
            _warn(f"invalid status='{status}', expected: {'|'.join(sorted(valid_statuses))}")

        if status == "needs_input":
            for field in ("questions", "completed-steps", "resume-guidance"):
                if f"<{field}>" not in result:
                    _warn(f"status=needs_input but missing <{field}>")

    sys.exit(0)


if __name__ == "__main__":
    main()
