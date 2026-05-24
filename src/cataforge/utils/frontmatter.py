"""Single entry point for YAML front matter in Markdown (requires PyYAML)."""

from __future__ import annotations

import re
from typing import Any

import yaml

# Matches a closing front matter fence: a line that is exactly ``---``
# (optional trailing whitespace), anchored at line start.
_FENCE_RE = re.compile(r"^---\s*$", re.MULTILINE)


def split_yaml_frontmatter(raw: str) -> tuple[dict[str, Any] | None, str]:
    """Split leading ``---`` / ``---`` YAML block from Markdown body.

    Returns:
        ``(None, raw)`` if the document does not start with a front matter fence.
        ``(metadata_dict, body)`` if a block was parsed (empty dict on YAML parse edge cases).
    """
    if not raw.startswith("---"):
        return None, raw

    # Search for a closing fence that sits at the start of a line, beginning
    # after the opening fence (offset 3).
    m = _FENCE_RE.search(raw, 3)
    if m is None:
        return None, raw

    end = m.start()
    fm_text = raw[3:end].strip()
    body = raw[m.end() :]
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
