"""PostToolUse Hook: Detect option-override corrections from AskUserQuestion.

Matcher: AskUserQuestion
Never blocks (exit 0).
"""

import os
import sys
from datetime import datetime

from cataforge.core.paths import find_project_root
from cataforge.hook.base import hook_main, matches_capability, read_hook_input

CORRECTIONS_LOG = os.path.join("docs", "reviews", "CORRECTIONS-LOG.md")


def _recommended_label(options: list) -> str | None:
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
            "> 本文件由 detect_correction hook 追加写入。\n"
            "> 触发条件见 ORCHESTRATOR-PROTOCOLS.md §On-Correction Learning Protocol。\n"
        )
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(header)
            f.write(entry)
    else:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(entry)


def _resolve_agent_id(data: dict) -> str:
    return data.get("agent_id") or "orchestrator"


def _extract_answers(tool_response: object) -> dict:
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

    project_dir = str(find_project_root())
    agent_id = _resolve_agent_id(data)

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
            _append_corrections_log(
                project_dir, "unknown", agent_id, question_text, recommended, str(chosen)
            )
        except Exception as e:
            print(f"[HOOK-WARN] {e}", file=sys.stderr)

    sys.exit(0)


if __name__ == "__main__":
    main()
