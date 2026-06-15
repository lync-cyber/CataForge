"""Unit tests for the section-level merger.

Covers the four section categories (framework / schema / runtime / user) plus
the AGENTS.md multi-platform scenario (item 3 of the deploy-strategy work).
"""

from __future__ import annotations

from cataforge.adapter.platform.section_merge import merge_sections


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
        out = merge_sections(cur, tpl, policy={"framework": ["Docs"]})
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
        cur = "## State\n- 当前阶段: development\n- 上次完成: sprint-3\n"
        tpl = "## State\n- 当前阶段: {requirements|...}\n- 上次完成: {agent} — {desc}\n"
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
        cur = "## Info\n- a: 1\n## Dogfood Rules\n1. rule\n2. rule2\n"
        tpl = "## Info\n- a: 1\n"
        out = merge_sections(cur, tpl, policy={"schema": ["Info"], "user_extensible": True})
        assert _has_section(out, "Dogfood Rules")
        assert "1. rule" in out

    def test_user_extensible_false_drops_extra_sections(self) -> None:
        cur = "## Info\n- a: 1\n## Extra\nbody\n"
        tpl = "## Info\n- a: 1\n"
        out = merge_sections(cur, tpl, policy={"schema": ["Info"], "user_extensible": False})
        assert not _has_section(out, "Extra")


class TestTemplateOrderingDrives:
    def test_output_follows_template_order(self) -> None:
        # Template introduces a new section and reorders
        cur = "## B\nold-b\n## A\nold-a\n"
        tpl = "## A\nnew-a\n## B\nnew-b\n## C\nnew-c\n"
        out = merge_sections(cur, tpl, policy={"framework": ["A", "B", "C"]})
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
        out = merge_sections(cur, tpl, policy={"runtime": ["项目状态"]})
        assert "user-data" in out
        assert "template-default" not in out

    def test_cross_version_heading_rename_updates_in_place(self) -> None:
        """A runtime heading's embedded command hint changed across versions.
        The merger matches the existing filled section by canonical name, adopts
        the new heading, and does NOT duplicate it with a placeholder body."""
        cur = (
            "## 执行环境 (Bootstrap 时由 `cataforge setup --emit-env-block` 填入)\n"
            "- OS: Windows\n- Python: 3.12\n"
        )
        tpl = (
            "## 执行环境 (Bootstrap 时由 `cataforge setup env-block` 填入)\n"
            "{执行环境检测结果 — 未填入时 orchestrator 应在 Bootstrap 时调用:\n"
            " cataforge setup env-block}\n"
        )
        out = merge_sections(cur, tpl, policy={"runtime": ["执行环境"]})
        assert out.count("## 执行环境") == 1
        assert "cataforge setup env-block" in out  # new heading hint adopted
        assert "OS: Windows" in out  # user-filled body preserved
        assert "{执行环境检测结果" not in out  # placeholder not injected

    def test_collapses_preexisting_duplicate_sections(self) -> None:
        """A file already corrupted with a placeholder + a filled duplicate
        heals to a single filled section on the next deploy, regardless of which
        duplicate appears first."""
        cur = (
            "## 执行环境 (Bootstrap 时由 `cataforge setup env-block` 填入)\n"
            "{执行环境检测结果}\n"
            "## 执行环境 (Bootstrap 时由 `old-cmd` 填入)\n"
            "- OS: Windows\n"
        )
        tpl = "## 执行环境 (Bootstrap 时由 `cataforge setup env-block` 填入)\n{执行环境检测结果}\n"
        out = merge_sections(cur, tpl, policy={"runtime": ["执行环境"]})
        assert out.count("## 执行环境") == 1
        assert "OS: Windows" in out
        assert "{执行环境检测结果}" not in out

    def test_cross_version_rename_is_idempotent(self) -> None:
        """After the in-place update, re-deploying the same template is a fixpoint."""
        cur = "## 执行环境 (Bootstrap 时由 `old-cmd` 填入)\n- OS: Windows\n"
        tpl = "## 执行环境 (Bootstrap 时由 `new-cmd` 填入)\n{执行环境检测结果}\n"
        once = merge_sections(cur, tpl, policy={"runtime": ["执行环境"]})
        twice = merge_sections(once, tpl, policy={"runtime": ["执行环境"]})
        assert once == twice
        assert once.count("## 执行环境") == 1
        assert "OS: Windows" in once


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
        tpl = "@.cataforge/rules/COMMON-RULES.md\n\n# CataForge\n\n## X\nbody\n"
        out = merge_sections(cur, tpl, policy={"framework": ["X"]})
        assert "DOGFOOD WORKTREE" in out
        assert "# CataForge (dev)" in out


class TestNestedFieldPreservation:
    """Regression tests for multi-line schema fields."""

    def test_nested_value_preserved_over_template(self) -> None:
        cur = "## Info\n- 阶段配置:\n  - ui_design: N/A\n  - testing: 保留\n"
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
        cur = "## Info\n- 分支:\n  - main — 发布主线\n  - dev — dogfood\n"
        tpl = "## Info\n- 分支: {策略}\n"
        out = merge_sections(cur, tpl, policy={"schema": ["Info"]})
        assert "main — 发布主线" in out
        assert "dev — dogfood" in out
        assert "{策略}" not in out


