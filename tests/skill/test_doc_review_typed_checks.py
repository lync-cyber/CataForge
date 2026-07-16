"""Characterization tests for TypedDocChecksMixin — lock current branch behaviour.

Each test constructs a minimal DocChecker backed by a temp file, calls one
typed check method, and asserts on the errors/warnings the checker produced.
Tests cover both the pass (no issue) and fail/warn paths for every check
method in TypedDocChecksMixin.
"""

from __future__ import annotations

from pathlib import Path

from cataforge.runtime.skill.builtins.doc_review.checker import DocChecker

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _checker(tmp_path: Path, doc_type: str, content: str) -> DocChecker:
    """Write *content* to a temp file and return a DocChecker for it."""
    f = tmp_path / f"{doc_type}.md"
    f.write_text(content, encoding="utf-8")
    return DocChecker(doc_type, str(f), docs_dir=str(tmp_path))


# ---------------------------------------------------------------------------
# check_prd
# ---------------------------------------------------------------------------

_PRD_GOOD = """\
### F-001 Login
用户故事: As a user I want to login.
- AC-001: Return token on success.
优先级: P0

## 3. 非功能需求
- 性能
- 安全
- 可用性
"""

_PRD_MISSING_USER_STORIES = """\
### F-001 Feature A
- AC-001: Return value.
优先级: P0

### F-002 Feature B
- AC-002: Show result.
优先级: P1

## 3. 非功能需求
- 性能
- 安全
- 可用性
"""

_PRD_NO_AC = """\
### F-001 Login
用户故事: As a user I want to login.
优先级: P0

## 3. 非功能需求
- 性能
- 安全
- 可用性
"""

_PRD_NFR_TOO_SHORT = """\
### F-001 Login
用户故事: As a user I want to login.
- AC-001: Return token.
优先级: P0

## 3. 非功能需求
- 性能
"""

_PRD_MISSING_PRIORITY = """\
### F-001 Login
用户故事: As a user I want to login.
- AC-001: Return token.

## 3. 非功能需求
- 性能
- 安全
- 可用性
"""


def test_check_prd_pass(tmp_path: Path) -> None:
    """Well-formed PRD with user stories, AC, NFR, and priorities passes."""
    c = _checker(tmp_path, "prd", _PRD_GOOD)
    c.check_prd()
    assert c.errors == []


def test_check_prd_more_features_than_user_stories_fails(tmp_path: Path) -> None:
    """Two F-NNN sections but only one user story triggers a failure."""
    c = _checker(tmp_path, "prd", _PRD_MISSING_USER_STORIES)
    c.check_prd()
    assert any("用户故事" in e for e in c.errors)


def test_check_prd_no_ac_fails(tmp_path: Path) -> None:
    """PRD with no AC-NNN entries is rejected."""
    c = _checker(tmp_path, "prd", _PRD_NO_AC)
    c.check_prd()
    assert any("AC" in e or "验收" in e for e in c.errors)


def test_check_prd_nfr_too_short_fails(tmp_path: Path) -> None:
    """Non-functional requirements section with < 3 lines fails."""
    c = _checker(tmp_path, "prd", _PRD_NFR_TOO_SHORT)
    c.check_prd()
    assert any("非功能需求" in e for e in c.errors)


def test_check_prd_missing_priority_fails(tmp_path: Path) -> None:
    """Feature section without P0/P1/P2 priority annotation fails."""
    c = _checker(tmp_path, "prd", _PRD_MISSING_PRIORITY)
    c.check_prd()
    assert any("优先级" in e for e in c.errors)


# ---------------------------------------------------------------------------
# check_arch
# ---------------------------------------------------------------------------

_ARCH_GOOD = """\
### API-001 Login
request:
  method: POST

### M-001 Auth
F-001 authorization module.

### E-001 User
| field | type |
|-------|------|
| id    | int  |
"""


def test_check_arch_pass(tmp_path: Path) -> None:
    """Arch with request, F-NNN mapping, and entity field table passes."""
    c = _checker(tmp_path, "arch", _ARCH_GOOD)
    c.check_arch()
    assert c.errors == []


def test_check_arch_api_missing_request_fails(tmp_path: Path) -> None:
    """API section without 'request:' or event-stream type fails."""
    content = "### API-001 Login\nno request here\n"
    c = _checker(tmp_path, "arch", content)
    c.check_arch()
    assert any("request" in e for e in c.errors)


