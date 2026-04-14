#!/usr/bin/env python3
"""CataForge Upgrade Verification Module.

Extracted from upgrade.py for single-responsibility:
- Post-upgrade verification (compatibility matrix, feature applicability,
  file integrity, migration artifact checks)

Functions:
  load_compat_matrix()          - Load compatibility matrix from framework.json
  check_feature_applicability() - Check feature applicability per project phase
  check_file_integrity()        - Verify AGENT.md skill references exist
  check_migration_artifacts()   - Data-driven migration checks from framework.json
  run_verify()                  - Execute full post-upgrade verification report
"""

import json
import os
import re
import sys

_FRAMEWORK_DIR = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS_ROOT = os.path.dirname(_FRAMEWORK_DIR)
_LIB = os.path.join(_SCRIPTS_ROOT, "lib")
for _p in (_LIB, _FRAMEWORK_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)
from _config import load_framework_config
from _version import PHASE_ORDER, parse_semver, phase_index, read_version
from phase_reader import read_current_phase


def load_compat_matrix() -> dict:
    """从 framework.json 加载兼容性矩阵（features + migration_checks）"""
    config = load_framework_config()
    if not config:
        return {}
    # 构造与旧 compat-matrix.json 兼容的结构
    return {
        "features": config.get("features", {}),
        "migration_checks": config.get("migration_checks", []),
    }


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
    agents_dir = os.path.join(".cataforge", "agents")
    skills_dir = os.path.join(".cataforge", "skills")

    if not os.path.exists(agents_dir):
        issues.append("目录不存在: .cataforge/agents/")
        return issues

    for agent_name in os.listdir(agents_dir):
        agent_file = os.path.join(agents_dir, agent_name, "AGENT.md")
        if not os.path.exists(agent_file):
            continue

        with open(agent_file, "r", encoding="utf-8") as f:
            content = f.read()

        fm_match = re.search(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
        if not fm_match:
            continue

        frontmatter = fm_match.group(1)
        skills_match = re.search(r"skills:\s*\n((?:\s*-\s*.+\n)*)", frontmatter)
        if not skills_match:
            continue

        skills_block = skills_match.group(1)
        for skill_line in skills_block.strip().split("\n"):
            skill_name = skill_line.strip().lstrip("- ").strip()
            if "#" in skill_name:
                skill_name = skill_name[: skill_name.index("#")].strip()
            if not skill_name:
                continue
            skill_file = os.path.join(skills_dir, skill_name, "SKILL.md")
            if not os.path.exists(skill_file):
                issues.append(
                    f"Agent '{agent_name}' 引用了不存在的 skill: '{skill_name}' "
                    f"(缺少 {skill_file})"
                )

    # Check scripts referenced in SKILL.md files
    if os.path.exists(skills_dir):
        for skill_name in os.listdir(skills_dir):
            skill_file = os.path.join(skills_dir, skill_name, "SKILL.md")
            if not os.path.exists(skill_file):
                continue
            with open(skill_file, "r", encoding="utf-8") as f:
                content = f.read()
            script_refs = re.findall(
                r"python\s+\.cataforge/skills/([^/]+)/scripts/(\S+\.py)", content
            )
            for ref_skill, ref_script in script_refs:
                script_path = os.path.join(
                    ".cataforge", "skills", ref_skill, "scripts", ref_script
                )
                if not os.path.exists(script_path):
                    issues.append(
                        f"Skill '{skill_name}' 引用了不存在的脚本: {script_path}"
                    )

    return issues


def check_migration_artifacts() -> list:
    """数据驱动的迁移检查: 从 framework.json 的 `migration_checks` 字段
    读取每次 release 声明的强制约束并执行。

    每个 migration check 声明:
      {
        "id": "mc-0.6.0-001",
        "description": "...",
        "release_version": "0.6.0",
        "type": "file_must_exist" | "file_must_contain" | "file_must_not_contain",
        "path": ".cataforge/rules/COMMON-RULES.md",
        "patterns": ["DOC_SPLIT_THRESHOLD_LINES", ...]   # type 决定 patterns 语义
      }

    支持的 type:
    - file_must_exist        : path 文件必须存在 (patterns 可空)
    - file_must_contain      : path 文件必须包含 patterns 中所有字串
    - file_must_not_contain  : path 文件不得包含 patterns 中任一字串
    - dir_must_contain_files : path 目录下必须存在 patterns 中列出的所有文件

    未知 type 被跳过并报告为警告。此函数完全取代 v0.6.x 版本的三个硬编码检查函数
    (check_framework_constants / check_lite_templates / check_doc_gen_no_hardcoded_500)。
    """
    issues: list[str] = []
    matrix = load_compat_matrix()
    checks = matrix.get("migration_checks", [])
    if not checks:
        return issues  # 无迁移检查声明，通过

    for check in checks:
        check_id = check.get("id", "<unnamed>")
        description = check.get("description", "")
        check_type = check.get("type", "")
        path = check.get("path", "")
        patterns = check.get("patterns", []) or []
        label = f"{check_id} ({description})" if description else check_id

        if not path or not check_type:
            issues.append(f"[{label}] 声明不完整: 缺少 path 或 type")
            continue

        if check_type == "file_must_exist":
            if not os.path.exists(path):
                issues.append(f"[{label}] 缺少文件: {path}")
            continue

        if check_type == "dir_must_contain_files":
            if not os.path.isdir(path):
                issues.append(f"[{label}] 缺少目录: {path}")
                continue
            for fname in patterns:
                fpath = os.path.join(path, fname)
                if not os.path.exists(fpath):
                    issues.append(f"[{label}] 缺少文件: {fpath}")
            continue

        if check_type in ("file_must_contain", "file_must_not_contain"):
            if not os.path.exists(path):
                issues.append(f"[{label}] 文件不存在: {path}")
                continue
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
            except OSError as e:
                issues.append(f"[{label}] 读取失败: {path} ({e})")
                continue
            for pat in patterns:
                present = pat in content
                if check_type == "file_must_contain" and not present:
                    issues.append(f"[{label}] {path} 缺少必需字串: {pat!r}")
                elif check_type == "file_must_not_contain" and present:
                    issues.append(f"[{label}] {path} 仍包含已废弃字串: {pat!r}")
            continue

        issues.append(f"[{label}] 未知 migration check type: {check_type}")

    return issues


def run_verify() -> int:
    """执行升级后验证"""
    print("=" * 60)
    print("CataForge 升级后验证报告")
    print("=" * 60)

    current_version = read_version(".")
    current_phase = read_current_phase()
    has_issues = False

    print(f"\n框架版本: {current_version}")
    display_phase = current_phase if current_phase != "unknown" else "(未设置/新项目)"
    print(f"项目阶段: {display_phase}")

    # 功能适用性检查
    matrix = load_compat_matrix()
    if matrix:
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
        print("\n--- 未找到 framework.json，跳过功能适用性检查 ---")

    # 文件完整性检查
    print("\n--- 文件完整性检查 ---")
    issues = check_file_integrity()
    if issues:
        has_issues = True
        print(f"  发现 {len(issues)} 个问题:")
        for issue in issues:
            print(f"  [错误] {issue}")
    else:
        print("  所有引用完整，无缺失文件。")

    # 迁移检查 (数据驱动: 读取 framework.json 的 migration_checks 字段)
    print("\n--- 迁移检查 (framework.migration_checks) ---")
    mig_issues = check_migration_artifacts()
    if mig_issues:
        has_issues = True
        print(f"  发现 {len(mig_issues)} 个问题:")
        for issue in mig_issues:
            print(f"  [错误] {issue}")
    else:
        mc_count = len(matrix.get("migration_checks", [])) if matrix else 0
        if mc_count > 0:
            print(f"  通过 {mc_count} 项迁移检查。")
        else:
            print("  framework.json 未声明 migration_checks，跳过。")

    print("\n" + "=" * 60)
    if has_issues:
        print("验证结果: 发现问题，请检查上方输出")
        return 1
    else:
        print("验证结果: 通过")
        return 0
