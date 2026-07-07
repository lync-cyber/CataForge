"""Frozen-upstream preflight for the unattended building-loop."""

from __future__ import annotations

from pathlib import Path

from cataforge.application.unattended_preflight import (
    preflight_frozen_upstream,
    preflight_prototype_brief,
)

_FROZEN = """\
---
id: dev-plan
doc_type: dev-plan
status: approved
---
## sprint-1
- T-1 AC: 用户能登录，返回 200。
"""

# agile-prototype brief: no doc-review approval gate exists in the mode, so the
# brief stays status: draft — the prototype preflight must NOT require approved.
_BRIEF = """\
---
id: brief-x
doc_type: brief
status: draft
---
## 5. 开发任务
### T-001: 温度换算
- tdd_acceptance:
  - [ ] AC-001: Given 摄氏度, When 换算, Then 返回华氏度。
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


# --- agile-prototype brief preflight ---------------------------------------


def test_prototype_refuses_when_no_brief(tmp_path: Path) -> None:
    assert preflight_prototype_brief(tmp_path) is not None


def test_prototype_passes_on_flat_brief(tmp_path: Path) -> None:
    _write(tmp_path, "docs/brief.md", _BRIEF)
    assert preflight_prototype_brief(tmp_path) is None


def test_prototype_passes_on_subdir_brief(tmp_path: Path) -> None:
    _write(tmp_path, "docs/brief/brief-x.md", _BRIEF)
    assert preflight_prototype_brief(tmp_path) is None


def test_prototype_does_not_require_approved(tmp_path: Path) -> None:
    # draft is the brief's steady state in agile-prototype (checkpoints=none);
    # requiring approved would refuse every real prototype build.
    _write(tmp_path, "docs/brief.md", _BRIEF)
    assert "draft" in _BRIEF
    assert preflight_prototype_brief(tmp_path) is None


def test_prototype_refuses_without_task_section(tmp_path: Path) -> None:
    body = "---\nid: brief-x\ndoc_type: brief\nstatus: draft\n---\n## 1. 目标\n- 做个原型。\n"
    _write(tmp_path, "docs/brief.md", body)
    reason = preflight_prototype_brief(tmp_path)
    assert reason is not None and "开发任务" in reason


def test_prototype_refuses_on_unresolved_placeholder(tmp_path: Path) -> None:
    _write(tmp_path, "docs/brief.md", _BRIEF + "- T-002 AC: TBD\n")
    reason = preflight_prototype_brief(tmp_path)
    assert reason is not None and "TBD" in reason


def test_prototype_refuses_raw_template_heading(tmp_path: Path) -> None:
    # A brief dropped from the raw template still reads `### T-001: {任务名}` —
    # brace placeholders the TODO/TBD/FIXME rule cannot see. Building against
    # placeholder cards is undefined behavior, so the gate must refuse.
    body = (
        "---\nid: brief-x\ndoc_type: brief\nstatus: draft\n---\n"
        "## 5. 开发任务\n### T-001: {任务名}\n- **目标**: {一句话}\n"
    )
    _write(tmp_path, "docs/brief.md", body)
    reason = preflight_prototype_brief(tmp_path)
    assert reason is not None and "占位符" in reason


def test_prototype_allows_braces_outside_headings(tmp_path: Path) -> None:
    # Heading-only scope: JSON braces in a §4 code block or a body line must
    # not false-reject a genuinely filled brief.
    body = _BRIEF + '\n## 4. 数据结构\n```\n{"celsius": 25.0}\n```\n'
    _write(tmp_path, "docs/brief.md", body)
    assert preflight_prototype_brief(tmp_path) is None
