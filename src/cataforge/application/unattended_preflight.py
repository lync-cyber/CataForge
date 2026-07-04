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

from pathlib import Path

from cataforge.utils.frontmatter import split_yaml_frontmatter
from cataforge.utils.placeholders import count_unresolved_placeholders


def _read(path: Path) -> str:
    try:
        return path.read_text(errors="replace")
    except OSError:
        return ""


def _devplan_volumes(docs_dir: Path) -> list[Path]:
    """Every dev-plan volume: ``docs/dev-plan/*.md`` plus flat/lite fallbacks."""
    sub = docs_dir / "dev-plan"
    vols = sorted(sub.glob("*.md")) if sub.is_dir() else []
    vols += [p for p in (docs_dir / "dev-plan.md", docs_dir / "dev-plan-lite.md") if p.is_file()]
    return vols


def preflight_frozen_upstream(project_root: Path, sprint: str) -> str | None:
    """Return a refusal reason, or ``None`` when it is safe to build *sprint*."""
    docs_dir = project_root / "docs"
    volumes = _devplan_volumes(docs_dir)
    if not volumes:
        return f"未找到 dev-plan（docs/dev-plan/ 为空）——无法对 {sprint} 跑无人值守 building"

    statuses: list[str] = []
    placeholders = 0
    combined: list[str] = []
    for vol in volumes:
        fm, body = split_yaml_frontmatter(_read(vol))
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
