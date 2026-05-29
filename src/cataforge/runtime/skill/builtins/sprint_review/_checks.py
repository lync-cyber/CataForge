"""Sprint completion structural checks (Layer 1 helpers)."""

from __future__ import annotations

import collections
import fnmatch
import os

from cataforge.core.types import Severity
from cataforge.runtime.skill.builtins._shared import Issue
from cataforge.runtime.skill.builtins.sprint_review.ignore import (
    IgnoreSpec,
    list_candidate_files,
)


def _issue(
    severity: Severity,
    category: str,
    message: str,
    *,
    task: str | None = None,
    path: str | None = None,
) -> Issue:
    return Issue(severity, category, message, task=task, path=path)


def check_task_status(tasks: list[dict]) -> list[Issue]:
    issues: list[Issue] = []
    for task in tasks:
        if task["status"] != "done":
            issues.append(
                _issue(
                    Severity.HIGH,
                    "task_status_done",
                    f"任务 {task['id']} 状态为 '{task['status']}'，期望 'done'",
                    task=task["id"],
                )
            )
    return issues


def check_deliverables(
    tasks: list[dict],
    *,
    accept_alternation: bool = False,
) -> list[Issue]:
    """Check each deliverable exists.

    When *accept_alternation* is true, a ``A | B`` entry passes if any
    candidate exists. Without the flag, the literal ``"A | B"`` string is
    treated as a single (non-existent) path — preserving prior behavior.
    """
    issues: list[Issue] = []
    for task in tasks:
        for path in task["deliverables"]:
            if accept_alternation and "|" in path:
                candidates = [p.strip() for p in path.split("|") if p.strip()]
                if not any(os.path.exists(c) for c in candidates):
                    issues.append(
                        _issue(
                            Severity.HIGH,
                            "deliverables_exist",
                            f"任务 {task['id']} 交付物所有候选均缺失: {path}",
                            task=task["id"],
                            path=path,
                        )
                    )
                continue
            if not os.path.exists(path):
                issues.append(
                    _issue(
                        Severity.HIGH,
                        "deliverables_exist",
                        f"任务 {task['id']} 交付物缺失: {path}",
                        task=task["id"],
                        path=path,
                    )
                )
    return issues


def check_ac_coverage(tasks: list[dict], test_dir: str) -> list[Issue]:
    issues: list[Issue] = []
    if not os.path.isdir(test_dir):
        issues.append(
            _issue(
                Severity.MEDIUM,
                "ac_coverage",
                f"测试目录不存在: {test_dir}",
                path=test_dir,
            )
        )
        return issues
    test_content = ""
    for root, _, files in os.walk(test_dir):
        for f in files:
            filepath = os.path.join(root, f)
            try:
                with open(filepath, encoding="utf-8", errors="replace") as fh:
                    test_content += fh.read() + "\n"
            except (OSError, UnicodeDecodeError):
                continue
    for task in tasks:
        for ac_id in task["tdd_acceptance"]:
            if ac_id not in test_content:
                issues.append(
                    _issue(
                        Severity.HIGH,
                        "ac_coverage",
                        f"任务 {task['id']} 的 {ac_id} 在 {test_dir} 中无测试引用",
                        task=task["id"],
                    )
                )
    return issues


def check_unplanned_files(
    tasks: list[dict],
    src_dirs: list[str],
    *,
    respect_gitignore: bool,
    ignore_spec: IgnoreSpec,
    glob_whitelist: list[str] | None = None,
) -> list[Issue]:
    """Detect gold-plating: files under ``src_dirs`` not in any deliverable.

    Candidate enumeration honours .gitignore (when in a git repo and
    ``respect_gitignore`` is true) plus ``ignore_spec``. Files matching
    the deliverables list — or sitting under a deliverable directory —
    are filtered out.

    *glob_whitelist* (from ``project_features.unplanned_glob_patterns``)
    further filters out files whose normalised path matches any fnmatch
    pattern. Use for project-wide test/helper conventions like
    ``**/*.test.ts`` or ``**/helpers/*.py`` that the team accepts as
    permanent unplanned territory.
    """
    if not src_dirs:
        return []
    planned_norm: set[str] = set()
    planned_dirs: list[str] = []
    for task in tasks:
        for path in task["deliverables"]:
            # Alternation in deliverables — both candidates count as planned.
            for candidate in (
                [p.strip() for p in path.split("|") if p.strip()] if "|" in path else [path]
            ):
                norm = os.path.normpath(candidate).replace("\\", "/")
                planned_norm.add(norm)
                if candidate.endswith("/") or not os.path.splitext(candidate)[1]:
                    planned_dirs.append(norm.rstrip("/") + "/")

    candidates = list_candidate_files(
        src_dirs,
        respect_gitignore=respect_gitignore,
        ignore_spec=ignore_spec,
    )
    whitelist = list(glob_whitelist or [])
    issues: list[Issue] = []
    for fp in candidates:
        norm = os.path.normpath(fp).replace("\\", "/")
        if norm in planned_norm:
            continue
        if any(norm.startswith(d) for d in planned_dirs):
            continue
        if any(fnmatch.fnmatch(norm, g) for g in whitelist):
            continue
        issues.append(
            _issue(
                Severity.LOW,
                "unplanned_files",
                f"计划外文件(可能gold-plating): {fp}",
                path=fp,
            )
        )
    return issues


def check_code_reviews(
    tasks: list[dict],
    reviews_dir: str,
    *,
    merged_review: bool = False,
) -> list[Issue]:
    """Verify each task has a per-task CODE-REVIEW report.

    Short-circuits when *merged_review* is true (the sprint-review report
    carries per-task Layer 2 instead of separate CODE-REVIEW files —
    declared via ``project_features.merged_review`` in dev-plan
    frontmatter).

    Tasks without a CODE-REVIEW file are reported as WARN (not FAIL) to
    accommodate deferred batch code-review: low-risk tasks may skip
    per-task code-review and be covered by sprint-review batch instead.
    """
    if merged_review:
        return []
    issues: list[Issue] = []
    if not os.path.isdir(reviews_dir):
        issues.append(
            _issue(
                Severity.MEDIUM,
                "code_review_present",
                f"审查报告目录不存在: {reviews_dir}",
                path=reviews_dir,
            )
        )
        return issues
    review_files = os.listdir(reviews_dir)
    for task in tasks:
        pattern = f"CODE-REVIEW-{task['id']}"
        if not any(f.startswith(pattern) for f in review_files):
            issues.append(
                _issue(
                    Severity.MEDIUM,
                    "code_review_present",
                    f"任务 {task['id']} 缺少CODE-REVIEW报告（将由sprint-review批量审查覆盖）",
                    task=task["id"],
                )
            )
    return issues


def _aggregate_unplanned(issues: list[Issue], cap: int) -> tuple[list[Issue], dict[str, int], int]:
    """Fold the unplanned-files WARN list to a printable subset.

    Returns ``(visible, by_top_dir, total_hidden)``:

    * ``visible`` — first ``cap`` issues to print verbatim. ``cap=0`` =
      unlimited (no folding).
    * ``by_top_dir`` — counts grouped by top-level directory segment, for
      a one-line summary per group when folded.
    * ``total_hidden`` — count of issues not in ``visible``.
    """
    if cap <= 0 or len(issues) <= cap:
        return issues, {}, 0
    visible = issues[:cap]
    hidden = issues[cap:]
    by_dir: collections.Counter[str] = collections.Counter()
    for it in hidden:
        path = it.path or ""
        top = path.split("/", 1)[0] if "/" in path else "<root>"
        by_dir[top] += 1
    return visible, dict(by_dir), len(hidden)