def test_check_arch_module_missing_f_ref_fails(tmp_path: Path) -> None:
    """Module section without F-NNN reference fails."""
    content = "### M-001 Auth\nno feature mapping.\n"
    c = _checker(tmp_path, "arch", content)
    c.check_arch()
    assert any("模块" in e or "功能映射" in e for e in c.errors)


def test_check_arch_entity_missing_table_fails(tmp_path: Path) -> None:
    """Entity section without a pipe-delimited table fails."""
    content = "### E-001 User\nid and name fields\n"
    c = _checker(tmp_path, "arch", content)
    c.check_arch()
    assert any("实体" in e or "字段" in e for e in c.errors)


def test_check_arch_event_stream_api_passes(tmp_path: Path) -> None:
    """API with type: event-stream is exempt from request: requirement."""
    content = "### API-001 Stream\ntype: event-stream\n"
    c = _checker(tmp_path, "arch", content)
    c.check_arch()
    assert c.errors == []


def test_check_arch_api_input_field_passes(tmp_path: Path) -> None:
    """A capability contract declares inputs as `input:`, not HTTP `request:`."""
    content = "### API-001 解析\ninput:\n  text: str\noutput:\n  tokens: list\n"
    c = _checker(tmp_path, "arch", content)
    c.check_arch()
    assert c.errors == []


def test_check_arch_api_param_table_passes(tmp_path: Path) -> None:
    """A 参数 table satisfies the input-definition requirement."""
    content = "### API-001 解析\n| 参数 | 类型 |\n|------|------|\n| text | str |\n"
    c = _checker(tmp_path, "arch", content)
    c.check_arch()
    assert c.errors == []


def test_check_arch_api_no_input_at_all_still_fails(tmp_path: Path) -> None:
    """An API with neither request/input/参数 nor event-stream still fails."""
    content = "### API-001 Login\nno input definition here\n"
    c = _checker(tmp_path, "arch", content)
    c.check_arch()
    assert any("入参" in e or "request" in e for e in c.errors)


# ---------------------------------------------------------------------------
# check_arch — tech-stack 选型理由
# ---------------------------------------------------------------------------

_ARCH_TECH_EMPTY_RATIONALE = """\
### 1.4 技术栈
| 层次 | 技术 | 选型理由 | 调研来源 |
|------|------|----------|----------|
| 后端 | Python | 类型系统成熟 | tech-eval |
| 认证 | JWT |  | - |
"""

_ARCH_TECH_FILLED_RATIONALE = """\
### 1.4 技术栈
| 层次 | 技术 | 选型理由 | 调研来源 |
|------|------|----------|----------|
| 后端 | Python | 类型系统成熟 | tech-eval |
| 认证 | JWT | 无状态会话标准 | tech-eval |
"""

_ARCH_TECH_NO_RATIONALE_COLUMN = """\
### 技术栈
| 类别 | 选型 | 备注 |
|------|------|------|
| 语言 | Python |  |
"""


def test_check_arch_tech_stack_empty_rationale_warns(tmp_path: Path) -> None:
    """A tech-stack row with a blank 选型理由 cell warns."""
    c = _checker(tmp_path, "arch", _ARCH_TECH_EMPTY_RATIONALE)
    c.check_arch()
    assert any("选型理由" in w for w in c.warnings), c.warnings


def test_check_arch_tech_stack_filled_rationale_no_warn(tmp_path: Path) -> None:
    """Every 选型理由 filled → no warn."""
    c = _checker(tmp_path, "arch", _ARCH_TECH_FILLED_RATIONALE)
    c.check_arch()
    assert not any("选型理由" in w for w in c.warnings), c.warnings


def test_check_arch_tech_stack_no_rationale_column_no_warn(tmp_path: Path) -> None:
    """The terser lite 类别/选型/备注 schema has no 理由 column → not checked."""
    c = _checker(tmp_path, "arch", _ARCH_TECH_NO_RATIONALE_COLUMN)
    c.check_arch()
    assert not any("选型理由" in w for w in c.warnings), c.warnings


