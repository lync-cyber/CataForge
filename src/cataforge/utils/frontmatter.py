"""Single entry point for YAML front matter in Markdown (requires PyYAML)."""

from __future__ import annotations

from typing import Any

import yaml


def split_yaml_frontmatter(raw: str) -> tuple[dict[str, Any] | None, str]:
    """Split leading ``---`` / ``---`` YAML block from Markdown body.

    Returns:
        ``(None, raw)`` if the document does not start with a front matter fence.
        ``(metadata_dict, body)`` if a block was parsed (empty dict on YAML parse edge cases).
    """
    if not raw.startswith("---"):
        return None, raw

    end = raw.find("---", 3)
    if end == -1:
        return None, raw

    fm_text = raw[3:end].strip()
    body = raw[end + 3 :]
    if body.startswith("\n"):
        body = body[1:]

    if not fm_text:
        return {}, body

    try:
        data = yaml.safe_load(fm_text)
    except yaml.YAMLError:
        return {}, body

    if data is None:
        return {}, body
    if not isinstance(data, dict):
        return {}, body
    return dict(data), body
