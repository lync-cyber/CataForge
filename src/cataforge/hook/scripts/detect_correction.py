"""PostToolUse Hook: Detect option-override corrections from AskUserQuestion.

Matcher: AskUserQuestion
Never blocks (exit 0).
"""

from __future__ import annotations

import sys
from typing import Any

from cataforge.core.corrections import record_correction
from cataforge.core.paths import find_project_root
from cataforge.hook.base import hook_main, matches_capability, read_hook_input


def _recommended_label(options: list[Any]) -> str | None:
    if not isinstance(options, list):
        return None
    for opt in options:
        if not isinstance(opt, dict):
            continue
        label = opt.get("label", "") or ""
        if "(Recommended)" in label or "(推荐)" in label:
            return label
    return None


def _resolve_agent_id(data: dict[str, Any]) -> str:
    return data.get("agent_id") or "orchestrator"


def _extract_answers(tool_response: object) -> dict[str, Any]:
    if not isinstance(tool_response, dict):
        return {}
    answers = tool_response.get("answers")
    if isinstance(answers, dict):
        return answers
    return (
        tool_response if all(isinstance(v, str) for v in tool_response.values()) else {}
    )


@hook_main
def main() -> None:
    data = read_hook_input()

    if not data or not matches_capability(data, "user_question"):
        sys.exit(0)

    tool_input = data.get("tool_input") or {}
    tool_response = data.get("tool_response") or {}
    questions = tool_input.get("questions") or []
    if not isinstance(questions, list):
        sys.exit(0)

    answers = _extract_answers(tool_response)
    if not answers:
        sys.exit(0)

    project_root = find_project_root()
    agent_id = _resolve_agent_id(data)
    phase = str(data.get("phase") or tool_input.get("phase") or "unknown")

    for q in questions:
        if not isinstance(q, dict):
            continue
        question_text = q.get("question", "") or ""
        options = q.get("options") or []
        recommended = _recommended_label(options)
        if not recommended:
            continue

        chosen = answers.get(question_text)
        if not chosen or chosen == recommended:
            continue

        print(
            f"[HOOK-INFO] correction | option-override | {question_text[:60]}",
            file=sys.stderr,
        )

        try:
            record_correction(
                project_root,
                trigger="option-override",
                agent=agent_id,
                phase=phase,
                question=question_text,
                baseline=recommended,
                actual=str(chosen),
                deviation="preference",
            )
        except (ValueError, OSError) as e:
            print(f"[HOOK-WARN] {e}", file=sys.stderr)

    sys.exit(0)


if __name__ == "__main__":
    main()