def test_check_arch_tech_stack_prose_mention_does_not_false_trigger(tmp_path: Path) -> None:
    """A non-heading prose mention of 技术栈 (no table) must not warn — the
    check anchors on a 技术栈 heading, not on any occurrence of the word."""
    content = "## 1. 概览\n- 附录另有技术栈清单指针，本节无表格。\n"
    c = _checker(tmp_path, "arch", content)
    c.check_arch()
    assert not any("选型理由" in w for w in c.warnings), c.warnings


# ---------------------------------------------------------------------------
# check_id_continuity
# ---------------------------------------------------------------------------


def test_id_continuity_flags_api_gap(tmp_path: Path) -> None:
    """A genuine gap in API- numbering warns."""
    content = "### API-001 A\n\n### API-003 C\n"
    c = _checker(tmp_path, "arch", content)
    c.check_id_continuity()
    assert any("API-002" in w for w in c.warnings), c.warnings


def test_id_continuity_checks_every_arch_prefix(tmp_path: Path) -> None:
    """An arch doc checks every arch prefix (M / API / E)."""
    content = "### M-001 A\n\n### M-003 C\n"
    c = _checker(tmp_path, "arch", content)
    c.check_id_continuity()
    assert any("M-002" in w for w in c.warnings), c.warnings


# ---------------------------------------------------------------------------
# check_dev_plan
# ---------------------------------------------------------------------------

_DEV_PLAN_GOOD = """\
### T-001 Setup
- deliverables: README
- tdd_acceptance:
  - AC-001: Return true on success.
- context_load: arch#§1
"""


def test_check_dev_plan_pass(tmp_path: Path) -> None:
    """Dev plan task with deliverables, tdd_acceptance, and context_load passes."""
    c = _checker(tmp_path, "dev-plan", _DEV_PLAN_GOOD)
    c.check_dev_plan()
    assert c.errors == []


def test_check_dev_plan_missing_deliverables_fails(tmp_path: Path) -> None:
    """Task without deliverables entry fails."""
    content = "### T-001 Setup\n- tdd_acceptance: yes\n- context_load: arch\n"
    c = _checker(tmp_path, "dev-plan", content)
    c.check_dev_plan()
    assert any("deliverables" in e for e in c.errors)


def test_check_dev_plan_missing_tdd_acceptance_fails(tmp_path: Path) -> None:
    """Task without tdd_acceptance entry fails."""
    content = "### T-001 Setup\n- deliverables: README\n- context_load: arch\n"
    c = _checker(tmp_path, "dev-plan", content)
    c.check_dev_plan()
    assert any("tdd_acceptance" in e or "验收" in e for e in c.errors)


def test_check_dev_plan_missing_context_load_warns(tmp_path: Path) -> None:
    """Task without context_load produces a warning (not error)."""
    content = "### T-001 Setup\n- deliverables: README\n- tdd_acceptance: yes\n"
    c = _checker(tmp_path, "dev-plan", content)
    c.check_dev_plan()
    assert any("context_load" in w for w in c.warnings)
    assert not any("context_load" in e for e in c.errors)


def test_check_dev_plan_cyclic_dependency_fails(tmp_path: Path) -> None:
    """Task dependency graph with a cycle fails."""
    content = (
        "### T-001 A\n- deliverables: x\n- tdd_acceptance: yes\n- context_load: y\n"
        "T-002 ─ T-001\n"
        "T-001 ─ T-002\n"
    )
    c = _checker(tmp_path, "dev-plan", content)
    c.check_dev_plan()
    assert any("循环" in e for e in c.errors)


# ---------------------------------------------------------------------------
# _check_ac_observability (called from check_dev_plan)
# ---------------------------------------------------------------------------

_DEV_PLAN_NONOBSERVABLE_AC = """\
### T-001 Feature
- deliverables: code.py
- tdd_acceptance:
  - AC-001: Implement the login module completely.
- context_load: arch
"""

_DEV_PLAN_NO_GWT = """\
### T-001 Feature
- deliverables: code.py
- tdd_acceptance:
  - AC-001: Return the correct token.
- context_load: arch
"""

_DEV_PLAN_GOOD_AC = """\
### T-001 Feature
- deliverables: code.py
- tdd_acceptance:
  - AC-001: Given valid credentials, When login called, Then return token.
- context_load: arch
"""


def test_check_dev_plan_ac_no_observable_verb_warns(tmp_path: Path) -> None:
    """AC text without an observable verb produces a warning."""
    c = _checker(tmp_path, "dev-plan", _DEV_PLAN_NONOBSERVABLE_AC)
    c.check_dev_plan()
    assert any("可观测" in w or "observable" in w.lower() for w in c.warnings)


