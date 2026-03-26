#!/usr/bin/env python3
"""post_upgrade_check.py — CataForge 升级后验证工具

在 upgrade.py 完成后运行，检查:
1. 新功能的适用性（基于项目当前阶段）
2. SKILL.md / AGENT.md 文件引用完整性
3. 输出人类可读的迁移报告

返回: exit 0=健康, exit 1=发现问题
"""

import io
import json
import os
import re
import sys

# Ensure UTF-8 output on Windows
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Phase ordering for phase_guard comparison
PHASE_ORDER = [
    "requirements",
    "architecture",
    "ui_design",
    "dev_planning",
    "development",
    "testing",
    "deployment",
    "completed",
]


def parse_semver(ver_str: str) -> tuple:
    """解析 semver 字符串为 (major, minor, patch) 元组"""
    ver_str = ver_str.strip()
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)", ver_str)
    if not match:
        return (0, 0, 0)
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def read_current_version() -> str:
    """读取当前框架版本（从 pyproject.toml）"""
    ver_file = "pyproject.toml"
    if not os.path.exists(ver_file):
        return "0.0.0"
    with open(ver_file, "r", encoding="utf-8") as f:
        content = f.read()
    match = re.search(r'^version\s*=\s*"([^"]+)"', content, re.MULTILINE)
    return match.group(1) if match else "0.0.0"


def read_project_phase() -> str:
    """从 CLAUDE.md 读取当前项目阶段"""
    claude_md = "CLAUDE.md"
    if not os.path.exists(claude_md):
        return ""
    with open(claude_md, "r", encoding="utf-8") as f:
        content = f.read()
    match = re.search(r"当前阶段:\s*(\S+)", content)
    return match.group(1) if match else ""


def phase_index(phase: str) -> int:
    """返回阶段在生命周期中的索引，未知阶段返回-1"""
    try:
        return PHASE_ORDER.index(phase)
    except ValueError:
        return -1


def load_compat_matrix() -> dict:
    """加载兼容性矩阵"""
    matrix_file = os.path.join(".claude", "compat-matrix.json")
    if not os.path.exists(matrix_file):
        return {}
    with open(matrix_file, "r", encoding="utf-8") as f:
        return json.load(f)


def check_feature_applicability(
    matrix: dict, current_phase: str, old_version: str
) -> list:
    """检查每个功能在当前项目中的适用性"""
    results = []
    features = matrix.get("features", {})
    cur_phase_idx = phase_index(current_phase)
    old_ver = parse_semver(old_version)

    for feature_id, info in features.items():
        min_ver = parse_semver(info.get("min_version", "0.0.0"))
        auto_enable = info.get("auto_enable", True)
        phase_guard = info.get("phase_guard")
        description = info.get("description", "")

        is_new = min_ver > old_ver

        if not is_new:
            results.append(
                {
                    "feature": feature_id,
                    "status": "existing",
                    "description": description,
                    "message": "已有功能，无变化",
                }
            )
            continue

        if not auto_enable:
            results.append(
                {
                    "feature": feature_id,
                    "status": "opt-in",
                    "description": description,
                    "message": "新功能（需手动启用）",
                }
            )
            continue

        if phase_guard is None:
            results.append(
                {
                    "feature": feature_id,
                    "status": "auto-enabled",
                    "description": description,
                    "message": "新功能，所有阶段可用，已自动启用",
                }
            )
            continue

        guard_idx = phase_index(phase_guard)
        if cur_phase_idx < 0 or cur_phase_idx <= guard_idx:
            results.append(
                {
                    "feature": feature_id,
                    "status": "auto-enabled",
                    "description": description,
                    "message": f"新功能，项目尚未过 {phase_guard} 阶段，已自动启用",
                }
            )
        else:
            results.append(
                {
                    "feature": feature_id,
                    "status": "next-project",
                    "description": description,
                    "message": f"新功能，项目已过 {phase_guard} 阶段，下个项目可用",
                }
            )

    return results


