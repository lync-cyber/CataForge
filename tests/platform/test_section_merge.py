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
    """Preamble = everything before first ## heading (at-mentions, H1, banners).

    Regression tests for a dogfood-discovered bug: deploying CataForge on its
    own dev worktree erased the '<!-- DOGFOOD WORKTREE -->' banner and
    reverted '# CataForge (dev)' back to '# CataForge' — because the merger
    unconditionally let template preamble win.
    """

    def test_template_wins_when_current_preamble_is_empty(self) -> None:
        """First deploy: no prior preamble → use template."""
        cur = "## X\nbody\n"
        tpl = "@.cataforge/rules/COMMON-RULES.md\n\n# Title\n\n## X\nbody\n"
        out = merge_sections(cur, tpl, policy={"framework": ["X"]})
        assert out.startswith("@.cataforge/rules/COMMON-RULES.md")
        assert "# Title" in out

    def test_template_wins_when_semantically_equivalent(self) -> None:
        """Whitespace-only difference is not a user customization — template
        wins so framework preamble updates propagate on upgrade."""
        cur = "@.cataforge/rules/COMMON-RULES.md\n\n# CataForge\n\n## X\nbody\n"
        # Template is same content, different whitespace
        tpl = "@.cataforge/rules/COMMON-RULES.md\n# CataForge\n## X\nbody\n"
        out = merge_sections(cur, tpl, policy={"framework": ["X"]})
        # Template's compact form used — verify cur's double blanks not present
        assert "COMMON-RULES.md\n\n\n" not in out

    def test_user_customized_preamble_is_preserved(self) -> None:
        """User-added banner / custom H1 must survive deploy."""
        cur = (
            "@.cataforge/rules/COMMON-RULES.md\n\n"
            "<!-- DOGFOOD WORKTREE (dev 分支 · 形态 C) -->\n\n"
            "# CataForge (dev)\n\n"
            "## X\nbody\n"
        )
        tpl = (
            "@.cataforge/rules/COMMON-RULES.md\n\n"
            "# CataForge\n\n"
            "## X\nbody\n"
        )
        out = merge_sections(cur, tpl, policy={"framework": ["X"]})
        assert "DOGFOOD WORKTREE" in out
        assert "# CataForge (dev)" in out


class TestNestedFieldPreservation:
    """Regression tests for multi-line schema fields.

    Before the fix: ``- 阶段配置:`` with indented continuation lines had an
    inline value of ``""`` which ``_is_placeholder`` reported as True → the
    field was treated as unfilled and template default won, erasing the
    user's nested content. Discovered via dogfood deploy validation.
    """

    def test_nested_value_preserved_over_template(self) -> None:
        cur = (
            "## Info\n"
            "- 阶段配置:\n"
            "  - ui_design: N/A\n"
            "  - testing: 保留\n"
        )
        tpl = (
            "## Info\n"
            "- 阶段配置: 以下阶段可在 Bootstrap 时标记为 N/A 以跳过:\n"
            "  - ui_design: 后端/CLI/API-only 项目可跳过\n"
            "  - testing: 原型/PoC 项目可跳过\n"
        )
        out = merge_sections(cur, tpl, policy={"schema": ["Info"]})
        assert "ui_design: N/A" in out
        assert "testing: 保留" in out
        # Template's nested defaults must not leak through
        assert "后端/CLI/API-only 项目可跳过" not in out
        assert "原型/PoC 项目可跳过" not in out

    def test_empty_value_without_continuation_is_still_placeholder(self) -> None:
        """Edge: ``- key:`` with no body at all → accept template default."""
        cur = "## Info\n- 命名:\n"
        tpl = "## Info\n- 命名: kebab-case\n"
        out = merge_sections(cur, tpl, policy={"schema": ["Info"]})
        assert "kebab-case" in out

    def test_nested_list_under_bullet_preserved(self) -> None:
        """Nested markdown list under a bullet counts as content."""
        cur = (
            "## Info\n"
            "- 分支:\n"
            "  - main — 发布主线\n"
            "  - dev — dogfood\n"
        )
        tpl = "## Info\n- 分支: {策略}\n"
        out = merge_sections(cur, tpl, policy={"schema": ["Info"]})
        assert "main — 发布主线" in out
        assert "dev — dogfood" in out
        assert "{策略}" not in out


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
