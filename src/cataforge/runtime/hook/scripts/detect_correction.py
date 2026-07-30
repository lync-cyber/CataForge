"""PostToolUse Hook: Detect option-override corrections from user questions.

Matcher: platform ``user_question`` capability
Never blocks (exit 0).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

from cataforge.core.corrections import record_correction
from cataforge.core.paths import find_project_root
from cataforge.runtime.hook.base import hook_main, matches_capability, read_hook_input
from cataforge.runtime.hook.question import (
    normalize_answers,
    normalize_questions,
    recommended_label,
)


@dataclass(frozen=True)
class CorrectionOverride:
    question: str
    baseline: str
    actual: str


def _resolve_agent_id(data: dict[str, object]) -> str:
    value = data.get("agent_id")
    return str(value) if value else "orchestrator"


def find_option_overrides(data: dict[str, object]) -> list[CorrectionOverride]:
    tool_input = data.get("tool_input") or {}
    questions = normalize_questions(tool_input)
    answers = normalize_answers(data.get("tool_response") or {})
    overrides: list[CorrectionOverride] = []
    for question in questions:
        recommended = recommended_label(question)
        if not recommended:
            continue
        chosen = answers.get(question.id) or answers.get(question.text)
        if not chosen or chosen == [recommended]:
            continue
        overrides.append(
            CorrectionOverride(
                question=question.text,
                baseline=recommended,
                actual=", ".join(chosen),
            )
        )
    return overrides


@hook_main
def main() -> None:
    data = read_hook_input()

    if not data or not matches_capability(data, "user_question"):
        sys.exit(0)

    overrides = find_option_overrides(data)
    if not overrides:
        sys.exit(0)

    project_root = find_project_root()
    agent_id = _resolve_agent_id(data)
    tool_input = data.get("tool_input") or {}
    input_phase = tool_input.get("phase") if isinstance(tool_input, dict) else None
    phase = str(data.get("phase") or input_phase or "unknown")

    for override in overrides:
        print(
            f"[HOOK-INFO] correction | option-override | {override.question[:60]}",
            file=sys.stderr,
        )

        try:
            record_correction(
                project_root,
                trigger="option-override",
                agent=agent_id,
                phase=phase,
                question=override.question,
                baseline=override.baseline,
                actual=override.actual,
                deviation="preference",
            )
        except (ValueError, OSError) as e:
            print(f"[HOOK-WARN] {e}", file=sys.stderr)

    sys.exit(0)


if __name__ == "__main__":
    main()
