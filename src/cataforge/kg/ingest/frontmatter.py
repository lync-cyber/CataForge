"""Markdown YAML frontmatter extraction (`---\\n…\\n---`)."""

from __future__ import annotations

import warnings
from typing import Any

import yaml

_PARSE_ERROR_KEY = "__parse_error__"


def parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """Split a Markdown document into (frontmatter dict, body text).

    A document without leading ``---`` is returned with an empty dict and the
    original content as body.

    When the YAML block is present but malformed, the returned dict contains
    ``{"__parse_error__": "<message>"}`` and a ``UserWarning`` is emitted.
    Callers that do not check the sentinel key continue to behave as before
    (they receive an otherwise-empty dict).
    """
    if not content.startswith("---"):
        return {}, content

    lines = content.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return {}, content

    closing_idx = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            closing_idx = i
            break

    if closing_idx is None:
        return {}, content

    fm_text = "".join(lines[1:closing_idx])
    body = "".join(lines[closing_idx + 1 :])

    try:
        data = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError as exc:
        msg = f"YAML parse error in frontmatter: {exc}"
        warnings.warn(msg, category=UserWarning, stacklevel=2)
        return {_PARSE_ERROR_KEY: str(exc)}, body

    if not isinstance(data, dict):
        data = {}
    return data, body
