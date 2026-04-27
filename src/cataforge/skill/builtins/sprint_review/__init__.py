"""Built-in sprint-review skill.

``CHECKS_MANIFEST`` mirrors the actual structural checks executed by
``sprint_check.py``. ``framework-review`` cross-checks this list against
the prose ``## Layer 1 检查项`` section in
``.cataforge/skills/sprint-review/SKILL.md``; any divergence FAILs.
"""

from __future__ import annotations

CHECKS_MANIFEST: tuple[dict[str, str], ...] = (
    {
        "id": "task_status_done",
        "title": "Sprint 任务表中所有任务状态 = done",
        "severity": "fail",
    },
    {
        "id": "deliverables_exist",
        "title": "每个任务 deliverables 中声明的文件路径在磁盘上存在",
        "severity": "fail",
    },
    {
        "id": "ac_coverage",
        "title": "tdd_acceptance 中的 AC-NNN 在 tests/ 目录下有引用",
        "severity": "fail",
    },
    {
        "id": "unplanned_files",
        "title": "src/ 中存在但不属于任何任务 deliverables 的新文件 (gold-plating 信号)",
        "severity": "warn",
    },
    {
        "id": "code_review_present",
        "title": "每个任务有对应的 docs/reviews/code/CODE-REVIEW-{task_id}-*.md",
        "severity": "fail",
    },
)
