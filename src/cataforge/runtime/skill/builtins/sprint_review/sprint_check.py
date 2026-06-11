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

from cataforge.runtime.skill.builtins._shared import Issue
from cataforge.runtime.skill.builtins.sprint_review._checks import (
    _aggregate_unplanned,
    check_ac_coverage,
    check_code_reviews,
    check_deliverables,
    check_task_status,
    check_unplanned_files,
)
from cataforge.runtime.skill.builtins.sprint_review._extract import (
    extract_sprint_tasks,
    find_dev_plan_files,
    load_project_features,
)
from cataforge.runtime.skill.builtins.sprint_review._render import render_json, render_text
from cataforge.runtime.skill.builtins.sprint_review.ignore import (
    DEFAULT_UNPLANNED_GLOB_PATTERNS,
    build_ignore_spec,
)
from cataforge.utils.common import ensure_utf8

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
    "_aggregate_unplanned",
    "render_text",
    "render_json",
    "main",
]


def main() -> None:
    ensure_utf8()
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
    args = parser.parse_args()

    src_dirs = args.src_dir if args.src_dir else ["src/"]

    ignore_spec = build_ignore_spec(
        use_defaults=not args.no_default_ignores,
        extra_patterns=args.ignore,
        extra_files=args.ignore_file,
    )

    sprint_num = args.sprint_number
    dev_plan_files = find_dev_plan_files(args.dev_plan)
    if not dev_plan_files:
        if args.format == "json":
            print(
                json.dumps(
                    {
                        "sprint": sprint_num,
                        "summary": {"blocking": 1, "advisory": 0, "total": 1},
                        "issues": [
                            {
                                "severity": "CRITICAL",
                                "category": "dev_plan_missing",
                                "message": f"未找到dev-plan文件: {args.dev_plan}",
                            }
                        ],
                    },
                    ensure_ascii=False,
                )
            )
        else:
            print(f"[CRITICAL] 未找到dev-plan文件: {args.dev_plan}")
        sys.exit(1)

    tasks = extract_sprint_tasks(dev_plan_files, sprint_num)
    if not tasks:
        if args.format == "json":
            print(
                json.dumps(
                    {
                        "sprint": sprint_num,
                        "summary": {"blocking": 1, "advisory": 0, "total": 1},
                        "issues": [
                            {
                                "severity": "CRITICAL",
                                "category": "sprint_tasks_missing",
                                "message": f"Sprint {sprint_num} 中未找到任务",
                            }
                        ],
                    },
                    ensure_ascii=False,
                )
            )
        else:
            print(f"[CRITICAL] Sprint {sprint_num} 中未找到任务")
        sys.exit(1)

    features = load_project_features(dev_plan_files)
    accept_alternation = bool(features.get("deliverables_accept_alternation", True))
    merged_review = bool(features.get("merged_review"))
    task_status_external = bool(features.get("task_status_external"))
    glob_whitelist_raw = features.get("unplanned_glob_patterns") or []
    glob_whitelist = [g for g in glob_whitelist_raw if isinstance(g, str)]
    if not args.no_default_ignores:
        glob_whitelist = list(DEFAULT_UNPLANNED_GLOB_PATTERNS) + glob_whitelist

    sections: list[tuple[str, list[Issue], str]] = [
        (
            "任务状态检查",
            check_task_status(tasks, external_tracking=task_status_external),
            "所有任务状态为 done"
            + (" (跳过: project_features.task_status_external)" if task_status_external else ""),
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
            ),
            "未发现计划外文件",
        ),
        (
            "CODE-REVIEW报告检查",
            check_code_reviews(tasks, args.reviews_dir, merged_review=merged_review),
            "所有任务有CODE-REVIEW报告"
            + (" (跳过: project_features.merged_review)" if merged_review else ""),
        ),
    ]

    if args.format == "json":
        has_fail = render_json(sprint_num, tasks, sections, args.unplanned_log)
    else:
        has_fail = render_text(
            sprint_num,
            tasks,
            sections,
            args.warn_cap,
            args.unplanned_log,
        )

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