def check_file_integrity() -> list:
    """验证 AGENT.md 中引用的 skills 对应的 SKILL.md 文件存在"""
    issues = []
    agents_dir = os.path.join(".claude", "agents")
    skills_dir = os.path.join(".claude", "skills")

    if not os.path.exists(agents_dir):
        issues.append("目录不存在: .claude/agents/")
        return issues

    for agent_name in os.listdir(agents_dir):
        agent_file = os.path.join(agents_dir, agent_name, "AGENT.md")
        if not os.path.exists(agent_file):
            continue

        with open(agent_file, "r", encoding="utf-8") as f:
            content = f.read()

        # Extract skills from frontmatter
        fm_match = re.search(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
        if not fm_match:
            continue

        frontmatter = fm_match.group(1)
        # Look for skills list in YAML frontmatter
        skills_match = re.search(r"skills:\s*\n((?:\s*-\s*.+\n)*)", frontmatter)
        if not skills_match:
            continue

        skills_block = skills_match.group(1)
        for skill_line in skills_block.strip().split("\n"):
            skill_name = skill_line.strip().lstrip("- ").strip()
            # Remove YAML inline comments (# ...)
            if "#" in skill_name:
                skill_name = skill_name[: skill_name.index("#")].strip()
            if not skill_name:
                continue
            skill_file = os.path.join(skills_dir, skill_name, "SKILL.md")
            if not os.path.exists(skill_file):
                issues.append(
                    f"Agent '{agent_name}' 引用了不存在的 skill: '{skill_name}' (缺少 {skill_file})"
                )

    # Check scripts referenced in SKILL.md files
    if os.path.exists(skills_dir):
        for skill_name in os.listdir(skills_dir):
            skill_file = os.path.join(skills_dir, skill_name, "SKILL.md")
            if not os.path.exists(skill_file):
                continue

            with open(skill_file, "r", encoding="utf-8") as f:
                content = f.read()

            # Find script references like `python .claude/skills/xxx/scripts/yyy.py`
            script_refs = re.findall(
                r"python\s+\.claude/skills/([^/]+)/scripts/(\S+\.py)", content
            )
            for ref_skill, ref_script in script_refs:
                script_path = os.path.join(
                    ".claude", "skills", ref_skill, "scripts", ref_script
                )
                if not os.path.exists(script_path):
                    issues.append(
                        f"Skill '{skill_name}' 引用了不存在的脚本: {script_path}"
                    )

    return issues


def main():
    print("=" * 60)
    print("CataForge 升级后验证报告")
    print("=" * 60)

    current_version = read_current_version()
    current_phase = read_project_phase()
    has_issues = False

    print(f"\n框架版本: {current_version}")
    print(f"项目阶段: {current_phase or '(未设置/新项目)'}")

    # 1. 功能适用性检查
    matrix = load_compat_matrix()
    if matrix:
        # Determine old version (before this upgrade) — use env var if set by upgrade.py
        old_version = os.environ.get("CATAFORGE_OLD_VERSION", "0.0.0")
        results = check_feature_applicability(matrix, current_phase, old_version)

        new_features = [r for r in results if r["status"] != "existing"]
        if new_features:
            print(f"\n--- 新功能状态 ({len(new_features)} 项) ---")
            for r in new_features:
                status_icon = {
                    "auto-enabled": "[启用]",
                    "opt-in": "[手动]",
                    "next-project": "[待用]",
                }.get(r["status"], "[??]")
                print(f"  {status_icon} {r['feature']}: {r['description']}")
                print(f"         {r['message']}")
        else:
            print("\n--- 无新功能 ---")
    else:
        print("\n--- 未找到 compat-matrix.json，跳过功能适用性检查 ---")

    # 2. 文件完整性检查
    print("\n--- 文件完整性检查 ---")
    issues = check_file_integrity()
    if issues:
        has_issues = True
        print(f"  发现 {len(issues)} 个问题:")
        for issue in issues:
            print(f"  [错误] {issue}")
    else:
        print("  所有引用完整，无缺失文件。")

    # 3. 总结
    print("\n" + "=" * 60)
    if has_issues:
        print("验证结果: 发现问题，请检查上方输出")
        sys.exit(1)
    else:
        print("验证结果: 通过")
        sys.exit(0)


if __name__ == "__main__":
    main()
