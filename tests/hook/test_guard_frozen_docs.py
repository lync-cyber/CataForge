"""guard_frozen_docs PreToolUse hook — the unattended file-edit deny layer.

Blocks Write / Edit to frozen upstream docs (PRD / ARCH / UI-SPEC / DEV-PLAN /
BRIEF) only when ``CATAFORGE_UNATTENDED`` is set, and is a no-op otherwise.
Under ``context.mode = markdown`` a status-only Edit to a task-carrying doc
(dev-plan / brief) passes — the doc is the task-status source of truth there.
Driven through the real module entry point over stdin.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _run_guard(
    file_path: str,
    *,
    unattended: bool,
    tool: str = "Edit",
    old: str | None = None,
    new: str | None = None,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    env = {**os.environ}
    env.pop("CATAFORGE_UNATTENDED", None)
    if unattended:
        env["CATAFORGE_UNATTENDED"] = "1"
    tool_input: dict[str, str] = {"file_path": file_path}
    if old is not None:
        tool_input["old_string"] = old
    if new is not None:
        tool_input["new_string"] = new
    payload: dict[str, object] = {"tool_name": tool, "tool_input": tool_input}
    if cwd is not None:
        payload["cwd"] = str(cwd)
    return subprocess.run(
        [sys.executable, "-m", "cataforge.runtime.hook.scripts.guard_frozen_docs"],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
    )


def _project(tmp_path: Path, mode: str) -> Path:
    (tmp_path / ".cataforge").mkdir()
    (tmp_path / ".cataforge" / "framework.json").write_text(
        json.dumps({"context": {"mode": mode}}), encoding="utf-8"
    )
    return tmp_path


def test_blocks_dev_plan_edit() -> None:
    r = _run_guard("docs/dev-plan/dev-plan.md", unattended=True)
    assert r.returncode == 2
    assert "冻结" in r.stderr


def test_blocks_prd_arch_uispec() -> None:
    for path in (
        "docs/prd/prd.md",
        "docs/arch/arch.md",
        "docs/ui-spec/ui-spec.md",
    ):
        assert _run_guard(path, unattended=True).returncode == 2, path


def test_blocks_extra_file_in_frozen_dir() -> None:
    # Any .md under a frozen doc_type dir is blocked, not just the canonical name.
    r = _run_guard("docs/dev-plan/dev-plan-extra.md", unattended=True)
    assert r.returncode == 2


def test_blocks_flat_and_lite_variants() -> None:
    assert _run_guard("docs/dev-plan.md", unattended=True).returncode == 2
    assert _run_guard("docs/prd-lite.md", unattended=True).returncode == 2


def test_blocks_prototype_brief() -> None:
    # agile-prototype: brief.md holds the frozen task cards during the loop, so
    # both the flat file and the subdir variant must be blocked.
    assert _run_guard("docs/brief.md", unattended=True).returncode == 2
    assert _run_guard("docs/brief/brief-x.md", unattended=True).returncode == 2


def test_blocks_case_variants() -> None:
    # Windows / macOS default filesystems are case-insensitive: docs/BRIEF.MD
    # physically edits docs/brief.md, so case variants must match the frozen set.
    assert _run_guard("docs/BRIEF.MD", unattended=True).returncode == 2
    assert _run_guard("docs/Brief.md", unattended=True).returncode == 2
    assert _run_guard("docs/Dev-Plan/dev-plan.md", unattended=True).returncode == 2


def test_blocks_write_tool_too() -> None:
    # The Write tool (not just Edit) maps to file_edit and must be caught.
    r = _run_guard("docs/dev-plan/dev-plan.md", unattended=True, tool="Write")
    assert r.returncode == 2


def test_blocks_windows_absolute_path() -> None:
    r = _run_guard(r"C:\proj\docs\dev-plan\dev-plan.md", unattended=True)
    assert r.returncode == 2


def test_allows_code_review_report() -> None:
    # The loop legitimately writes code-review reports under docs/reviews/.
    r = _run_guard("docs/reviews/code/CODE-REVIEW-T-1-r1.md", unattended=True)
    assert r.returncode == 0


def test_allows_source_and_tests() -> None:
    assert _run_guard("src/pkg/mod.py", unattended=True).returncode == 0
    assert _run_guard("tests/test_mod.py", unattended=True).returncode == 0


def test_no_false_match_on_lookalike_dirs() -> None:
    # docs/dev-planner/ and docs/prd-notes.md are not the frozen planning docs.
    assert _run_guard("docs/dev-planner/notes.md", unattended=True).returncode == 0
    assert _run_guard("docs/prd-notes.md", unattended=True).returncode == 0
    # docs/brief-notes.md is not the brief itself.
    assert _run_guard("docs/brief-notes.md", unattended=True).returncode == 0


def test_no_op_when_not_unattended() -> None:
    r = _run_guard("docs/dev-plan/dev-plan.md", unattended=False)
    assert r.returncode == 0


# --- markdown-mode status carve-out ---------------------------------------
# Under context.mode=markdown the doc is the task-status source of truth
# (remove-hybrid two-state model), so a status-only Edit must pass — it is the
# loop's only legal way to mark a card done. Everything else still blocks.


def test_markdown_mode_allows_status_field_edit(tmp_path: Path) -> None:
    root = _project(tmp_path, "markdown")
    r = _run_guard(
        "docs/brief.md",
        unattended=True,
        old="- status: pending",
        new="- status: done",
        cwd=root,
    )
    assert r.returncode == 0, r.stderr


def test_markdown_mode_allows_sprint_table_cell(tmp_path: Path) -> None:
    root = _project(tmp_path, "markdown")
    r = _run_guard(
        "docs/dev-plan/dev-plan.md",
        unattended=True,
        old="| T-001 | 登录 | pending |",
        new="| T-001 | 登录 | done |",
        cwd=root,
    )
    assert r.returncode == 0, r.stderr


def test_markdown_mode_blocks_content_edit(tmp_path: Path) -> None:
    root = _project(tmp_path, "markdown")
    r = _run_guard(
        "docs/brief.md",
        unattended=True,
        old="- AC-001: Given A, When B, Then C",
        new="- AC-001: Given A, When B, Then D",
        cwd=root,
    )
    assert r.returncode == 2


def test_markdown_mode_blocks_line_insertion(tmp_path: Path) -> None:
    # A status flip that smuggles in an extra line is content, not state.
    root = _project(tmp_path, "markdown")
    r = _run_guard(
        "docs/brief.md",
        unattended=True,
        old="- status: pending",
        new="- status: done\n- 备注: 顺手加一行",
        cwd=root,
    )
    assert r.returncode == 2


def test_markdown_mode_blocks_multi_cell_table_edit(tmp_path: Path) -> None:
    root = _project(tmp_path, "markdown")
    r = _run_guard(
        "docs/dev-plan/dev-plan.md",
        unattended=True,
        old="| T-001 | 登录 | pending |",
        new="| T-001 | 登录并鉴权 | done |",
        cwd=root,
    )
    assert r.returncode == 2


def test_markdown_mode_write_still_blocked(tmp_path: Path) -> None:
    # A full-file Write is indistinguishable from a rewrite — no carve-out.
    root = _project(tmp_path, "markdown")
    r = _run_guard("docs/brief.md", unattended=True, tool="Write", cwd=root)
    assert r.returncode == 2


def test_markdown_mode_carveout_not_for_prd(tmp_path: Path) -> None:
    # PRD / ARCH / UI-SPEC carry no execution status — hard-blocked in both modes.
    root = _project(tmp_path, "markdown")
    r = _run_guard(
        "docs/prd.md",
        unattended=True,
        old="- status: pending",
        new="- status: done",
        cwd=root,
    )
    assert r.returncode == 2


def test_graph_mode_blocks_status_edit(tmp_path: Path) -> None:
    # graph mode: status goes through `cataforge context update`; the exported
    # markdown is a derived view, so even a status-only Edit stays blocked.
    root = _project(tmp_path, "graph")
    r = _run_guard(
        "docs/brief.md",
        unattended=True,
        old="- status: pending",
        new="- status: done",
        cwd=root,
    )
    assert r.returncode == 2


def test_no_project_root_fails_closed(tmp_path: Path) -> None:
    # No .cataforge/ anywhere up the chain → mode unknown → keep blocking.
    r = _run_guard(
        "docs/brief.md",
        unattended=True,
        old="- status: pending",
        new="- status: done",
        cwd=tmp_path,
    )
    assert r.returncode == 2
