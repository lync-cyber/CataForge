"""Unit + green-state tests for the scripts/checks anti-rot guards.

The guards are standalone scripts that `from _common import …`, so they must
be imported with `scripts/checks` as `sys.path[0]` (the same invariant
run_local / pre-commit rely on when running them by file path). Two layers:

  - detection logic exercised on synthetic inputs (the regex / AST / helpers),
  - a green-state smoke layer asserting each guard's `main()` returns 0 on the
    current repo, locking in the "存量零命中" acceptance for the coverage
    expansion and the new probes.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKS_DIR = REPO_ROOT / "scripts" / "checks"
sys.path.insert(0, str(CHECKS_DIR))

import _common  # noqa: E402
import check_doc_structure  # noqa: E402
import check_markdown_link_resolution as link_guard  # noqa: E402
import check_no_design_residue as residue_guard  # noqa: E402
import check_ssot_reconciliation as ssot_guard  # noqa: E402

# --- _common helpers ---------------------------------------------------------


def test_iter_scannable_lines_skips_code_fence_and_frontmatter() -> None:
    text = "\n".join(
        [
            "---",
            "version: 1.2.3 起",  # frontmatter — skipped
            "---",
            "body line",  # yielded
            "```",
            "fenced 原方案",  # fence — skipped
            "```",
            "tail line",  # yielded
        ]
    )
    yielded = [line for _, line in _common.iter_scannable_lines(text)]
    assert yielded == ["body line", "tail line"]


def test_iter_scannable_lines_keeps_line_numbers_accurate() -> None:
    text = "a\n```\nb\n```\nc"
    nums = [n for n, _ in _common.iter_scannable_lines(text)]
    assert nums == [1, 5]  # 'a' at 1, 'c' at 5; fence + b skipped


def test_make_escape_hatch_is_case_insensitive() -> None:
    hatch = _common.make_escape_hatch("allow-design-residue")
    assert _common.is_whitelisted_for("x <!-- Allow-Design-Residue: y -->", hatch)
    assert not _common.is_whitelisted_for("plain line", hatch)


# --- design-residue narrative anchors ---------------------------------------


@pytest.mark.parametrize(
    "line",
    [
        "原方案 X 改为 Y",
        "该阈值收紧自 N≥3",
        "不再使用旧的 dispatch 表",
        "该 Skill 重命名为 foo",
    ],
)
def test_design_residue_narrative_anchors_fire(line: str) -> None:
    assert any(p.search(line) for _, p in residue_guard.FORBIDDEN)


@pytest.mark.parametrize(
    "line",
    [
        "由 draft 改为 approved",  # bare 改为 — must NOT fire
        "应改为契约定义值",
        "状态机将状态改为完成",
    ],
)
def test_design_residue_does_not_fire_on_bare_gaizhao(line: str) -> None:
    assert not any(p.search(line) for _, p in residue_guard.FORBIDDEN)


# --- doc-structure heading + table-cell numbering ---------------------------


def test_doc_structure_flags_non_standard_heading() -> None:
    issues = check_doc_structure.check_non_standard_numbering(["### 3a. Title"])
    assert issues and issues[0][1] == "non-standard-step"


def test_doc_structure_flags_table_cell_numbering() -> None:
    issues = check_doc_structure.check_non_standard_numbering(["| 3b. step | x |"])
    assert issues and issues[0][1] == "non-standard-step-in-table"


def test_doc_structure_allows_hierarchical_heading() -> None:
    # `### 3.1` is digit.digit, a legitimate hierarchical section number.
    assert check_doc_structure.check_non_standard_numbering(["### 3.1 Title"]) == []


# --- markdown link resolution ------------------------------------------------


def test_link_target_skips_external_and_anchor() -> None:
    assert link_guard.link_target_path("https://example.com") is None
    assert link_guard.link_target_path("#section") is None


def test_link_target_relative_vs_repo_root() -> None:
    rel = link_guard.link_target_path("references/foo.md")
    assert rel is not None and not rel.is_absolute()
    rooted = link_guard.link_target_path(".cataforge/rules/COMMON-RULES.md")
    assert rooted is not None and rooted.is_absolute()


def test_link_target_strips_title_and_anchor() -> None:
    assert link_guard.link_target_path('foo.md#sec "title"') == Path("foo.md")


# --- SSOT reconciliation probes ---------------------------------------------


def test_report_add_ids_extracts_multiline_literal() -> None:
    src = 'report.add(\n    "B6_hook_script_reachability",\n    "FAIL",\n)'
    assert ssot_guard._report_add_ids(ast.parse(src)) == ["B6_hook_script_reachability"]


def test_report_add_ids_ignores_non_report_calls() -> None:
    src = 'other.add("X")\nreport.run("Y")'
    assert ssot_guard._report_add_ids(ast.parse(src)) == []


def test_platform_features_reconcile_clean() -> None:
    assert ssot_guard._check_platform_features() == []


def test_framework_review_ids_all_registered() -> None:
    assert ssot_guard._check_framework_review_ids() == []


# --- green-state smoke: every guard passes on the current repo ---------------


@pytest.mark.parametrize(
    "module_name",
    [
        "check_no_design_residue",
        "check_no_language_coupling",
        "check_doc_structure",
        "check_markdown_link_resolution",
        "check_ssot_reconciliation",
        "check_run_local_coverage",
        "check_orphan_cli_capabilities",
        "check_skill_count",
    ],
)
def test_guard_is_green_on_repo(module_name: str) -> None:
    module = __import__(module_name)
    assert module.main() == 0
