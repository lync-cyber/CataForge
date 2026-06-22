"""Unit tests for ``cataforge.core.template.render_project_state``."""

from __future__ import annotations

from cataforge.core.template import render_project_state


def test_renders_platform_token() -> None:
    out = render_project_state("运行时: {platform}\n", "claude-code")
    assert "运行时: claude-code" in out
    assert "{platform}" not in out


def test_renders_design_tool_placeholder() -> None:
    out = render_project_state("- 设计工具: {DESIGN_TOOL}\n", "claude-code", design_tool="penpot")
    assert "- 设计工具: penpot" in out
    assert "{DESIGN_TOOL}" not in out


def test_design_tool_defaults_to_none() -> None:
    out = render_project_state("- 设计工具: {DESIGN_TOOL}\n", "claude-code")
    assert "- 设计工具: none" in out


def test_design_tool_rewrites_legacy_literal_value() -> None:
    """A PROJECT-STATE.md that still carries a hand-edited literal (no
    placeholder) is rewritten to the framework.json value, so existing
    projects converge on the single source of truth without a separate
    file migration."""
    out = render_project_state("- 设计工具: penpot\n", "claude-code", design_tool="none")
    assert "- 设计工具: none" in out
    assert "penpot" not in out


def test_design_tool_rewrite_leaves_comment_untouched() -> None:
    src = "- 设计工具: {DESIGN_TOOL}\n  <!-- 可选值: none | penpot -->\n"
    out = render_project_state(src, "claude-code", design_tool="penpot")
    assert "- 设计工具: penpot" in out
    assert "<!-- 可选值: none | penpot -->" in out
