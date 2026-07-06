"""Frozen-upstream preflight for the unattended building-loop."""

from __future__ import annotations

from pathlib import Path

from cataforge.application.unattended_preflight import preflight_frozen_upstream

_FROZEN = """\
---
id: dev-plan
doc_type: dev-plan
status: approved
---
## sprint-1
- T-1 AC: 用户能登录，返回 200。
"""


def _write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_refuses_when_no_devplan(tmp_path: Path) -> None:
    assert preflight_frozen_upstream(tmp_path, "sprint-1") is not None


def test_refuses_draft_devplan(tmp_path: Path) -> None:
    _write(tmp_path, "docs/dev-plan/dev-plan.md", _FROZEN.replace("approved", "draft"))
    reason = preflight_frozen_upstream(tmp_path, "sprint-1")
    assert reason is not None and "冻结" in reason


def test_refuses_when_sprint_absent(tmp_path: Path) -> None:
    _write(tmp_path, "docs/dev-plan/dev-plan.md", _FROZEN)
    reason = preflight_frozen_upstream(tmp_path, "sprint-9")
    assert reason is not None and "sprint-9" in reason


def test_refuses_on_unresolved_placeholder(tmp_path: Path) -> None:
    _write(tmp_path, "docs/dev-plan/dev-plan.md", _FROZEN + "- T-2 AC: TBD\n")
    reason = preflight_frozen_upstream(tmp_path, "sprint-1")
    assert reason is not None and "TBD" in reason


def test_refuses_when_no_status(tmp_path: Path) -> None:
    body = "## sprint-1\n- T-1 AC: 具体断言。\n"
    _write(tmp_path, "docs/dev-plan/dev-plan.md", body)  # no frontmatter
    assert preflight_frozen_upstream(tmp_path, "sprint-1") is not None


def test_passes_on_frozen_clean_devplan(tmp_path: Path) -> None:
    _write(tmp_path, "docs/dev-plan/dev-plan.md", _FROZEN)
    assert preflight_frozen_upstream(tmp_path, "sprint-1") is None


def test_annotated_assumption_is_not_a_placeholder(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "docs/dev-plan/dev-plan.md",
        _FROZEN + "- T-2 AC: 超时默认值 [ASSUMPTION] TBD→30s。\n",
    )
    assert preflight_frozen_upstream(tmp_path, "sprint-1") is None


def test_placeholder_in_any_dev_plan_file_is_caught(tmp_path: Path) -> None:
    # A clean file must not mask a TBD in another file under docs/dev-plan/.
    _write(tmp_path, "docs/dev-plan/dev-plan-part-1.md", _FROZEN)
    _write(
        tmp_path,
        "docs/dev-plan/dev-plan-part-2.md",
        "---\nid: dev-plan-2\ndoc_type: dev-plan\nstatus: approved\n---\n- T-9 AC: FIXME\n",
    )
    reason = preflight_frozen_upstream(tmp_path, "sprint-1")
    assert reason is not None and "FIXME" in reason
