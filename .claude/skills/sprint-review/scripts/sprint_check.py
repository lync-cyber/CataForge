#!/usr/bin/env python3
"""sprint_check.py — Sprint完成度结构检查 (Layer 1)

用法: python .claude/skills/sprint-review/scripts/sprint_check.py {sprint_number}
      [--dev-plan DIR] [--src-dir DIR] [--test-dir DIR]

检查项:
1. Sprint任务表中所有任务状态=done
2. 每个任务的deliverables文件全部存在
3. 每个任务的AC-NNN在tests/目录有对应引用
4. 检测计划外文件(src/中不属于任何任务deliverables的文件)
5. 每个任务有对应的CODE-REVIEW报告

返回: exit 0=通过, exit 1=失败
"""

import argparse
import os
import re
import sys


def find_dev_plan_files(dev_plan_dir: str) -> list:
    """查找dev-plan目录下的所有markdown文件"""
    files = []
    if not os.path.isdir(dev_plan_dir):
        return files
    for f in sorted(os.listdir(dev_plan_dir)):
        if f.endswith(".md"):
            files.append(os.path.join(dev_plan_dir, f))
    return files


def extract_sprint_tasks(dev_plan_files: list, sprint_number: int) -> list:
    """从dev-plan文件中提取指定Sprint的任务列表

    Returns list of dicts: {id, status, deliverables, tdd_acceptance}
    """
    tasks = []
    in_sprint = False
    current_task = None

    # 尝试找Sprint专属卷文件 (dev-plan-*-s{N}.md)
    sprint_volume = None
    for f in dev_plan_files:
        if re.search(rf"-s{sprint_number}\.md$", f):
            sprint_volume = f
            break

    # 确定要搜索的文件列表
    files_to_search = [sprint_volume] if sprint_volume else dev_plan_files

    for filepath in files_to_search:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        lines = content.split("\n")
        i = 0
        while i < len(lines):
            line = lines[i]

            # 检测Sprint边界
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

            # 检测任务卡（### T-NNN 或 #### T-NNN，支持字母后缀如 T-007a）
            task_match = re.match(r"^#{2,4}\s+(T-\d+[a-z]?)", line)
            if task_match:
                if current_task:
                    tasks.append(current_task)
                current_task = {
                    "id": task_match.group(1),
                    "status": "",
                    "deliverables": [],
                    "tdd_acceptance": [],
                }
                i += 1
                continue

            # 在任务卡内提取字段
            if current_task:
                # 状态字段
                status_match = re.match(
                    r"^[-*]\s+\*?\*?(?:status|状态)\*?\*?\s*[:：]\s*(.+)",
                    line,
                    re.IGNORECASE,
                )
                if status_match:
                    current_task["status"] = status_match.group(1).strip().lower()

                # deliverables字段（支持 "**deliverables** (交付物):" 格式）
                deliv_match = re.match(
                    r"^[-*]\s+\*?\*?(?:deliverables|交付物)\*?\*?\s*(?:\([^)]*\)\s*)?[:：]",
                    line,
                    re.IGNORECASE,
                )
                if deliv_match:
                    # 收集后续缩进的列表项
                    i += 1
                    while i < len(lines) and re.match(r"^\s+[-*]", lines[i]):
                        path = re.sub(r"^\s+[-*]\s+", "", lines[i]).strip()
                        # 去掉 checkbox 前缀 ([ ] 或 [x])
                        path = re.sub(r"^\[[ x]\]\s*", "", path).strip()
                        # 去掉markdown标记
                        path = re.sub(r"[`*]", "", path).strip()
                        # 去掉 " — 描述" 或 " -- 描述" 后缀
                        path = re.sub(r"\s+[—\-]{1,2}\s+.*$", "", path).strip()
                        # 过滤非路径文本（含中文、空格、模板变量）
                        if path and not re.search(r"[\u4e00-\u9fff\s{]", path):
                            current_task["deliverables"].append(path)
                        i += 1
                    continue

                # tdd_acceptance字段
                ac_match = re.match(
                    r"^[-*]\s+\*?\*?(?:tdd_acceptance|验收标准)\*?\*?\s*[:：]",
                    line,
                    re.IGNORECASE,
                )
                if ac_match:
                    # 提取AC-NNN引用
                    rest = line + " "
                    i += 1
                    while i < len(lines) and re.match(r"^\s+[-*]", lines[i]):
                        rest += lines[i] + " "
                        i += 1
                    ac_ids = re.findall(r"AC-\d+", rest)
                    current_task["tdd_acceptance"] = list(set(ac_ids))
                    continue

                # 表格行中的任务（| T-001 | ... | done | ...），支持字母后缀
                table_match = re.match(
                    r"^\|\s*(T-\d+[a-z]?)\s*\|.*?\|\s*(done|todo|in[_-]?progress|blocked)\s*\|",
                    line,
                    re.IGNORECASE,
                )
                if table_match and not current_task["status"]:
                    if table_match.group(1) == current_task["id"]:
                        current_task["status"] = table_match.group(2).strip().lower()

            # 表格行直接解析（无任务卡格式时的fallback），支持字母后缀
            if not current_task:
                table_match = re.match(
                    r"^\|\s*(T-\d+[a-z]?)\s*\|.*?\|\s*(done|todo|in[_-]?progress|blocked)\s*\|",
                    line,
                    re.IGNORECASE,
                )
                if table_match and (in_sprint or sprint_volume):
                    tasks.append(
                        {
                            "id": table_match.group(1),
                            "status": table_match.group(2).strip().lower(),
                            "deliverables": [],
                            "tdd_acceptance": [],
                        }
                    )

            i += 1

        if current_task:
            tasks.append(current_task)
            current_task = None

    # 后处理: 从所有 dev-plan 文件的表格行回填缺失状态
    tasks_missing_status = {t["id"] for t in tasks if not t["status"]}
    if tasks_missing_status:
        for filepath in dev_plan_files:
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    table_match = re.match(
                        r"^\|\s*(T-\d+[a-z]?)\s*\|.*?\|\s*(done|todo|in[_-]?progress|blocked)\s*\|",
                        line,
                        re.IGNORECASE,
                    )
                    if table_match and table_match.group(1) in tasks_missing_status:
                        tid = table_match.group(1)
                        status = table_match.group(2).strip().lower()
                        for t in tasks:
                            if t["id"] == tid and not t["status"]:
                                t["status"] = status
                        tasks_missing_status.discard(tid)
            if not tasks_missing_status:
                break

    return tasks


