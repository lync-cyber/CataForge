"""Pure token substitution for in-tree templates.

:func:`render_project_state` fills the framework-owned fields of
PROJECT-STATE.md from the resolved config: the ``运行时: {platform}`` token
(rendered from the declared platform audience so shared instruction files
are byte-stable across deploy order), the ``设计工具`` field
(``framework.json#project.design_tool``) and the ``人工审查检查点`` field
(``framework.json#constants.MANUAL_REVIEW_CHECKPOINTS``). It takes plain
values (no adapter), so it stays in ``core`` — adapter-bound placeholder
rendering lives in :mod:`cataforge.runtime.deploy.template_render`.
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

# Same wholesale-rewrite discipline for the manual-review-checkpoints bullet:
# framework.json#constants is the single source of truth, so the template
# never carries a copyable literal that can drift from COMMON-RULES.
_PROJECT_STATE_CHECKPOINTS_RE = re.compile(r"(?m)^- 人工审查检查点: \[[^\]\n]*\]")


def render_project_state(
    content: str,
    platform_id: str | list[str],
    *,
    design_tool: str = "none",
    manual_review_checkpoints: list[str] | None = None,
) -> str:
    """Substitute the framework-owned fields in PROJECT-STATE.md.

    ``platform_id`` accepts the single deploying platform or the full
    audience list of a shared instruction file — the rendered value depends
    only on the audience set, never on deploy order.
    """
    if isinstance(platform_id, str):
        audience = platform_id
    else:
        audience = ", ".join(dict.fromkeys(platform_id))
    content = content.replace(
        _PROJECT_STATE_PLATFORM_PLACEHOLDER,
        f"运行时: {audience}",
    )
    content = _PROJECT_STATE_DESIGN_TOOL_RE.sub(f"- 设计工具: {design_tool}", content)
    if manual_review_checkpoints is not None:
        rendered = ", ".join(str(c) for c in manual_review_checkpoints)
        content = _PROJECT_STATE_CHECKPOINTS_RE.sub(f"- 人工审查检查点: [{rendered}]", content)
    return content