def test_check_dev_plan_ac_no_gwt_warns(tmp_path: Path) -> None:
    """AC text without GWT keywords produces a GWT warning."""
    c = _checker(tmp_path, "dev-plan", _DEV_PLAN_NO_GWT)
    c.check_dev_plan()
    assert any(
        "Given" in w or "When" in w or "Then" in w or "GWT" in w or "given" in w.lower()
        for w in c.warnings
    )


def test_check_dev_plan_ac_gwt_passes(tmp_path: Path) -> None:
    """AC text with GWT keywords and observable verb produces no warnings."""
    c = _checker(tmp_path, "dev-plan", _DEV_PLAN_GOOD_AC)
    c.check_dev_plan()
    assert c.warnings == []
    assert c.errors == []


_DEV_PLAN_CLI_AC = """\
### T-001 Feature
- deliverables: cli.py
- tdd_acceptance:
  - AC-001: Given 合法参数, When 运行 CLI, Then 输出排序结果并以退出码 0 结束。
- context_load: arch
"""


def test_check_dev_plan_ac_chinese_cli_verbs_pass(tmp_path: Path) -> None:
    """CLI-style Chinese observable verbs (输出/退出) count as observable."""
    c = _checker(tmp_path, "dev-plan", _DEV_PLAN_CLI_AC)
    c.check_dev_plan()
    assert not any("可观测" in w for w in c.warnings), c.warnings


# ---------------------------------------------------------------------------
# check_ui_spec
# ---------------------------------------------------------------------------

_UI_SPEC_GOOD = """\
---
mode: standard
---
## 0. 设计方向
调性: modern, clean

### UC-001 Button
variant: primary
props: size, color
视觉差异: hover state changes background

### P-001 Home
route: /home
UC-001 used here
空间构成: centered layout

色彩: primary blue #0055ff
typography: sans-serif

| Token | Value |
|-------|-------|
| primary | #0055ff |
| secondary | #00aa00 |
| neutral | #888888 |
| error | #cc0000 |
| warning | #ff8800 |
"""

_UI_SPEC_LITE = """\
---
mode: agile-lite
---
### UC-001 Button
变体: primary
Props: size
视觉差异: hover

色彩: #0055ff
typography: yes

| Token | Hex |
|-------|-----|
| p | #001122 |
| s | #334455 |
| n | #667788 |
"""


def test_check_ui_spec_pass_standard(tmp_path: Path) -> None:
    """Standard-mode UI spec with all required sections passes."""
    c = _checker(tmp_path, "ui-spec", _UI_SPEC_GOOD)
    c.check_ui_spec()
    assert c.errors == []


def test_check_ui_spec_pass_lite(tmp_path: Path) -> None:
    """Agile-lite mode requires fewer color tokens; 3 tokens passes."""
    c = _checker(tmp_path, "ui-spec", _UI_SPEC_LITE)
    c.check_ui_spec()
    assert c.errors == []


def test_check_ui_spec_component_missing_variant_fails(tmp_path: Path) -> None:
    """Component section without variant/变体 fails."""
    content = "### UC-001 Btn\nprops: size\n视觉差异: hover\n"
    c = _checker(tmp_path, "ui-spec", content)
    c.check_ui_spec()
    assert any("变体" in e or "variant" in e.lower() for e in c.errors)


def test_check_ui_spec_component_missing_props_fails(tmp_path: Path) -> None:
    """Component section without Props/props/属性 fails."""
    content = "### UC-001 Btn\n变体: primary\n视觉差异: hover\n"
    c = _checker(tmp_path, "ui-spec", content)
    c.check_ui_spec()
    assert any("Props" in e or "props" in e or "属性" in e for e in c.errors)


def test_check_ui_spec_missing_design_dir_fails_standard(tmp_path: Path) -> None:
    """Standard-mode spec without §0 设计方向 section fails."""
    content = (
        "---\nmode: standard\n---\n### UC-001 Btn\n变体: primary\nprops: size\n视觉差异: hover\n"
    )
    c = _checker(tmp_path, "ui-spec", content)
    c.check_ui_spec()
    assert any("设计方向" in e for e in c.errors)


