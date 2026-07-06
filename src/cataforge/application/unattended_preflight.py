"""Frozen-upstream preflight for the unattended building-loop.

The loop drives one sprint's building against a *frozen* dev-plan. Before
spending an overnight token budget it must confirm the plan is actually ready:
present, doc-review-frozen (``status: approved``), naming the target sprint, and
free of unresolved ``TODO`` / ``TBD`` / ``FIXME`` in its acceptance criteria. A
failed check returns a human-readable reason so the CLI can refuse to start.

Lives in the application layer (not the runtime loop) so it can locate project
docs and reuse the doc gate's placeholder rule; the CLI runs it ahead of
``run_building_loop``, whose own branch check stays the fail-closed safety net.
"""

from __future__ import annotations

import re
from pathlib import Path

from cataforge.utils.frontmatter import split_yaml_frontmatter
from cataforge.utils.placeholders import count_unresolved_placeholders

# A brief has something to build when it carries at least one task card heading
# (``### T-001: …``). Anchored on the T-<digit> id convention (NAV: T-001..T-NNN)
# rather than the section title, so a reworded heading or a prose mention of
# "开发任务" can neither false-reject nor false-pass.
_TASK_CARD_RE = re.compile(r"(?m)^#{2,6}\s+T-\d")


def _read(path: Path) -> str:
    try:
        return path.read_text(errors="replace")
    except OSError:
        return ""


def _devplan_files(docs_dir: Path) -> list[Path]:
    """Every dev-plan file: ``docs/dev-plan/*.md`` plus flat/lite fallbacks."""
    sub = docs_dir / "dev-plan"
    files = sorted(sub.glob("*.md")) if sub.is_dir() else []
    files += [p for p in (docs_dir / "dev-plan.md", docs_dir / "dev-plan-lite.md") if p.is_file()]
    return files


def _brief_files(docs_dir: Path) -> list[Path]:
    """Every brief file: ``docs/brief/*.md`` plus the flat ``docs/brief.md``."""
    sub = docs_dir / "brief"
    files = sorted(sub.glob("*.md")) if sub.is_dir() else []
    files += [p for p in (docs_dir / "brief.md",) if p.is_file()]
    return files


def preflight_frozen_upstream(project_root: Path, sprint: str) -> str | None:
    """Return a refusal reason, or ``None`` when it is safe to build *sprint*."""
    docs_dir = project_root / "docs"
    dev_plan_files = _devplan_files(docs_dir)
    if not dev_plan_files:
        return f"未找到 dev-plan（docs/dev-plan/ 为空）——无法对 {sprint} 跑无人值守 building"

    statuses: list[str] = []
    placeholders = 0
    combined: list[str] = []
    for f in dev_plan_files:
        fm, body = split_yaml_frontmatter(_read(f))
        if fm and isinstance(fm.get("status"), str):
            statuses.append(fm["status"])
        placeholders += count_unresolved_placeholders(body)
        combined.append(body)

    if sprint not in "\n".join(combined):
        return f"dev-plan 未引用 {sprint}——目标 sprint 不存在或拼写有误，无法定位任务卡"
    if not statuses:
        return "dev-plan 无 status frontmatter——未经 doc-review 冻结"
    non_approved = sorted({s for s in statuses if s != "approved"})
    if non_approved:
        return f"dev-plan 未冻结（status={','.join(non_approved)}）——需 doc-review approved"
    if placeholders:
        return f"dev-plan 含 {placeholders} 处未处理 TODO/TBD/FIXME——AC 未定稿，冻结前请消解"
    return None


def preflight_prototype_brief(project_root: Path) -> str | None:
    """Return a refusal reason, or ``None`` when the brief is ready to build.

    agile-prototype has no doc-review approval gate (checkpoints=none, Layer 1
    only), so — unlike the dev-plan gate — this does NOT require
    ``status: approved``; the brief stays ``draft`` throughout. It confirms the
    brief is present, carries a §5 开发任务 section to build against, and is free
    of unresolved ``TODO`` / ``TBD`` / ``FIXME``. The guarantee is deliberately
    weaker than the dev-plan gate (no approval anchor exists in the mode) — the
    real protection is the same sandbox + PR-only + morning review.
    """
    docs_dir = project_root / "docs"
    brief_files = _brief_files(docs_dir)
    if not brief_files:
        return (
            "未找到 brief（docs/brief/ 或 docs/brief.md 为空）"
            "——无法跑 agile-prototype 无人值守 building"
        )

    placeholders = 0
    combined: list[str] = []
    for f in brief_files:
        _fm, body = split_yaml_frontmatter(_read(f))
        placeholders += count_unresolved_placeholders(body)
        combined.append(body)

    if not _TASK_CARD_RE.search("\n".join(combined)):
        return "brief 缺少 §5 开发任务卡（未见 ### T- 卡片）——无待建目标，无法定位 building"
    if placeholders:
        return f"brief 含 {placeholders} 处未处理 TODO/TBD/FIXME——AC 未定稿，请先消解"
    return None
