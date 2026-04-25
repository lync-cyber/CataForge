"""Rendering layer for PROJECT-STATE.md and similar in-tree templates.

Why this lives here, not on PlatformAdapter:

The platform adapter base class used to do the substitution inline
(``content.replace("运行时: {platform}", ...)``), which leaked the
template's literal Chinese wording into the abstraction. Any rewording
of PROJECT-STATE.md, or a future English template variant, would have
required editing platform/base.py — a layering violation.

By isolating the substitution here, ``PlatformAdapter`` only knows
"render the project-state file with the chosen platform_id"; the
actual placeholder syntax and template wording live next to the
documents they describe.
"""

from __future__ import annotations


_PROJECT_STATE_PLATFORM_PLACEHOLDER = "运行时: {platform}"


def render_project_state(content: str, platform_id: str) -> str:
    """Substitute the runtime-platform placeholder in PROJECT-STATE.md."""
    return content.replace(
        _PROJECT_STATE_PLATFORM_PLACEHOLDER,
        f"运行时: {platform_id}",
    )