def test_check_ui_spec_no_color_tokens_fails(tmp_path: Path) -> None:
    """A ui-spec with no color token table fails."""
    content = "### UC-001 Btn\n变体: x\nProps: y\n视觉差异: z\n色彩: blue\ntypography: yes\n"
    c = _checker(tmp_path, "ui-spec", content)
    c.check_ui_spec()
    assert any("色彩Token" in e or "Token" in e for e in c.errors)


def test_check_ui_spec_missing_color_warns(tmp_path: Path) -> None:
    """A ui-spec without any color keyword produces a warning."""
    content = "### UC-001 Btn\n变体: x\nProps: y\n视觉差异: z\n"
    c = _checker(tmp_path, "ui-spec", content)
    c.check_ui_spec()
    assert any("色彩" in w for w in c.warnings)


# ---------------------------------------------------------------------------
# check_test_report
# ---------------------------------------------------------------------------

_TEST_REPORT_GOOD = """\
Unit tests cover the service layer.
Integration tests cover the API.
E2E tests cover the user journey.

## 测试用例矩阵
|ID|Case|Result|
|----|------|--------|
|T1|login|PASS|

## 覆盖率目标
Line coverage ≥ 80%
"""


def test_check_test_report_pass(tmp_path: Path) -> None:
    """Test report with unit/integration/E2E and matrix row passes."""
    c = _checker(tmp_path, "test-report", _TEST_REPORT_GOOD)
    c.check_test_report()
    assert c.errors == []


def test_check_test_report_missing_pyramid_layers_fails(tmp_path: Path) -> None:
    """Test report missing E2E layer fails."""
    content = "Unit tests pass.\nIntegration tests pass.\n"
    c = _checker(tmp_path, "test-report", content)
    c.check_test_report()
    assert any("E2E" in e for e in c.errors)


def test_check_test_report_missing_all_layers_fails(tmp_path: Path) -> None:
    """Test report with no recognized layers fails with all three listed."""
    content = "All tests passed.\n"
    c = _checker(tmp_path, "test-report", content)
    c.check_test_report()
    assert any("Unit" in e for e in c.errors)
    assert any("Integration" in e for e in c.errors)


def test_check_test_report_empty_matrix_fails(tmp_path: Path) -> None:
    """Test report with a matrix heading but no data rows fails."""
    content = "Unit Integration E2E\n## 测试用例矩阵\n| ID | Case |\n|----|------|\n"
    c = _checker(tmp_path, "test-report", content)
    c.check_test_report()
    assert any("矩阵" in e for e in c.errors)


_TEST_REPORT_STANDARD_TABLE = """\
Unit tests cover the service layer.
Integration tests cover the API.
E2E tests cover the user journey.

## 测试用例矩阵

| 用例ID | 名称 | 结果 |
|--------|------|------|
| TC-01 | 摄氏转华氏 | PASS |
| TC-02 | 非法输入报错 | PASS |

## 覆盖率目标
Line coverage ≥ 80%
"""


def test_check_test_report_standard_format_matrix_with_rows_passes(tmp_path: Path) -> None:
    """Standard `| cell |` rows (spaces after pipes, CJK content) count as data."""
    c = _checker(tmp_path, "test-report", _TEST_REPORT_STANDARD_TABLE)
    c.check_test_report()
    assert not any("矩阵" in e for e in c.errors), c.errors


def test_check_test_report_coverage_no_number_warns(tmp_path: Path) -> None:
    """Coverage section with no percentage value produces a warning."""
    content = "Unit Integration E2E\n## 覆盖率目标\nCoverage should be high.\n"
    c = _checker(tmp_path, "test-report", content)
    c.check_test_report()
    assert any("覆盖率" in w for w in c.warnings)


# ---------------------------------------------------------------------------
# check_deploy_spec
# ---------------------------------------------------------------------------

_DEPLOY_SPEC_GOOD = """\
## 构建流程
Run docker build -t app .

## 环境配置
dev: local
prod: cloud

## 发布检查清单
- [x] Tests pass
- [ ] Notify team
"""


def test_check_deploy_spec_pass(tmp_path: Path) -> None:
    """Complete deploy spec passes all checks."""
    c = _checker(tmp_path, "deploy-spec", _DEPLOY_SPEC_GOOD)
    c.check_deploy_spec()
    assert c.errors == []
    assert c.warnings == []


