"""sprint_check.py — Sprint completion structural check (Layer 1).

Usage: python -m cataforge.skill.builtins.sprint_review.sprint_check {sprint_number} \
         [--dev-plan DIR] [--src-dir DIR] [--test-dir DIR] [--reviews-dir DIR] \
         [--ignore PATTERN] [--ignore-file PATH] [--no-respect-gitignore] \
         [--no-default-ignores] [--warn-cap N] [--unplanned-log PATH] \
         [--format {text,json}]
Returns: exit 0=pass, exit 1=fail
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import re
import sys

from cataforge.skill.builtins.sprint_review.ignore import (
    IgnoreSpec,
    build_ignore_spec,
    list_candidate_files,
)
from cataforge.utils.common import ensure_utf8_stdio


def find_dev_plan_files(dev_plan_dir: str) -> list[str]:
    files = []
    if not os.path.isdir(dev_plan_dir):
        return files
    for f in sorted(os.listdir(dev_plan_dir)):
        if f.endswith(".md"):
            files.append(os.path.join(dev_plan_dir, f))
    return files


def extract_sprint_tasks(dev_plan_files: list[str], sprint_number: int) -> list[dict]:
    tasks: list[dict] = []
    in_sprint = False
    current_task: dict | None = None

    sprint_volume = None
    for f in dev_plan_files:
        if re.search(rf"-s{sprint_number}\.md$", f):
            sprint_volume = f
            break

    files_to_search = [sprint_volume] if sprint_volume else dev_plan_files

    for filepath in files_to_search:
        with open(filepath, encoding="utf-8") as f:
            content = f.read()

        lines = content.split("\n")
        i = 0
        while i < len(lines):
            line = lines[i]
            if re.match(rf"^###?\s+Sprint\s+{sprint_number}\b", line, re.IGNORECASE):
                in_sprint = True
                i += 1
                continue
            elif in_sprint and re.match(r"^###?\s+Sprint\s+\d+", line, re.IGNORECASE):
                in_sprint = False
                i += 1
                continue

            if not in_sprint and not sprint_volume:
                i += 1
                continue

            task_match = re.match(r"^#{2,4}\s+(T-\d+[a-z]?)", line)
            if task_match:
                if current_task:
                    tasks.append(current_task)
                current_task = {
                    "id": task_match.group(1), "status": "",
                    "deliverables": [], "tdd_acceptance": [],
                }
                i += 1
                continue

            if current_task:
                status_match = re.match(
                    r"^[-*]\s+\*?\*?(?:status|状态)\*?\*?\s*[:：]\s*(.+)", line, re.IGNORECASE
                )
                if status_match:
                    current_task["status"] = status_match.group(1).strip().lower()

                deliv_match = re.match(
                    r"^[-*]\s+\*?\*?(?:deliverables|交付物)\*?\*?\s*(?:\([^)]*\)\s*)?[:：]",
                    line, re.IGNORECASE,
                )
                if deliv_match:
                    i += 1
                    while i < len(lines) and re.match(r"^\s+[-*]", lines[i]):
                        path = re.sub(r"^\s+[-*]\s+", "", lines[i]).strip()
                        path = re.sub(r"^\[[ x]\]\s*", "", path).strip()
                        path = re.sub(r"[`*]", "", path).strip()
                        path = re.sub(r"\s+[—\-]{1,2}\s+.*$", "", path).strip()
                        if path and not re.search(r"[一-鿿\s{]", path):
                            current_task["deliverables"].append(path)
                        i += 1
                    continue

                ac_match = re.match(
                    r"^[-*]\s+\*?\*?(?:tdd_acceptance|验收标准)\*?\*?\s*[:：]",
                    line, re.IGNORECASE,
                )
                if ac_match:
                    rest = line + " "
                    i += 1
                    while i < len(lines) and re.match(r"^\s+[-*]", lines[i]):
                        rest += lines[i] + " "
                        i += 1
                    ac_ids = re.findall(r"AC-\d+", rest)
                    current_task["tdd_acceptance"] = list(set(ac_ids))
                    continue

                table_match = re.match(
                    r"^\|\s*(T-\d+[a-z]?)\s*\|.*?\|\s*(done|todo|in[_-]?progress|blocked)\s*\|",
                    line, re.IGNORECASE,
                )
                if (
                    table_match
                    and not current_task["status"]
                    and table_match.group(1) == current_task["id"]
                ):
                    current_task["status"] = table_match.group(2).strip().lower()

            if not current_task:
                table_match = re.match(
                    r"^\|\s*(T-\d+[a-z]?)\s*\|.*?\|\s*(done|todo|in[_-]?progress|blocked)\s*\|",
                    line, re.IGNORECASE,
                )
                if table_match and (in_sprint or sprint_volume):
                    tasks.append({
                        "id": table_match.group(1),
                        "status": table_match.group(2).strip().lower(),
                        "deliverables": [], "tdd_acceptance": [],
                    })

            i += 1

        if current_task:
            tasks.append(current_task)
            current_task = None

    tasks_missing_status = {t["id"] for t in tasks if not t["status"]}
    if tasks_missing_status:
        for filepath in dev_plan_files:
            with open(filepath, encoding="utf-8") as f:
                for line in f:
                    table_match = re.match(
                        r"^\|\s*(T-\d+[a-z]?)\s*\|.*?\|\s*(done|todo|in[_-]?progress|blocked)\s*\|",
                        line, re.IGNORECASE,
                    )
                    if table_match and table_match.group(1) in tasks_missing_status:
                        tid = table_match.group(1)
                        for t in tasks:
                            if t["id"] == tid and not t["status"]:
                                t["status"] = table_match.group(2).strip().lower()
                        tasks_missing_status.discard(tid)
            if not tasks_missing_status:
                break

    return tasks


# ---------------------------------------------------------------------------
# Structured issue model — feeds both text and JSON renderers
# ---------------------------------------------------------------------------


def _issue(
    severity: str,
    category: str,
    message: str,
    *,
    task: str | None = None,
    path: str | None = None,
) -> dict:
    out: dict = {"severity": severity, "category": category, "message": message}
    if task is not None:
        out["task"] = task
    if path is not None:
        out["path"] = path
    return out


def check_task_status(tasks: list[dict]) -> list[dict]:
    issues: list[dict] = []
    for task in tasks:
        if task["status"] != "done":
            issues.append(_issue(
                "fail", "task_status_done",
                f"任务 {task['id']} 状态为 '{task['status']}'，期望 'done'",
                task=task["id"],
            ))
    return issues


def check_deliverables(tasks: list[dict]) -> list[dict]:
    issues: list[dict] = []
    for task in tasks:
        for path in task["deliverables"]:
            if not os.path.exists(path):
                issues.append(_issue(
                    "fail", "deliverables_exist",
                    f"任务 {task['id']} 交付物缺失: {path}",
                    task=task["id"], path=path,
                ))
    return issues


def check_ac_coverage(tasks: list[dict], test_dir: str) -> list[dict]:
    issues: list[dict] = []
    if not os.path.isdir(test_dir):
        issues.append(_issue(
            "warn", "ac_coverage", f"测试目录不存在: {test_dir}", path=test_dir,
        ))
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
                issues.append(_issue(
                    "fail", "ac_coverage",
                    f"任务 {task['id']} 的 {ac_id} 在 {test_dir} 中无测试引用",
                    task=task["id"],
                ))
    return issues


def check_unplanned_files(
    tasks: list[dict],
    src_dirs: list[str],
    *,
    respect_gitignore: bool,
    ignore_spec: IgnoreSpec,
) -> list[dict]:
    """Detect gold-plating: files under ``src_dirs`` not in any deliverable.

    Candidate enumeration honours .gitignore (when in a git repo and
    ``respect_gitignore`` is true) plus ``ignore_spec``. Files matching
    the deliverables list — or sitting under a deliverable directory —
    are filtered out.
    """
    if not src_dirs:
        return []
    planned_norm: set[str] = set()
    planned_dirs: list[str] = []
    for task in tasks:
        for path in task["deliverables"]:
            norm = os.path.normpath(path).replace("\\", "/")
            planned_norm.add(norm)
            # treat deliverable that look like dirs (no extension or trailing /)
            # as covering their whole subtree
            if path.endswith("/") or not os.path.splitext(path)[1]:
                planned_dirs.append(norm.rstrip("/") + "/")

    candidates = list_candidate_files(
        src_dirs,
        respect_gitignore=respect_gitignore,
        ignore_spec=ignore_spec,
    )
    issues: list[dict] = []
    for fp in candidates:
        norm = os.path.normpath(fp).replace("\\", "/")
        if norm in planned_norm:
            continue
        if any(norm.startswith(d) for d in planned_dirs):
            continue
        issues.append(_issue(
            "warn", "unplanned_files",
            f"计划外文件(可能gold-plating): {fp}",
            path=fp,
        ))
    return issues


def check_code_reviews(tasks: list[dict], reviews_dir: str) -> list[dict]:
    issues: list[dict] = []
    if not os.path.isdir(reviews_dir):
        issues.append(_issue(
            "warn", "code_review_present",
            f"审查报告目录不存在: {reviews_dir}", path=reviews_dir,
        ))
        return issues
    review_files = os.listdir(reviews_dir)
    for task in tasks:
        pattern = f"CODE-REVIEW-{task['id']}"
        if not any(f.startswith(pattern) for f in review_files):
            issues.append(_issue(
                "fail", "code_review_present",
                f"任务 {task['id']} 缺少CODE-REVIEW报告",
                task=task["id"],
            ))
    return issues


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------


def _aggregate_unplanned(
    issues: list[dict], cap: int
) -> tuple[list[dict], dict[str, int], int]:
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
        path = it.get("path", "")
        top = path.split("/", 1)[0] if "/" in path else "<root>"
        by_dir[top] += 1
    return visible, dict(by_dir), len(hidden)


def render_text(
    sprint_num: int,
    tasks: list[dict],
    sections: list[tuple[str, list[dict], str]],
    warn_cap: int,
    unplanned_log: str | None,
) -> bool:
    """Render text mode. Returns True if any FAIL was printed."""
    print(f"Sprint {sprint_num} 结构检查\n{'=' * 40}")
    print(f"找到 {len(tasks)} 个任务: {', '.join(t['id'] for t in tasks)}")

    has_fail = False
    all_fail = 0
    all_warn = 0
    folded_total = 0

    for title, issues, ok_msg in sections:
        print(f"\n--- {title} ---")
        is_unplanned = title.startswith("计划外文件")
        if is_unplanned:
            visible, by_dir, hidden = _aggregate_unplanned(issues, warn_cap)
            for it in visible:
                tag = "[FAIL]" if it["severity"] == "fail" else "[WARN]"
                print(f"  {tag} {it['message']}")
            if hidden:
                print(
                    f"  [WARN] ...折叠 {hidden} 条 "
                    "(--warn-cap=0 关闭折叠)"
                )
                for top, n in sorted(by_dir.items(), key=lambda kv: -kv[1]):
                    print(f"         {top}/* ({n})")
                folded_total += hidden
            elif not issues:
                print(f"  {ok_msg}")
        else:
            if issues:
                for it in issues:
                    tag = "[FAIL]" if it["severity"] == "fail" else "[WARN]"
                    print(f"  {tag} {it['message']}")
            else:
                print(f"  {ok_msg}")

        for it in issues:
            if it["severity"] == "fail":
                has_fail = True
                all_fail += 1
            else:
                all_warn += 1

    if unplanned_log:
        unplanned = [
            it for _, items, _ in sections for it in items
            if it["category"] == "unplanned_files"
        ]
        try:
            os.makedirs(os.path.dirname(unplanned_log) or ".", exist_ok=True)
            with open(unplanned_log, "w", encoding="utf-8") as fh:
                for it in unplanned:
                    fh.write(it.get("path", "") + "\n")
        except OSError as exc:
            print(f"  [WARN] 无法写入 unplanned-log {unplanned_log}: {exc}")

    print(f"\n{'=' * 40}")
    if folded_total:
        print(
            f"结果: {all_fail} FAIL, {all_warn} WARN "
            f"(其中 {folded_total} 条 unplanned 已折叠)"
        )
    else:
        print(f"结果: {all_fail} FAIL, {all_warn} WARN")
    return has_fail


def render_json(
    sprint_num: int,
    tasks: list[dict],
    sections: list[tuple[str, list[dict], str]],
    unplanned_log: str | None,
) -> bool:
    flat: list[dict] = [it for _, items, _ in sections for it in items]
    fails = sum(1 for it in flat if it["severity"] == "fail")
    warns = sum(1 for it in flat if it["severity"] == "warn")
    payload = {
        "sprint": sprint_num,
        "tasks": [t["id"] for t in tasks],
        "summary": {"fail": fails, "warn": warns, "total": len(flat)},
        "issues": flat,
    }
    if unplanned_log:
        payload["unplanned_log"] = unplanned_log
        try:
            unplanned = [it for it in flat if it["category"] == "unplanned_files"]
            os.makedirs(os.path.dirname(unplanned_log) or ".", exist_ok=True)
            with open(unplanned_log, "w", encoding="utf-8") as fh:
                for it in unplanned:
                    fh.write(it.get("path", "") + "\n")
        except OSError:
            pass
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return fails > 0


def main() -> None:
    ensure_utf8_stdio()
    parser = argparse.ArgumentParser(description="Sprint completion structural check")
    parser.add_argument("sprint_number", type=int, help="Sprint number to check")
    parser.add_argument("--dev-plan", default="docs/dev-plan/", help="Dev plan directory")
    parser.add_argument(
        "--src-dir", action="append", default=None,
        help="Source directory to scope unplanned-file detection. "
             "Repeatable; default ['src/'].",
    )
    parser.add_argument("--test-dir", default="tests/", help="Test directory")
    parser.add_argument(
        "--reviews-dir", default="docs/reviews/code/",
        help="Code reviews directory",
    )
    parser.add_argument(
        "--ignore", action="append", default=[],
        help="Extra gitignore-style pattern (repeatable).",
    )
    parser.add_argument(
        "--ignore-file", action="append", default=[],
        help="Extra gitignore-style file to load (repeatable).",
    )
    parser.add_argument(
        "--no-respect-gitignore", action="store_true",
        help="Disable .gitignore integration "
             "(default: honour .gitignore via 'git ls-files').",
    )
    parser.add_argument(
        "--no-default-ignores", action="store_true",
        help="Disable built-in default ignore list "
             "(node_modules/, dist/, *.tsbuildinfo, ...).",
    )
    parser.add_argument(
        "--warn-cap", type=int, default=50,
        help="Max unplanned-file WARNs to print verbatim (0 = unlimited). "
             "Excess folded to per-directory counts. Default 50.",
    )
    parser.add_argument(
        "--unplanned-log", default=None,
        help="Write the full unplanned-files list to this path "
             "(useful when WARN cap is in effect).",
    )
    parser.add_argument(
        "--format", choices=("text", "json"), default="text",
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
            print(json.dumps({
                "sprint": sprint_num,
                "summary": {"fail": 1, "warn": 0, "total": 1},
                "issues": [{
                    "severity": "fail", "category": "dev_plan_missing",
                    "message": f"未找到dev-plan文件: {args.dev_plan}",
                }],
            }, ensure_ascii=False))
        else:
            print(f"[FAIL] 未找到dev-plan文件: {args.dev_plan}")
        sys.exit(1)

    tasks = extract_sprint_tasks(dev_plan_files, sprint_num)
    if not tasks:
        if args.format == "json":
            print(json.dumps({
                "sprint": sprint_num,
                "summary": {"fail": 1, "warn": 0, "total": 1},
                "issues": [{
                    "severity": "fail", "category": "sprint_tasks_missing",
                    "message": f"Sprint {sprint_num} 中未找到任务",
                }],
            }, ensure_ascii=False))
        else:
            print(f"[FAIL] Sprint {sprint_num} 中未找到任务")
        sys.exit(1)

    sections: list[tuple[str, list[dict], str]] = [
        ("任务状态检查", check_task_status(tasks), "所有任务状态为 done"),
        ("交付物检查", check_deliverables(tasks),
         f"所有交付物存在 ({sum(len(t['deliverables']) for t in tasks)} 个文件)"),
        ("AC覆盖检查", check_ac_coverage(tasks, args.test_dir),
         f"所有AC已覆盖 ({sum(len(t['tdd_acceptance']) for t in tasks)} 个验收标准)"),
        ("计划外文件检测", check_unplanned_files(
            tasks, src_dirs,
            respect_gitignore=not args.no_respect_gitignore,
            ignore_spec=ignore_spec,
        ), "未发现计划外文件"),
        ("CODE-REVIEW报告检查", check_code_reviews(tasks, args.reviews_dir),
         "所有任务有CODE-REVIEW报告"),
    ]

    if args.format == "json":
        has_fail = render_json(sprint_num, tasks, sections, args.unplanned_log)
    else:
        has_fail = render_text(
            sprint_num, tasks, sections, args.warn_cap, args.unplanned_log,
        )

    sys.exit(1 if has_fail else 0)


if __name__ == "__main__":
    main()