def check_deliverables(tasks: list) -> list:
    """检查每个任务的deliverables文件是否存在"""
    issues = []
    for task in tasks:
        for path in task["deliverables"]:
            if not os.path.exists(path):
                issues.append(f"[FAIL] 任务 {task['id']} 交付物缺失: {path}")
    return issues


def check_ac_coverage(tasks: list, test_dir: str) -> list:
    """检查每个AC-NNN是否在tests/目录下有引用"""
    issues = []
    if not os.path.isdir(test_dir):
        issues.append(f"[WARN] 测试目录不存在: {test_dir}")
        return issues

    # 收集tests/中所有文件内容
    test_content = ""
    for root, _, files in os.walk(test_dir):
        for f in files:
            filepath = os.path.join(root, f)
            try:
                with open(filepath, "r", encoding="utf-8", errors="replace") as fh:
                    test_content += fh.read() + "\n"
            except (OSError, UnicodeDecodeError):
                continue

    for task in tasks:
        for ac_id in task["tdd_acceptance"]:
            if ac_id not in test_content:
                issues.append(
                    f"[FAIL] 任务 {task['id']} 的 {ac_id} 在 {test_dir} 中无测试引用"
                )

    return issues


def check_unplanned_files(tasks: list, src_dir: str) -> list:
    """检测src/目录中不属于任何任务deliverables的文件"""
    issues = []
    if not os.path.isdir(src_dir):
        return issues

    # 收集所有任务的deliverables路径（规范化）
    planned_paths = set()
    for task in tasks:
        for path in task["deliverables"]:
            norm = os.path.normpath(path)
            planned_paths.add(norm)

    # 扫描src/目录
    for root, _, files in os.walk(src_dir):
        for f in files:
            filepath = os.path.normpath(os.path.join(root, f))
            # 跳过隐藏文件、__pycache__ 目录内文件和 .pyc 文件
            if f.startswith(".") or f.endswith(".pyc") or "__pycache__" in root:
                continue
            if filepath not in planned_paths:
                # 检查是否为任何deliverables的子路径
                is_planned = any(
                    filepath.startswith(os.path.normpath(p)) for p in planned_paths
                )
                if not is_planned:
                    issues.append(f"[WARN] 计划外文件(可能gold-plating): {filepath}")

    return issues


