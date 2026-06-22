"""Pure token substitution for in-tree templates.

:func:`render_project_state` fills the framework-owned fields of
PROJECT-STATE.md from the resolved config: the runtime ``运行时: {platform}``
token and the ``设计工具`` field (sourced from ``framework.json#project
.design_tool``). It takes plain values (no adapter), so it stays in ``core`` —
adapter-bound placeholder rendering lives in
:mod:`cataforge.runtime.deploy.template_render`.
"""

from __future__ import annotations

import re

_PROJECT_STATE_PLATFORM_PLACEHOLDER = "运行时: {platform}"

# Rewrites the whole ``- 设计工具: <anything>`` bullet so the framework.json
# value wins regardless of what the on-disk PROJECT-STATE.md carries — a fresh
# ``{DESIGN_TOOL}`` placeholder or a legacy hand-edited literal alike. Paired
# with the platform profiles' ``always_overwrite_fields: 全局约定: [设计工具]``,
# this makes framework.json the single source of truth for the field.
_PROJECT_STATE_DESIGN_TOOL_RE = re.compile(r"(?m)^- 设计工具:.*$")


def render_project_state(
    content: str,
    platform_id: str,
    *,
    design_tool: str = "none",
) -> str:
    """Substitute the runtime-platform and design-tool fields in PROJECT-STATE.md."""
    content = content.replace(
        _PROJECT_STATE_PLATFORM_PLACEHOLDER,
        f"运行时: {platform_id}",
    )
    content = _PROJECT_STATE_DESIGN_TOOL_RE.sub(f"- 设计工具: {design_tool}", content)
    return content
