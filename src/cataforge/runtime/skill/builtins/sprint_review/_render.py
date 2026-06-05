"""Sprint check result rendering (text / json)."""

from __future__ import annotations

import json
import os
from typing import Any

from cataforge.runtime.skill.builtins._shared import Issue
from cataforge.runtime.skill.builtins.sprint_review._checks import _aggregate_unplanned


def render_text(
    sprint_num: int,
    tasks: list[dict[str, Any]],
    sections: list[tuple[str, list[Issue], str]],
    warn_cap: int,
    unplanned_log: str | None,
) -> bool:
    """Render text mode. Returns True if any blocking issue was printed."""
    print(f"Sprint {sprint_num} 结构检查\n{'=' * 40}")
    print(f"找到 {len(tasks)} 个任务: {', '.join(t['id'] for t in tasks)}")

    has_blocking = False
    all_blocking = 0
    all_advisory = 0
    folded_total = 0

    for title, issues, ok_msg in sections:
        print(f"\n--- {title} ---")
        is_unplanned = title.startswith("计划外文件")
        if is_unplanned:
            visible, by_dir, hidden = _aggregate_unplanned(issues, warn_cap)
            for it in visible:
                print(f"  [{it.severity.value}] {it.message}")
            if hidden:
                print(f"  [LOW] ...折叠 {hidden} 条 (--warn-cap=0 关闭折叠)")
                for top, n in sorted(by_dir.items(), key=lambda kv: -kv[1]):
                    print(f"         {top}/* ({n})")
                folded_total += hidden
            elif not issues:
                print(f"  {ok_msg}")
        else:
            if issues:
                for it in issues:
                    print(f"  [{it.severity.value}] {it.message}")
            else:
                print(f"  {ok_msg}")

        for it in issues:
            if it.blocking:
                has_blocking = True
                all_blocking += 1
            else:
                all_advisory += 1

    if unplanned_log:
        unplanned = [
            it for _, items, _ in sections for it in items if it.category == "unplanned_files"
        ]
        try:
            os.makedirs(os.path.dirname(unplanned_log) or ".", exist_ok=True)
            with open(unplanned_log, "w") as fh:
                for it in unplanned:
                    fh.write((it.path or "") + "\n")
        except OSError as exc:
            print(f"  [WARN] 无法写入 unplanned-log {unplanned_log}: {exc}")

    print(f"\n{'=' * 40}")
    if folded_total:
        print(
            f"结果: {all_blocking} blocking, {all_advisory} advisory "
            f"(其中 {folded_total} 条 unplanned 已折叠)"
        )
    else:
        print(f"结果: {all_blocking} blocking, {all_advisory} advisory")
    return has_blocking


def render_json(
    sprint_num: int,
    tasks: list[dict[str, Any]],
    sections: list[tuple[str, list[Issue], str]],
    unplanned_log: str | None,
) -> bool:
    flat_issues: list[Issue] = [it for _, items, _ in sections for it in items]
    blocking = sum(1 for it in flat_issues if it.blocking)
    advisory = len(flat_issues) - blocking
    payload = {
        "sprint": sprint_num,
        "tasks": [t["id"] for t in tasks],
        "summary": {"blocking": blocking, "advisory": advisory, "total": len(flat_issues)},
        "issues": [it.to_dict() for it in flat_issues],
    }
    if unplanned_log:
        payload["unplanned_log"] = unplanned_log
        try:
            unplanned = [it for it in flat_issues if it.category == "unplanned_files"]
            os.makedirs(os.path.dirname(unplanned_log) or ".", exist_ok=True)
            with open(unplanned_log, "w") as fh:
                for it in unplanned:
                    fh.write((it.path or "") + "\n")
        except OSError:
            pass
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return blocking > 0
