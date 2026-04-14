"""sprint_check.py — Sprint completion structural check (Layer 1).

Usage: python -m cataforge.skill.builtins.sprint_review.sprint_check {sprint_number} \
         [--dev-plan DIR] [--src-dir DIR] [--test-dir DIR]
Returns: exit 0=pass, exit 1=fail
"""

from __future__ import annotations

import argparse
import os
import re
import sys

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
                        if path and not re.search(r"[\u4e00-\u9fff\s{]", path):
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


def check_deliverables(tasks: list[dict]) -> list[str]:
    issues = []
    for task in tasks:
        for path in task["deliverables"]:
            if not os.path.exists(path):
                issues.append(f"[FAIL] 任务 {task['id']} 交付物缺失: {path}")
    return issues


def check_ac_coverage(tasks: list[dict], test_dir: str) -> list[str]:
    issues = []
    if not os.path.isdir(test_dir):
        issues.append(f"[WARN] 测试目录不存在: {test_dir}")
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
                issues.append(f"[FAIL] 任务 {task['id']} 的 {ac_id} 在 {test_dir} 中无测试引用")
    return issues


def check_unplanned_files(tasks: list[dict], src_dir: str) -> list[str]:
    issues = []
    if not os.path.isdir(src_dir):
        return issues
    planned_paths = set()
    for task in tasks:
        for path in task["deliverables"]:
            planned_paths.add(os.path.normpath(path))
    for root, _, files in os.walk(src_dir):
        for f in files:
            filepath = os.path.normpath(os.path.join(root, f))
            if f.startswith(".") or f.endswith(".pyc") or "__pycache__" in root:
                continue
            if filepath not in planned_paths:
                is_planned = any(filepath.startswith(os.path.normpath(p)) for p in planned_paths)
                if not is_planned:
                    issues.append(f"[WARN] 计划外文件(可能gold-plating): {filepath}")
    return issues


def check_code_reviews(tasks: list[dict], reviews_dir: str) -> list[str]:
    issues = []
    if not os.path.isdir(reviews_dir):
        issues.append(f"[WARN] 审查报告目录不存在: {reviews_dir}")
        return issues
    review_files = os.listdir(reviews_dir)
    for task in tasks:
        pattern = f"CODE-REVIEW-{task['id']}"
        if not any(f.startswith(pattern) for f in review_files):
            issues.append(f"[FAIL] 任务 {task['id']} 缺少CODE-REVIEW报告")
    return issues


def main() -> None:
    ensure_utf8_stdio()
    parser = argparse.ArgumentParser(description="Sprint completion structural check")
    parser.add_argument("sprint_number", type=int, help="Sprint number to check")
    parser.add_argument("--dev-plan", default="docs/dev-plan/", help="Dev plan directory")
    parser.add_argument("--src-dir", default="src/", help="Source directory")
    parser.add_argument("--test-dir", default="tests/", help="Test directory")
    parser.add_argument(
        "--reviews-dir", default="docs/reviews/code/",
        help="Code reviews directory",
    )
    args = parser.parse_args()

    sprint_num = args.sprint_number
    print(f"Sprint {sprint_num} 结构检查\n{'=' * 40}")

    dev_plan_files = find_dev_plan_files(args.dev_plan)
    if not dev_plan_files:
        print(f"[FAIL] 未找到dev-plan文件: {args.dev_plan}")
        sys.exit(1)

    tasks = extract_sprint_tasks(dev_plan_files, sprint_num)
    if not tasks:
        print(f"[FAIL] Sprint {sprint_num} 中未找到任务")
        sys.exit(1)

    print(f"找到 {len(tasks)} 个任务: {', '.join(t['id'] for t in tasks)}")
    all_issues: list[str] = []
    has_fail = False

    for task in tasks:
        if task["status"] != "done":
            issue = f"[FAIL] 任务 {task['id']} 状态为 '{task['status']}'，期望 'done'"
            all_issues.append(issue)
            has_fail = True
    print("\n--- 任务状态检查 ---")
    status_issues = [i for i in all_issues if "状态为" in i]
    if status_issues:
        for i in status_issues:
            print(f"  {i}")
    else:
        print("  所有任务状态为 done")

    print("\n--- 交付物检查 ---")
    deliv_issues = check_deliverables(tasks)
    all_issues.extend(deliv_issues)
    if deliv_issues:
        has_fail = True
        for i in deliv_issues:
            print(f"  {i}")
    else:
        total_deliverables = sum(len(t["deliverables"]) for t in tasks)
        print(f"  所有交付物存在 ({total_deliverables} 个文件)")

    print("\n--- AC覆盖检查 ---")
    ac_issues = check_ac_coverage(tasks, args.test_dir)
    all_issues.extend(ac_issues)
    if any(i.startswith("[FAIL]") for i in ac_issues):
        has_fail = True
    for i in ac_issues:
        print(f"  {i}")
    if not ac_issues:
        total_ac = sum(len(t["tdd_acceptance"]) for t in tasks)
        print(f"  所有AC已覆盖 ({total_ac} 个验收标准)")

    print("\n--- 计划外文件检测 ---")
    unplanned_issues = check_unplanned_files(tasks, args.src_dir)
    all_issues.extend(unplanned_issues)
    if unplanned_issues:
        for i in unplanned_issues:
            print(f"  {i}")
    else:
        print("  未发现计划外文件")

    print("\n--- CODE-REVIEW报告检查 ---")
    review_issues = check_code_reviews(tasks, args.reviews_dir)
    all_issues.extend(review_issues)
    if any(i.startswith("[FAIL]") for i in review_issues):
        has_fail = True
    for i in review_issues:
        print(f"  {i}")
    if not review_issues:
        print("  所有任务有CODE-REVIEW报告")

    fails = [i for i in all_issues if i.startswith("[FAIL]")]
    warns = [i for i in all_issues if i.startswith("[WARN]")]
    print(f"\n{'=' * 40}")
    print(f"结果: {len(fails)} FAIL, {len(warns)} WARN")

    sys.exit(1 if has_fail else 0)


if __name__ == "__main__":
    main()
