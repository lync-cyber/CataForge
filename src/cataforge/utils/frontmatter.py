"""Single entry point for YAML front matter in Markdown (requires PyYAML)."""

from __future__ import annotations

import re
import warnings
from typing import Any, Literal

import yaml

# Matches a closing front matter fence: a line that is exactly ``---``
# (optional trailing whitespace), anchored at line start.
_FENCE_RE = re.compile(r"^---\s*$", re.MULTILINE)

_PARSE_ERROR_KEY = "__parse_error__"


def split_yaml_frontmatter(
    raw: str,
    on_error: Literal["empty", "marker", "raise"] = "empty",
) -> tuple[dict[str, Any] | None, str]:
    """Split leading ``---`` / ``---`` YAML block from Markdown body.

    Args:
        raw: Raw Markdown string.
        on_error: Controls behaviour when the YAML block is present but
            malformed.
            ``"empty"`` (default) — return ``{}`` silently.
            ``"marker"`` — return ``{"__parse_error__": "<msg>"}`` and emit
            a ``UserWarning``.
            ``"raise"`` — re-raise the ``yaml.YAMLError``.

    Returns:
        ``(None, raw)`` if the document does not start with a front matter
        fence.  ``(metadata_dict, body)`` when a block is found; the dict
        is empty on YAML parse edge cases (behaviour governed by
        ``on_error``).
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
    except yaml.YAMLError as exc:
        if on_error == "raise":
            raise
        if on_error == "marker":
            msg = f"YAML parse error in frontmatter: {exc}"
            warnings.warn(msg, category=UserWarning, stacklevel=2)
            return {_PARSE_ERROR_KEY: str(exc)}, body
        # on_error == "empty"
        return {}, body

    if data is None:
        return {}, body
    if not isinstance(data, dict):
        return {}, body
    return dict(data), body
