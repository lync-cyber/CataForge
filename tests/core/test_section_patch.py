"""Tests for markdown section patching (override existing + add new sections)."""

from __future__ import annotations

from cataforge.core.section_patch import apply_section_patch, patched_sections

_BASE = """\
---
name: architect
tools: file_read
---

# Role: Architect

## Identity
- 你是架构师
- 负责系统设计

## Execution Rules
- 先读 PRD
- 输出 arch 文档

## Output
- arch.md
"""


def test_override_existing_section() -> None:
    patch = "## Execution Rules\n- 改写后的规则\n- 第二条\n"
    out = apply_section_patch(_BASE, patch)
    assert "改写后的规则" in out
    # The base body of that section is gone.
    assert "先读 PRD" not in out
    # Other sections are untouched.
    assert "你是架构师" in out
    assert "arch.md" in out


def test_add_new_section_appended() -> None:
    patch = "## Project Conventions\n- 用 4 空格缩进\n"
    out = apply_section_patch(_BASE, patch)
    assert "## Project Conventions" in out
    # New section lands after the base sections.
    assert out.index("## Output") < out.index("## Project Conventions")
    # Existing sections survive intact.
    assert "先读 PRD" in out


def test_override_and_add_in_one_patch() -> None:
    patch = (
        "## Identity\n- 你是改写后的架构师\n\n"
        "## Extra Guidance\n- 额外约定\n"
    )
    out = apply_section_patch(_BASE, patch)
    assert "你是改写后的架构师" in out
    assert "你是架构师" not in out
    assert "## Extra Guidance" in out


def test_frontmatter_and_preamble_preserved() -> None:
    patch = "## Identity\n- changed\n"
    out = apply_section_patch(_BASE, patch)
    # Frontmatter + H1 preamble survive a section patch untouched.
    assert out.startswith("---\nname: architect\n")
    assert "# Role: Architect" in out


def test_empty_base_returns_patch_verbatim() -> None:
    patch = "## New\n- body\n"
    assert apply_section_patch("", patch) == patch


def test_patch_with_no_sections_is_noop() -> None:
    assert apply_section_patch(_BASE, "just prose, no headings\n") == _BASE


def test_patched_sections_inspection() -> None:
    patch = "## Identity\n- x\n\n## Brand New\n- y\n"
    overridden, added = patched_sections(_BASE, patch)
    assert overridden == ["Identity"]
    assert added == ["Brand New"]
