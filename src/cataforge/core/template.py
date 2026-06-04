"""Pure token substitution for in-tree templates.

:func:`render_project_state` substitutes ``运行时: {platform}`` in
PROJECT-STATE.md. It takes only a platform id (no adapter), so it stays in
``core`` — adapter-bound placeholder rendering lives in
:mod:`cataforge.runtime.deploy.template_render`.
"""

from __future__ import annotations

_PROJECT_STATE_PLATFORM_PLACEHOLDER = "运行时: {platform}"


def render_project_state(content: str, platform_id: str) -> str:
    """Substitute the runtime-platform placeholder in PROJECT-STATE.md."""
    return content.replace(
        _PROJECT_STATE_PLATFORM_PLACEHOLDER,
        f"运行时: {platform_id}",
    )