class TestForeignCuratedFile:
    """A hand-curated instruction file with zero schema/runtime overlap must
    keep its content and only gain framework sections — never template
    boilerplate injection."""

    _POLICY = {
        "framework": ["文档导航", "框架机制"],
        "schema": ["项目信息", "全局约定"],
        "runtime": ["项目状态", "执行环境"],
        "user_extensible": True,
    }
    _TPL = (
        "# CataForge\n\n"
        "## 项目信息\n- 技术栈: {框架/语言/工具}\n\n"
        "## 项目状态\n- 当前阶段: {x}\n\n"
        "## 文档导航\n- 导航索引: docs/.doc-index.json\n\n"
        "## 框架机制\n- Agent编排: orchestrator\n"
    )
    _CURATED = (
        "# My Project\n\n"
        "## Git Workflow\nmain protected; PRs only\n\n"
        "## House Rules\nrun tests before commit\n"
    )

    def test_preserves_curated_content_and_appends_framework(self) -> None:
        out = merge_sections(self._CURATED, self._TPL, policy=self._POLICY)
        # User sections survive verbatim.
        assert _has_section(out, "Git Workflow")
        assert "main protected" in out
        assert _has_section(out, "House Rules")
        # Framework sections are attached.
        assert _has_section(out, "文档导航")
        assert "导航索引: docs/.doc-index.json" in out
        assert _has_section(out, "框架机制")
        # Schema/runtime scaffolding is NOT injected.
        assert not _has_section(out, "项目信息")
        assert not _has_section(out, "项目状态")

    def test_is_idempotent(self) -> None:
        once = merge_sections(self._CURATED, self._TPL, policy=self._POLICY)
        twice = merge_sections(once, self._TPL, policy=self._POLICY)
        assert once == twice

    def test_template_derived_file_is_not_foreign(self) -> None:
        """A file carrying even one schema section uses the normal merge path."""
        cur = "## 项目信息\n- 技术栈: Python\n\n## My Extension\ncustom\n"
        out = merge_sections(cur, self._TPL, policy=self._POLICY)
        assert "技术栈: Python" in out  # schema field preserved (normal path)
        assert _has_section(out, "项目状态")  # runtime scaffolding injected (normal path)
        assert _has_section(out, "My Extension")

    def test_framework_only_policy_keeps_normal_path(self) -> None:
        """No schema/runtime declared → foreign detection is inert."""
        cur = "## A\nuser-a\n## Extra\nuser-extra\n"
        tpl = "## A\nnew-a\n"
        out = merge_sections(cur, tpl, policy={"framework": ["A"], "user_extensible": True})
        assert "new-a" in out
        assert _has_section(out, "Extra")


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


class TestBlankLinePreservation:
    """The blank line between a heading and its body must survive the merge.

    Dropping it violates MD022 and makes section-merge non-idempotent: every
    deploy strips the blank, producing a churn diff on an otherwise unchanged
    instruction file. Covers all three body-bearing categories plus a
    round-trip fixpoint check.
    """

    def test_framework_section_keeps_blank_line(self) -> None:
        cur = "## Docs\n\nold\n"
        tpl = "## Docs\n\nnew body\n"
        out = merge_sections(cur, tpl, policy={"framework": ["Docs"]})
        assert "## Docs\n\nnew body" in out

    def test_runtime_section_keeps_blank_line(self) -> None:
        cur = "## State\n\n- 当前阶段: development\n"
        tpl = "## State\n\n- 当前阶段: {x}\n"
        out = merge_sections(cur, tpl, policy={"runtime": ["State"]})
        assert "## State\n\n- 当前阶段: development" in out

    def test_schema_section_keeps_blank_line(self) -> None:
        cur = "## Info\n\n- 技术栈: Python\n"
        tpl = "## Info\n\n- 技术栈: {x}\n"
        out = merge_sections(cur, tpl, policy={"schema": ["Info"]})
        assert "## Info\n\n- 技术栈: Python" in out

    def test_compact_section_stays_compact(self) -> None:
        """A heading with no blank line is left as-is — the fix preserves the
        author's spacing, it does not force a blank in."""
        cur = "## Docs\nbody\n"
        tpl = "## Docs\nbody\n"
        out = merge_sections(cur, tpl, policy={"framework": ["Docs"]})
        assert "## Docs\nbody" in out
        assert "## Docs\n\nbody" not in out

    def test_blank_lines_are_idempotent(self) -> None:
        cur = (
            "# CataForge\n\n"
            "## 项目信息\n\n- 技术栈: Python\n\n"
            "## 文档导航\n\n- 导航索引: docs/.doc-index.json\n\n"
            "## My Ext\n\ncustom\n"
        )
        tpl = "## 项目信息\n\n- 技术栈: {x}\n\n## 文档导航\n\n- 导航索引: docs/.doc-index.json\n"
        policy = {
            "schema": ["项目信息"],
            "framework": ["文档导航"],
            "user_extensible": True,
        }
        once = merge_sections(cur, tpl, policy=policy)
        assert "## 项目信息\n\n- 技术栈: Python" in once
        assert "## 文档导航\n\n- 导航索引" in once
        assert "## My Ext\n\ncustom" in once
        twice = merge_sections(once, tpl, policy=policy)
        assert once == twice

    def test_sections_separated_by_blank_line(self) -> None:
        """A blank line precedes every heading even when the prior section's
        framework body carries no trailing blank (MD022)."""
        cur = "## A\nbody-a\n## B\nbody-b\n"
        tpl = "## A\nnew-a\n"  # framework body, no trailing blank line
        out = merge_sections(cur, tpl, policy={"framework": ["A"], "user_extensible": True})
        assert "new-a\n\n## B" in out
        assert "new-a\n## B" not in out