def check_code_reviews(tasks: list, reviews_dir: str) -> list:
    """检查每个任务是否有对应的CODE-REVIEW报告"""
    issues = []
    if not os.path.isdir(reviews_dir):
        issues.append(f"[WARN] 审查报告目录不存在: {reviews_dir}")
        return issues

    review_files = os.listdir(reviews_dir)
    for task in tasks:
        pattern = f"CODE-REVIEW-{task['id']}"
        has_review = any(f.startswith(pattern) for f in review_files)
        if not has_review:
            issues.append(f"[FAIL] 任务 {task['id']} 缺少CODE-REVIEW报告")

    return issues


def _ensure_utf8_stdio():
    """Wrap stdout/stderr with UTF-8 encoding on Windows (CLI use only)."""
    import io

    if sys.stdout.encoding != "utf-8":
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace"
        )
    if sys.stderr.encoding != "utf-8":
        sys.stderr = io.TextIOWrapper(
            sys.stderr.buffer, encoding="utf-8", errors="replace"
        )


def main():
    _ensure_utf8_stdio()
    parser = argparse.ArgumentParser(description="Sprint completion structural check")
    parser.add_argument("sprint_number", type=int, help="Sprint number to check")
    parser.add_argument(
        "--dev-plan", default="docs/dev-plan/", help="Dev plan directory"
    )
    parser.add_argument("--src-dir", default="src/", help="Source directory")
    parser.add_argument("--test-dir", default="tests/", help="Test directory")
    parser.add_argument(
        "--reviews-dir", default="docs/reviews/code/", help="Code reviews directory"
    )
    args = parser.parse_args()

    sprint_num = args.sprint_number
    print(f"Sprint {sprint_num} 结构检查\n{'=' * 40}")

    # 1. 解析任务列表
    dev_plan_files = find_dev_plan_files(args.dev_plan)
    if not dev_plan_files:
        print(f"[FAIL] 未找到dev-plan文件: {args.dev_plan}")
        sys.exit(1)

    tasks = extract_sprint_tasks(dev_plan_files, sprint_num)
    if not tasks:
        print(f"[FAIL] Sprint {sprint_num} 中未找到任务")
        sys.exit(1)

    print(f"找到 {len(tasks)} 个任务: {', '.join(t['id'] for t in tasks)}")

    all_issues = []
    has_fail = False

    # 2. 检查任务状态
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

    # 3. 检查deliverables
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

    # 4. 检查AC覆盖
    print("\n--- AC覆盖检查 ---")
    ac_issues = check_ac_coverage(tasks, args.test_dir)
    all_issues.extend(ac_issues)
    fail_ac = [i for i in ac_issues if i.startswith("[FAIL]")]
    if fail_ac:
        has_fail = True
    for i in ac_issues:
        print(f"  {i}")
    if not ac_issues:
        total_ac = sum(len(t["tdd_acceptance"]) for t in tasks)
        print(f"  所有AC已覆盖 ({total_ac} 个验收标准)")

    # 5. 检查计划外文件
    print("\n--- 计划外文件检测 ---")
    unplanned_issues = check_unplanned_files(tasks, args.src_dir)
    all_issues.extend(unplanned_issues)
    if unplanned_issues:
        for i in unplanned_issues:
            print(f"  {i}")
    else:
        print("  未发现计划外文件")

    # 6. 检查CODE-REVIEW报告
    print("\n--- CODE-REVIEW报告检查 ---")
    review_issues = check_code_reviews(tasks, args.reviews_dir)
    all_issues.extend(review_issues)
    fail_review = [i for i in review_issues if i.startswith("[FAIL]")]
    if fail_review:
        has_fail = True
    for i in review_issues:
        print(f"  {i}")
    if not review_issues:
        print("  所有任务有CODE-REVIEW报告")

    # 7. 汇总
    fails = [i for i in all_issues if i.startswith("[FAIL]")]
    warns = [i for i in all_issues if i.startswith("[WARN]")]
    print(f"\n{'=' * 40}")
    print(f"结果: {len(fails)} FAIL, {len(warns)} WARN")

    if has_fail:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
