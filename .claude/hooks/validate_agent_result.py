#!/usr/bin/env python3
"""PostToolUse Hook: Validate <agent-result> schema from Agent tool returns.

Matcher: Agent
Warning-only (exit 0) — agent-dispatch already has fallback logic.

Test:
  echo '{"tool_name":"Agent","tool_result":"<agent-result><status>completed</status><outputs>f.md</outputs><summary>done</summary></agent-result>"}' | python .claude/hooks/validate_agent_result.py
  Expected: exit 0, no warnings
"""

import json
import os
import re
import sys

# Event logger integration
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
try:
    from event_logger import append_event as _log_event
except ImportError:
    _log_event = None

# Load status codes from canonical schema (single source of truth)
_schema_path = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "schemas",
    "agent-result.schema.json",
)
try:
    with open(_schema_path, "r", encoding="utf-8") as _f:
        _schema = json.load(_f)
    VALID_STATUSES = set(_schema["properties"]["status"]["enum"])
except (OSError, KeyError, json.JSONDecodeError):
    # Fallback if schema file unavailable
    VALID_STATUSES = {
        "completed",
        "needs_input",
        "blocked",
        "approved",
        "approved_with_notes",
        "needs_revision",
        "rolled-back",
    }


def warn(msg):
    print(f"[WARN] agent-result schema: {msg}", file=sys.stderr)


def main():
    try:
        data = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    if not data or data.get("tool_name") != "Agent":
        sys.exit(0)

    # Try multiple possible field names for the result
    result = data.get("tool_result") or data.get("result") or data.get("tool_output")
    if not result:
        if os.environ.get("CATAFORGE_HOOK_DEBUG") == "1":
            debug_path = os.path.join(
                os.path.dirname(__file__), "agent-result-debug.log"
            )
            with open(debug_path, "a", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.write("\n")
        sys.exit(0)

    result = str(result)

    # 1. Check <agent-result> tag
    if "<agent-result>" not in result:
        warn("missing <agent-result> tag")
        sys.exit(0)

    # 2. Check required fields
    for field in ("status", "outputs", "summary"):
        if not re.search(rf"<{field}>[\s\S]*?</{field}>", result):
            warn(f"missing <{field}> field")

    # 3. Check status enum
    m = re.search(r"<status>\s*(.*?)\s*</status>", result)
    if m:
        status = m.group(1).strip()
        if status not in VALID_STATUSES:
            warn(
                f"invalid status='{status}', expected: {'|'.join(sorted(VALID_STATUSES))}"
            )

        # 4. needs_input requires <questions>, <completed-steps>, <resume-guidance>
        if status == "needs_input":
            for field in ("questions", "completed-steps", "resume-guidance"):
                if f"<{field}>" not in result:
                    warn(f"status=needs_input but missing <{field}>")

        # 5. Log agent_return event
        if _log_event:
            outputs_m = re.search(r"<outputs>\s*(.*?)\s*</outputs>", result, re.DOTALL)
            ref = outputs_m.group(1).strip() if outputs_m else None
            try:
                _log_event(
                    event="agent_return",
                    phase=os.environ.get("CATAFORGE_CURRENT_PHASE", "unknown"),
                    detail=f"Agent returned status={status}",
                    status=status if status in VALID_STATUSES else None,
                    ref=ref,
                )
            except Exception:
                pass  # Never block on logging failure

    sys.exit(0)


if __name__ == "__main__":
    main()
