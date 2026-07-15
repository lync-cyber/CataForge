"""sprint_check.py — Sprint completion structural check (Layer 1).

Usage: python -m cataforge.runtime.skill.builtins.sprint_review.sprint_check {sprint_number} \
         [--dev-plan DIR] [--src-dir DIR] [--test-dir DIR] [--reviews-dir DIR] \
         [--ignore PATTERN] [--ignore-file PATH] [--no-respect-gitignore] \
         [--no-default-ignores] [--warn-cap N] [--unplanned-log PATH] \
         [--format {text,json}]
Returns: exit 0=pass, exit 1=fail
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from cataforge.runtime.skill.builtins._shared import Issue
from cataforge.runtime.skill.builtins.sprint_review._checks import (
    _aggregate_unplanned,
    check_ac_coverage,
    check_code_reviews,
    check_deliverables,
    check_task_status,
    check_unplanned_files,
    resolve_task_status_external,
)
from cataforge.runtime.skill.builtins.sprint_review._extract import (
    classify_empty_extraction,
    extract_sprint_tasks,
    find_dev_plan_files,
    load_project_features,
)
from cataforge.runtime.skill.builtins.sprint_review._render import render_json, render_text
from cataforge.runtime.skill.builtins.sprint_review.ignore import (
    DEFAULT_UNPLANNED_GLOB_PATTERNS,
    IgnoreSpec,
    build_ignore_spec,
)
from cataforge.utils.encoding import ensure_utf8

# Actionable text per classify_empty_extraction code — turns the blanket
# "未找到任务" into a parse-failure vs genuinely-empty distinction.
_EMPTY_EXTRACTION_MESSAGES = {
    "no_tasks": "Sprint {sprint} 中未找到任务：dev-plan 未定义任何 T-NNN 任务",
    "no_anchor": (
        "Sprint {sprint} 中未找到任务：dev-plan 无 `### Sprint {sprint}` 标题锚定该 "
        "Sprint（检查 Sprint 编号是否越界 / 标题是否为 `### Sprint {sprint}`）"
    ),
    "anchored_empty": (
        "Sprint {sprint} 已锚定但未解析出任务（检查 §1 总览表任务行首列是否为 `| T-NNN | ... |`）"
    ),
}

# Re-export the check/extract/render surface so callers and tests keep
# importing them from this entry module after the helper split.
__all__ = [
    "Issue",
    "find_dev_plan_files",
    "load_project_features",
    "extract_sprint_tasks",
    "check_task_status",
    "check_deliverables",
    "check_ac_coverage",
    "check_unplanned_files",
    "check_code_reviews",
    "resolve_task_status_external",
    "_aggregate_unplanned",
    "render_text",
    "render_json",
    "main",
]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sprint completion structural check")
    parser.add_argument("sprint_number", type=int, help="Sprint number to check")
    parser.add_argument("--dev-plan", default="docs/dev-plan/", help="Dev plan directory")
    parser.add_argument(
        "--src-dir",
        action="append",
        default=None,
        help="Source directory to scope unplanned-file detection. Repeatable; default ['src/'].",
    )
    parser.add_argument("--test-dir", default="tests/", help="Test directory")
    parser.add_argument(
        "--reviews-dir",
        default="docs/reviews/code/",
        help="Code reviews directory",
    )
    parser.add_argument(
        "--ignore",
        action="append",
        default=[],
        help="Extra gitignore-style pattern (repeatable).",
    )
    parser.add_argument(
        "--ignore-file",
        action="append",
        default=[],
        help="Extra gitignore-style file to load (repeatable).",
    )
    parser.add_argument(
        "--no-respect-gitignore",
        action="store_true",
        help="Disable .gitignore integration (default: honour .gitignore via 'git ls-files').",
    )
    parser.add_argument(
        "--no-default-ignores",
        action="store_true",
        help="Disable built-in default ignore list (node_modules/, dist/, *.tsbuildinfo, ...).",
    )
    parser.add_argument(
        "--warn-cap",
        type=int,
        default=50,
        help="Max unplanned-file WARNs to print verbatim (0 = unlimited). "
        "Excess folded to per-directory counts. Default 50.",
    )
    parser.add_argument(
        "--unplanned-log",
        default=None,
        help="Write the full unplanned-files list to this path "
        "(useful when WARN cap is in effect).",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format. JSON is structured for CI / framework-review.",
    )
    return parser


def _emit_blocking(
    sprint_num: int, category: str, message: str, fmt: str, reason: str | None = None
) -> None:
    """Print a single-issue blocking result — the shape shared by both early exits."""
    if fmt == "json":
        issue: dict[str, str] = {"severity": "CRITICAL", "category": category}
        if reason is not None:
            issue["reason"] = reason
        issue["message"] = message
        print(
            json.dumps(
                {
                    "sprint": sprint_num,
                    "summary": {"blocking": 1, "advisory": 0, "total": 1},
                    "issues": [issue],
                },
                ensure_ascii=False,
            )
        )
    else:
        print(f"[CRITICAL] {message}")


def _build_sections(
    dev_plan_files: list[str],
    tasks: list[dict[str, Any]],
    args: argparse.Namespace,
    src_dirs: list[str],
    ignore_spec: IgnoreSpec,
) -> list[tuple[str, list[Issue], str]]:
    """Run every Sprint check and label its result for rendering."""
    features = load_project_features(dev_plan_files)
    accept_alternation = bool(features.get("deliverables_accept_alternation", True))
    merged_review = bool(features.get("merged_review"))
    task_status_external, status_external_auto = resolve_task_status_external(features, tasks)
    representative = bool(features.get("deliverables_representative"))
    glob_whitelist_raw = features.get("unplanned_glob_patterns") or []
    glob_whitelist = [g for g in glob_whitelist_raw if isinstance(g, str)]
    if not args.no_default_ignores:
        glob_whitelist = list(DEFAULT_UNPLANNED_GLOB_PATTERNS) + glob_whitelist

    return [
        (
            "任务状态检查",
            check_task_status(tasks, external_tracking=task_status_external),
            "所有任务状态为 done"
            + (
                " (跳过: 自动检测全部任务无 dev-plan 状态 → 视为外部追踪)"
                if status_external_auto
                else " (跳过: project_features.task_status_external)"
                if task_status_external
                else ""
            ),
        ),
        (
            "交付物检查",
            check_deliverables(tasks, accept_alternation=accept_alternation),
            f"所有交付物存在 ({sum(len(t['deliverables']) for t in tasks)} 个文件)",
        ),
        (
            "AC覆盖检查",
            check_ac_coverage(tasks, args.test_dir),
            f"所有AC已覆盖 ({sum(len(t['tdd_acceptance']) for t in tasks)} 个验收标准)",
        ),
        (
            "计划外文件检测",
            check_unplanned_files(
                tasks,
                src_dirs,
                respect_gitignore=not args.no_respect_gitignore,
                ignore_spec=ignore_spec,
                glob_whitelist=glob_whitelist,
                representative=representative,
            ),
            "未发现计划外文件"
            + (" (跳过: project_features.deliverables_representative)" if representative else ""),
        ),
        (
            "CODE-REVIEW报告检查",
            check_code_reviews(tasks, args.reviews_dir, merged_review=merged_review),
            "所有任务有CODE-REVIEW报告"
            + (" (跳过: project_features.merged_review)" if merged_review else ""),
        ),
    ]


def main() -> None:
    ensure_utf8()
    args = _build_parser().parse_args()

    src_dirs = args.src_dir if args.src_dir else ["src/"]
    ignore_spec = build_ignore_spec(
        use_defaults=not args.no_default_ignores,
        extra_patterns=args.ignore,
        extra_files=args.ignore_file,
    )
    sprint_num = args.sprint_number

    dev_plan_files = find_dev_plan_files(args.dev_plan)
    if not dev_plan_files:
        _emit_blocking(
            sprint_num, "dev_plan_missing", f"未找到dev-plan文件: {args.dev_plan}", args.format
        )
        sys.exit(1)

    tasks = extract_sprint_tasks(dev_plan_files, sprint_num)
    if not tasks:
        reason = classify_empty_extraction(dev_plan_files, sprint_num)
        message = _EMPTY_EXTRACTION_MESSAGES[reason].format(sprint=sprint_num)
        _emit_blocking(sprint_num, "sprint_tasks_missing", message, args.format, reason=reason)
        sys.exit(1)

    sections = _build_sections(dev_plan_files, tasks, args, src_dirs, ignore_spec)

    if args.format == "json":
        has_fail = render_json(sprint_num, tasks, sections, args.unplanned_log)
    else:
        has_fail = render_text(sprint_num, tasks, sections, args.warn_cap, args.unplanned_log)

    sys.exit(1 if has_fail else 0)


def _emit_runtime_error(exc: Exception, fmt: str) -> None:
    """Emit diagnostic on uncaught runtime failure. Exit 2 distinguishes
    runtime errors from normal FAIL (exit 1) so callers can branch."""
    import traceback

    summary = f"{type(exc).__name__}: {exc}"
    tb = traceback.format_exc(limit=5)
    if fmt == "json":
        print(
            json.dumps(
                {
                    "summary": {"blocking": 1, "advisory": 0, "total": 1},
                    "issues": [
                        {
                            "severity": "CRITICAL",
                            "category": "runtime_error",
                            "message": f"sprint_check runtime error: {summary}",
                            "traceback": tb.strip().splitlines()[-3:],
                        }
                    ],
                },
                ensure_ascii=False,
            )
        )
    else:
        print(f"[CRITICAL] sprint_check runtime error: {summary}", file=sys.stderr)
        print(tb, file=sys.stderr)


if __name__ == "__main__":
    _fmt = "json" if "--format" in sys.argv and "json" in sys.argv else "text"
    try:
        main()
    except Exception as _exc:
        _emit_runtime_error(_exc, _fmt)
        sys.exit(2)
