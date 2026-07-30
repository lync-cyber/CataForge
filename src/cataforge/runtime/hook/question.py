"""Platform-neutral normalization for structured user-question payloads."""

from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass(frozen=True)
class NormalizedQuestion:
    id: str
    text: str
    options: tuple[str, ...]


def normalize_questions(tool_input: object) -> list[NormalizedQuestion]:
    """Normalize Codex/Claude/OpenCode question input into one shape."""
    if not isinstance(tool_input, dict):
        return []
    raw_questions = tool_input.get("questions")
    if not isinstance(raw_questions, list):
        return []

    questions: list[NormalizedQuestion] = []
    for index, raw in enumerate(raw_questions):
        if not isinstance(raw, dict):
            continue
        text = raw.get("question")
        if not isinstance(text, str) or not text:
            continue
        question_id = raw.get("id")
        if not isinstance(question_id, str) or not question_id:
            question_id = text or f"question-{index}"
        options: list[str] = []
        raw_options = raw.get("options")
        if isinstance(raw_options, list):
            for option in raw_options:
                if isinstance(option, str) and option:
                    options.append(option)
                elif isinstance(option, dict):
                    label = option.get("label")
                    if isinstance(label, str) and label:
                        options.append(label)
        questions.append(NormalizedQuestion(id=question_id, text=text, options=tuple(options)))
    return questions


def normalize_answers(tool_response: object) -> dict[str, list[str]]:
    """Normalize response answers to ``question_id -> selected labels``.

    Codex presents the hook with a JSON string whose values are
    ``{"answers": [...]}``; Claude/OpenCode may provide a mapping directly,
    including the historical question-text → string form.
    """
    response = tool_response
    if isinstance(response, str):
        try:
            response = json.loads(response)
        except (json.JSONDecodeError, TypeError):
            return {}
    if not isinstance(response, dict):
        return {}

    nested = response.get("answers")
    if isinstance(nested, list):
        answers: dict[str, list[str]] = {}
        for entry in nested:
            if not isinstance(entry, dict):
                continue
            question_id = entry.get("question_id") or entry.get("id")
            if not isinstance(question_id, str) or not question_id:
                continue
            selected = _selected_answers(entry.get("answers", entry.get("answer")))
            if selected:
                answers[question_id] = selected
        return answers
    if isinstance(nested, dict):
        response = nested

    answers = {}
    for key, value in response.items():
        if not isinstance(key, str):
            continue
        if isinstance(value, dict):
            value = value.get("answers", value.get("answer"))
        selected = _selected_answers(value)
        if selected:
            answers[key] = selected
    return answers


def _selected_answers(value: object) -> list[str]:
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str) and item]
    return []


def recommended_label(question: NormalizedQuestion) -> str | None:
    """Return the explicitly marked recommended option, if present."""
    return next(
        (label for label in question.options if "(Recommended)" in label or "(推荐)" in label),
        None,
    )