def test_check_deploy_spec_short_build_section_fails(tmp_path: Path) -> None:
    """Build process section with < 10 chars of content fails."""
    content = "## 构建流程\nok\n"
    c = _checker(tmp_path, "deploy-spec", content)
    c.check_deploy_spec()
    assert any("构建" in e for e in c.errors)


def test_check_deploy_spec_env_missing_prod_warns(tmp_path: Path) -> None:
    """Environment section with only dev (no prod) warns."""
    content = "## 构建流程\nRun docker build -t app .\n## 环境配置\ndev: local\n"
    c = _checker(tmp_path, "deploy-spec", content)
    c.check_deploy_spec()
    assert any("prod" in w or "环境" in w for w in c.warnings)


def test_check_deploy_spec_checklist_too_few_fails(tmp_path: Path) -> None:
    """Release checklist with < 2 items fails."""
    content = "## 构建流程\nRun docker build -t app .\n## 发布检查清单\n- [x] Done\n"
    c = _checker(tmp_path, "deploy-spec", content)
    c.check_deploy_spec()
    assert any("检查清单" in e for e in c.errors)


# ---------------------------------------------------------------------------
# check_research
# ---------------------------------------------------------------------------

_RESEARCH_GOOD = """\
## 调研方法
web-search

## 结论
We found that the approach works well.
"""


def test_check_research_pass(tmp_path: Path) -> None:
    """Research doc with method keyword and substantive conclusion passes."""
    c = _checker(tmp_path, "research", _RESEARCH_GOOD)
    c.check_research()
    assert c.errors == []
    assert c.warnings == []


def test_check_research_no_method_warns(tmp_path: Path) -> None:
    """Research doc without web-search/doc-lookup/user-interview warns."""
    content = "## 调研\nWe looked at stuff.\n## 结论\nIt seems to work fine.\n"
    c = _checker(tmp_path, "research", content)
    c.check_research()
    assert any("web-search" in w or "调研" in w.lower() for w in c.warnings)


def test_check_research_short_conclusion_fails(tmp_path: Path) -> None:
    """Research doc with a very short conclusion section fails."""
    content = "web-search was used.\n## 结论\nOK.\n"
    c = _checker(tmp_path, "research", content)
    c.check_research()
    assert any("结论" in e for e in c.errors)


# ---------------------------------------------------------------------------
# check_changelog
# ---------------------------------------------------------------------------

_CHANGELOG_GOOD = """\
## [1.0.0]
### Added
- Initial release
"""


def test_check_changelog_pass(tmp_path: Path) -> None:
    """Changelog with version entry and Added/Changed/Fixed section passes."""
    c = _checker(tmp_path, "changelog", _CHANGELOG_GOOD)
    c.check_changelog()
    assert c.errors == []
    assert c.warnings == []


def test_check_changelog_no_versions_fails(tmp_path: Path) -> None:
    """Changelog with no ## [version] entries fails."""
    content = "# CHANGELOG\nSome changes happened.\n"
    c = _checker(tmp_path, "changelog", content)
    c.check_changelog()
    assert any("版本" in e for e in c.errors)


def test_check_changelog_missing_category_warns(tmp_path: Path) -> None:
    """Version section without Added/Changed/Fixed warns."""
    content = "## [1.0.0]\nChanges were made.\n"
    c = _checker(tmp_path, "changelog", content)
    c.check_changelog()
    assert any("Added" in w or "Changed" in w or "Fixed" in w for w in c.warnings)


# ---------------------------------------------------------------------------
# check_no_todo — per-line [ASSUMPTION] exemption
# ---------------------------------------------------------------------------


def test_check_no_todo_unannotated_fails(tmp_path: Path) -> None:
    c = _checker(tmp_path, "prd", "## 1\n- TODO: wire this up\n")
    c.check_no_todo()
    assert any("TODO" in e for e in c.errors)


def test_check_no_todo_same_line_assumption_is_exempt(tmp_path: Path) -> None:
    c = _checker(tmp_path, "prd", "## 1\n- TODO: pick a default [ASSUMPTION] use 30s\n")
    c.check_no_todo()
    assert c.errors == []


