"""Unit tests for the section-level merger.

Covers the four section categories (framework / schema / runtime / user) plus
the AGENTS.md multi-platform scenario (item 3 of the deploy-strategy work).
"""

from __future__ import annotations

from cataforge.platform.section_merge import merge_sections


def _has_section(text: str, title: str) -> bool:
    return f"## {title}\n" in text


def _get_section(text: str, title: str) -> str:
    marker = f"## {title}\n"
    start = text.index(marker) + len(marker)
    # Find next ## or end of text
    rest = text[start:]
    idx = rest.find("\n## ")
    return rest if idx == -1 else rest[: idx + 1]


class TestFrameworkCategory:
    def test_framework_section_is_overwritten(self) -> None:
        cur = "## Docs\nold body\n"
        tpl = "## Docs\nnew body from framework upgrade\n"
        out = merge_sections(
            cur, tpl, policy={"framework": ["Docs"]}
        )
        assert "new body from framework upgrade" in out
        assert "old body" not in out


class TestSchemaCategory:
    def test_preserves_user_filled_values(self) -> None:
        cur = "## Info\n- 技术栈: Python 3.10+\n- 命名: kebab-case\n"
        tpl = "## Info\n- 技术栈: {框架/语言/工具}\n- 命名: {规范}\n"
        out = merge_sections(cur, tpl, policy={"schema": ["Info"]})
        assert "Python 3.10+" in out
        assert "kebab-case" in out
        assert "{框架/语言/工具}" not in out

    def test_absorbs_new_template_fields(self) -> None:
        cur = "## Info\n- 技术栈: Python\n"
        tpl = "## Info\n- 技术栈: {placeholder}\n- 新字段: default\n"
        out = merge_sections(cur, tpl, policy={"schema": ["Info"]})
        assert "Python" in out
        assert "- 新字段: default" in out

    def test_preserves_user_added_fields(self) -> None:
        cur = "## Info\n- 技术栈: Python\n- 私有字段: mine\n"
        tpl = "## Info\n- 技术栈: {placeholder}\n"
        out = merge_sections(cur, tpl, policy={"schema": ["Info"]})
        assert "私有字段: mine" in out

    def test_placeholder_values_get_template_default(self) -> None:
        cur = "## Info\n- 技术栈: {框架/语言/工具}\n"
        tpl = "## Info\n- 技术栈: auto-detected\n"
        out = merge_sections(cur, tpl, policy={"schema": ["Info"]})
        assert "auto-detected" in out

    def test_always_overwrite_fields_wins(self) -> None:
        """Item 3: per-platform runtime field always matches current deploy."""
        cur = "## Info\n- 运行时: cursor\n- 技术栈: Python\n"
        tpl = "## Info\n- 运行时: codex\n- 技术栈: {placeholder}\n"
        out = merge_sections(
            cur,
            tpl,
            policy={
                "schema": ["Info"],
                "always_overwrite_fields": {"Info": ["运行时"]},
            },
            platform_id="codex",
        )
        assert "运行时: codex" in out
        assert "运行时: cursor" not in out
        # Other user values still preserved
        assert "技术栈: Python" in out


class TestRuntimeCategory:
    def test_preserves_orchestrator_populated_body(self) -> None:
        cur = (
            "## State\n- 当前阶段: development\n- 上次完成: sprint-3\n"
        )
        tpl = (
            "## State\n- 当前阶段: {requirements|...}\n"
            "- 上次完成: {agent} — {desc}\n"
        )
        out = merge_sections(cur, tpl, policy={"runtime": ["State"]})
        assert "当前阶段: development" in out
        assert "上次完成: sprint-3" in out
        assert "{requirements|...}" not in out

    def test_uses_template_when_runtime_is_empty(self) -> None:
        cur = "## State\n\n"
        tpl = "## State\n- 当前阶段: {x}\n"
        out = merge_sections(cur, tpl, policy={"runtime": ["State"]})
        assert "- 当前阶段: {x}" in out


class TestUserExtension:
    def test_preserves_unclassified_sections_from_current(self) -> None:
        cur = (
            "## Info\n- a: 1\n"
            "## Dogfood Rules\n1. rule\n2. rule2\n"
        )
        tpl = "## Info\n- a: 1\n"
        out = merge_sections(
            cur, tpl, policy={"schema": ["Info"], "user_extensible": True}
        )
        assert _has_section(out, "Dogfood Rules")
        assert "1. rule" in out

    def test_user_extensible_false_drops_extra_sections(self) -> None:
        cur = "## Info\n- a: 1\n## Extra\nbody\n"
        tpl = "## Info\n- a: 1\n"
        out = merge_sections(
            cur, tpl, policy={"schema": ["Info"], "user_extensible": False}
        )
        assert not _has_section(out, "Extra")


class TestTemplateOrderingDrives:
    def test_output_follows_template_order(self) -> None:
        # Template introduces a new section and reorders
        cur = "## B\nold-b\n## A\nold-a\n"
        tpl = "## A\nnew-a\n## B\nnew-b\n## C\nnew-c\n"
        out = merge_sections(
            cur, tpl, policy={"framework": ["A", "B", "C"]}
        )
        idx_a = out.index("## A")
        idx_b = out.index("## B")
        idx_c = out.index("## C")
        assert idx_a < idx_b < idx_c


class TestSectionAnnotationStripping:
    def test_matches_section_with_trailing_parenthetical(self) -> None:
        # The real PROJECT-STATE.md uses
        # "## 项目状态 (orchestrator专属写入区，其他Agent禁止修改)".
        # Policy names plain "项目状态"; merger strips the annotation.
        cur = "## 项目状态 (orchestrator专属写入区)\nuser-data\n"
        tpl = "## 项目状态 (orchestrator专属写入区)\ntemplate-default\n"
        out = merge_sections(
            cur, tpl, policy={"runtime": ["项目状态"]}
        )
        assert "user-data" in out
        assert "template-default" not in out


class TestPreamble:
    def test_preamble_from_template_is_used(self) -> None:
        cur = "old preamble\n## X\nbody\n"
        tpl = "@.cataforge/rules/COMMON-RULES.md\n\n## X\nbody\n"
        out = merge_sections(cur, tpl, policy={"framework": ["X"]})
        assert out.startswith("@.cataforge/rules/COMMON-RULES.md")


class TestAGENTSMultiPlatform:
    """Item 3: cursor → codex sequential deploys to AGENTS.md should not lose
    the current platform's runtime identifier."""

    def test_platform_runtime_field_is_current_platform(self) -> None:
        # Simulated: cursor wrote AGENTS.md first
        cursor_output = "## 项目信息\n- 运行时: cursor\n- 技术栈: Python\n"
        # Now codex's deploy runs — the template will have 运行时: codex
        codex_template = "## 项目信息\n- 运行时: codex\n- 技术栈: {placeholder}\n"

        out = merge_sections(
            cursor_output,
            codex_template,
            policy={
                "schema": ["项目信息"],
                "always_overwrite_fields": {"项目信息": ["运行时"]},
            },
            platform_id="codex",
        )

        assert "运行时: codex" in out
        assert "运行时: cursor" not in out
        # User-provided tech stack survived even through a different
        # platform's deploy.
        assert "技术栈: Python" in out
