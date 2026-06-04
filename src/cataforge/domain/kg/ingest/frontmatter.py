"""Markdown YAML frontmatter extraction (`---\\n…\\n---`)."""

from __future__ import annotations

from typing import Any

from cataforge.utils.frontmatter import _PARSE_ERROR_KEY, split_yaml_frontmatter

__all__ = ["parse_frontmatter", "_PARSE_ERROR_KEY"]


def parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """Split a Markdown document into (frontmatter dict, body text).

    A document without leading ``---`` is returned with an empty dict and the
    original content as body.

    When the YAML block is present but malformed, the returned dict contains
    ``{"__parse_error__": "<message>"}`` and a ``UserWarning`` is emitted.
    """
    meta, body = split_yaml_frontmatter(content, on_error="marker")
    if meta is None:
        return {}, content
    return meta, body
