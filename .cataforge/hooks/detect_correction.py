#!/usr/bin/env python3
"""PostToolUse Hook: Detect option-override corrections from AskUserQuestion.

Matcher: AskUserQuestion
Never blocks (exit 0).

Detection rule:
  For each question whose options contain exactly one "(Recommended)" label,
  if the user selected a different option, emit a `correction` event
  (severity=hard) and append an entry to docs/reviews/CORRECTIONS-LOG.md.

Rationale:
  The previous On-Correction Learning Protocol only triggered on
  Interrupt-Resume + literal [ASSUMPTION] override — composite hit rate
  ~0.5%. By promoting option-override to a structural signal we raise
  that to ~20% without any LLM-side judgment.

Test:
  echo '{"tool_name":"AskUserQuestion","tool_input":{"questions":[{"question":"Q","options":[{"label":"A (Recommended)","description":"x"},{"label":"B","description":"y"}]}]},"tool_response":{"answers":{"Q":"B"}}}' | python .cataforge/hooks/detect_correction.py
  Expected: exit 0, one correction event in EVENT-LOG.jsonl + one section in CORRECTIONS-LOG.md
"""

import json
import os
import sys
from datetime import datetime

from _hook_base import hook_main, read_hook_input, matches_capability

# Shared utilities
_scripts = os.path.join(os.path.dirname(__file__), "..", "scripts")
for _p in (
    os.path.join(_scripts, "lib"),
    os.path.join(_scripts, "framework"),
):
    if _p not in sys.path:
        sys.path.insert(0, _p)
try:
    from event_logger import append_event as _log_event
except ImportError:
    _log_event = None

try:
    from phase_reader import read_current_phase as _read_phase
except ImportError:
    _read_phase = None


CORRECTIONS_LOG = os.path.join("docs", "reviews", "CORRECTIONS-LOG.md")


def _recommended_label(options: list) -> str | None:
    """Return the label of the first option marked '(Recommended)', or None."""
    if not isinstance(options, list):
        return None
    for opt in options:
        if not isinstance(opt, dict):
            continue
        label = opt.get("label", "") or ""
        if "(Recommended)" in label or "(推荐)" in label:
            return label
    return None


def _append_corrections_log(
    project_dir: str,
    phase: str,
    agent_id: str,
    question: str,
    recommended: str,
    chosen: str,
) -> None:
    """Append one entry to CORRECTIONS-LOG.md (create if missing)."""
    log_path = os.path.join(project_dir, CORRECTIONS_LOG)
    parent = os.path.dirname(log_path)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)

    date = datetime.now().strftime("%Y-%m-%d")
    entry = (
        f"\n### {date} | {agent_id} | {phase}\n"
        f"- 触发信号: option-override\n"
        f"- 问题: {question}\n"
        f"- 推荐选项: {recommended}\n"
        f"- 用户选择: {chosen}\n"
        f"- 偏差类型: preference\n"
    )

    if not os.path.exists(log_path):
        header = (
            "# Corrections Log\n\n"
            "> 本文件由 `.cataforge/hooks/detect_correction.py` 追加写入。\n"
            "> 触发条件见 ORCHESTRATOR-PROTOCOLS.md §On-Correction Learning Protocol。\n"
        )
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(header)
            f.write(entry)
    else:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(entry)


def _resolve_agent_id(data: dict) -> str:
    """Best-effort agent_id resolution for the current dispatch context.

    Claude Code does not inject agent identity into hook payloads, so we
    inspect the recent tool call context or fall back to 'orchestrator'.
    """
    # Future enhancement: walk recent messages for subagent_type.
    return data.get("agent_id") or "orchestrator"


def _extract_answers(tool_response) -> dict:
    """AskUserQuestion returns { answers: { <question_text>: <selected_label> } }.

    Tolerate both dict-wrapped and direct-dict shapes.
    """
    if not isinstance(tool_response, dict):
        return {}
    answers = tool_response.get("answers")
    if isinstance(answers, dict):
        return answers
    # Fallback: direct mapping
    return (
        tool_response if all(isinstance(v, str) for v in tool_response.values()) else {}
    )


@hook_main
def main():
    if not _log_event:
        sys.exit(0)

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

    hooks_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(os.path.dirname(hooks_dir))

    phase = "unknown"
    if _read_phase:
        try:
            phase = _read_phase(project_dir) or "unknown"
        except Exception as e:
            print(f"[HOOK-WARN] {e}", file=sys.stderr)

    agent_id = _resolve_agent_id(data)

    for q in questions:
        if not isinstance(q, dict):
            continue
        question_text = q.get("question", "") or ""
        options = q.get("options") or []
        recommended = _recommended_label(options)
        if not recommended:
            continue  # No baseline to compare against — skip this question.

        chosen = answers.get(question_text)
        if not chosen or chosen == recommended:
            continue  # User accepted the recommendation or answered nothing.

        # Option override detected.
        try:
            _log_event(
                event="correction",
                phase=phase,
                agent=agent_id,
                detail=(
                    f"option-override | {question_text[:60]} | "
                    f"推荐={recommended[:30]} 选={str(chosen)[:30]}"
                ),
            )
        except Exception as e:
            print(f"[HOOK-WARN] {e}", file=sys.stderr)

        try:
            _append_corrections_log(
                project_dir,
                phase,
                agent_id,
                question_text,
                recommended,
                str(chosen),
            )
        except Exception as e:
            print(f"[HOOK-WARN] {e}", file=sys.stderr)

    sys.exit(0)


if __name__ == "__main__":
    main()
