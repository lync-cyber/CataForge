"""guard_frozen_docs PreToolUse hook — the unattended file-edit deny layer.

Blocks Write / Edit to frozen upstream docs (PRD / ARCH / UI-SPEC / DEV-PLAN)
only when ``CATAFORGE_UNATTENDED`` is set, and is a no-op otherwise. Driven
through the real module entry point over stdin.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys


def _run_guard(
    file_path: str, *, unattended: bool, tool: str = "Edit"
) -> subprocess.CompletedProcess[str]:
    env = {**os.environ}
    env.pop("CATAFORGE_UNATTENDED", None)
    if unattended:
        env["CATAFORGE_UNATTENDED"] = "1"
    payload = json.dumps({"tool_name": tool, "tool_input": {"file_path": file_path}})
    return subprocess.run(
        [sys.executable, "-m", "cataforge.runtime.hook.scripts.guard_frozen_docs"],
        input=payload,
        capture_output=True,
        text=True,
        env=env,
    )


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


def test_no_op_when_not_unattended() -> None:
    r = _run_guard("docs/dev-plan/dev-plan.md", unattended=False)
    assert r.returncode == 0