def test_check_no_todo_unrelated_assumption_does_not_cancel(tmp_path: Path) -> None:
    # A global count subtraction would cancel the TODO against the unrelated
    # [ASSUMPTION] on another line; per-line determination still fails.
    content = "## 1\n- TODO: wire this up\n- 默认超时 [ASSUMPTION] 30s\n"
    c = _checker(tmp_path, "prd", content)
    c.check_no_todo()
    assert any("TODO" in e for e in c.errors)


# ---------------------------------------------------------------------------
# check_dev_plan — walking-skeleton gate (external_oracles)
# ---------------------------------------------------------------------------

_ARCH_WITH_ORACLES = """\
## 1. 架构概览

### 1.5 外部消费边界 (external_oracles)
| ID | 外部系统 | 对产物的变换行为 | 验证方式 |
|----|---------|----------------|---------|
| EO-001 | 外部编辑器 | 粘贴过滤剥离样式 | 真机粘贴比对 |

## 2. 模块划分
"""

_ARCH_ORACLES_NA = """\
## 1. 架构概览

### 1.5 外部消费边界 (external_oracles)
N/A

## 2. 模块划分
"""

_ARCH_ORACLES_PLACEHOLDER = """\
## 1. 架构概览

### 1.5 外部消费边界 (external_oracles)
| ID | 外部系统 | 对产物的变换行为 | 验证方式 |
|----|---------|----------------|---------|
| EO-001 | {系统名} | {变换行为} | {验证方式} |

## 2. 模块划分
"""

_DEV_PLAN_WITH_SKELETON = """\
### T-001 walking skeleton tracer
- walking_skeleton: true
- deliverables: src/tracer.py
- tdd_acceptance:
  - AC-001: Given 最小产物 When 经真实通道送入外部系统 Then 返回比对差异为空。
- context_load: arch#§1
"""


def test_dev_plan_walking_skeleton_missing_fails(tmp_path: Path) -> None:
    """Arch declares external_oracles → dev-plan without walking_skeleton card fails."""
    (tmp_path / "arch-app.md").write_text(_ARCH_WITH_ORACLES, encoding="utf-8")
    c = _checker(tmp_path, "dev-plan", _DEV_PLAN_GOOD)
    c.check_dev_plan()
    assert any("walking_skeleton" in e for e in c.errors)
    assert any("EO-001" in e for e in c.errors)


def test_dev_plan_walking_skeleton_present_passes(tmp_path: Path) -> None:
    """Arch declares external_oracles and dev-plan carries the card → no error."""
    (tmp_path / "arch-app.md").write_text(_ARCH_WITH_ORACLES, encoding="utf-8")
    c = _checker(tmp_path, "dev-plan", _DEV_PLAN_WITH_SKELETON)
    c.check_dev_plan()
    assert not any("walking_skeleton" in e for e in c.errors)


def test_dev_plan_no_oracles_section_skips(tmp_path: Path) -> None:
    """Arch without external_oracles section → gate does not fire."""
    (tmp_path / "arch-app.md").write_text("## 1. 架构概览\n\n## 2. 模块划分\n", encoding="utf-8")
    c = _checker(tmp_path, "dev-plan", _DEV_PLAN_GOOD)
    c.check_dev_plan()
    assert not any("walking_skeleton" in e for e in c.errors)


def test_dev_plan_oracles_na_skips(tmp_path: Path) -> None:
    """external_oracles section marked N/A → gate does not fire."""
    (tmp_path / "arch-app.md").write_text(_ARCH_ORACLES_NA, encoding="utf-8")
    c = _checker(tmp_path, "dev-plan", _DEV_PLAN_GOOD)
    c.check_dev_plan()
    assert not any("walking_skeleton" in e for e in c.errors)


def test_dev_plan_oracles_placeholder_row_skips(tmp_path: Path) -> None:
    """Template placeholder rows (braces unfilled) do not count as declared oracles."""
    (tmp_path / "arch-app.md").write_text(_ARCH_ORACLES_PLACEHOLDER, encoding="utf-8")
    c = _checker(tmp_path, "dev-plan", _DEV_PLAN_GOOD)
    c.check_dev_plan()
    assert not any("walking_skeleton" in e for e in c.errors)


def test_dev_plan_no_arch_file_skips(tmp_path: Path) -> None:
    """No arch document present → gate does not fire."""
    c = _checker(tmp_path, "dev-plan", _DEV_PLAN_GOOD)
    c.check_dev_plan()
    assert not any("walking_skeleton" in e for e in c.errors)
