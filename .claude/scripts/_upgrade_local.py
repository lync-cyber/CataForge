#!/usr/bin/env python3
"""Local upgrade module extracted from upgrade.py.

Contains the local upgrade logic for CataForge framework:
- backup_framework: backup current framework files
- copy_framework: copy framework files from source
- merge_settings: merge settings.json preserving user config
- extract_section / extract_filled_values: CLAUDE.md parsing helpers
- merge_claude_md: merge CLAUDE.md template with project state
- run_local_upgrade: orchestrate the full local upgrade flow
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import FRAMEWORK_CONFIG_FILE, load_json_lenient
from _config import load_framework_config
from _version import VERSION_FILE, parse_semver, read_version

FRAMEWORK_DIRS = ["agents", "skills", "rules", "hooks", "scripts", "schemas"]


def backup_framework(backup_dir: str, dry_run: bool = False) -> list:
    """备份当前框架文件到指定目录"""
    backed_up = []
    claude_dir = ".claude"

    for d in FRAMEWORK_DIRS:
        src = os.path.join(claude_dir, d)
        if os.path.exists(src):
            dst = os.path.join(backup_dir, d)
            if dry_run:
                backed_up.append(f"  备份: {src} → {dst}")
            else:
                shutil.copytree(src, dst)
                backed_up.append(f"  备份: {src} → {dst}")

    if os.path.exists(VERSION_FILE):
        dst = os.path.join(backup_dir, VERSION_FILE)
        if not dry_run:
            shutil.copy2(VERSION_FILE, dst)
        backed_up.append(f"  备份: {VERSION_FILE} → {dst}")

    settings = os.path.join(claude_dir, "settings.json")
    if os.path.exists(settings):
        dst = os.path.join(backup_dir, "settings.json")
        if not dry_run:
            shutil.copy2(settings, dst)
        backed_up.append(f"  备份: {settings} → {dst}")

    return backed_up


def copy_framework(source_path: str, dry_run: bool = False) -> list:
    """从源路径复制框架文件覆盖当前目录"""
    changes = []
    claude_dir = ".claude"

    for d in FRAMEWORK_DIRS:
        src = os.path.join(source_path, ".claude", d)
        dst = os.path.join(claude_dir, d)

        if not os.path.exists(src):
            changes.append(f"  跳过: {src} (源目录不存在)")
            continue

        if dry_run:
            new_files = set()
            for root, _, files in os.walk(src):
                for f in files:
                    rel = os.path.relpath(os.path.join(root, f), src)
                    new_files.add(rel)
            old_files = set()
            if os.path.exists(dst):
                for root, _, files in os.walk(dst):
                    for f in files:
                        rel = os.path.relpath(os.path.join(root, f), dst)
                        old_files.add(rel)
            added = new_files - old_files
            removed = old_files - new_files
            updated = new_files & old_files
            if added:
                changes.append(f"  {d}/: +{len(added)} 新增")
            if removed:
                changes.append(f"  {d}/: -{len(removed)} 删除")
            if updated:
                changes.append(f"  {d}/: ~{len(updated)} 更新")
        else:
            if os.path.exists(dst):
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
            changes.append(f"  替换: .claude/{d}/")

    # 复制版本文件 (pyproject.toml)
    src_ver = os.path.join(source_path, VERSION_FILE)
    if os.path.exists(src_ver):
        if os.path.exists(VERSION_FILE):
            with open(VERSION_FILE, "r", encoding="utf-8") as f:
                cur_content = f.read()
            with open(src_ver, "r", encoding="utf-8") as f:
                new_content = f.read()
            new_ver_match = re.search(
                r'^version\s*=\s*"([^"]+)"', new_content, re.MULTILINE
            )
            if new_ver_match:
                new_ver_val = new_ver_match.group(1)
                updated = re.sub(
                    r'^(version\s*=\s*)"[^"]+"',
                    rf'\g<1>"{new_ver_val}"',
                    cur_content,
                    count=1,
                    flags=re.MULTILINE,
                )
                if not dry_run:
                    with open(VERSION_FILE, "w", encoding="utf-8") as f:
                        f.write(updated)
                changes.append(f"  更新: {VERSION_FILE} (version → {new_ver_val})")
        else:
            if not dry_run:
                shutil.copy2(src_ver, VERSION_FILE)
            changes.append(f"  新增: {VERSION_FILE}")

    # 合并 framework.json（features/migration_checks 全量覆盖，upgrade.source 合并，upgrade.state 保留）
    src_fw = os.path.join(source_path, ".claude", "framework.json")
    dst_fw = os.path.join(".claude", "framework.json")
    if os.path.exists(src_fw):
        if os.path.exists(dst_fw):
            try:
                with open(src_fw, "r", encoding="utf-8") as f:
                    new_fw = json.load(f)
                with open(dst_fw, "r", encoding="utf-8") as f:
                    cur_fw = json.load(f)
                # 框架出厂配置: 全量覆盖
                cur_fw["version"] = new_fw.get("version", cur_fw.get("version", ""))
                cur_fw["description"] = new_fw.get(
                    "description", cur_fw.get("description", "")
                )
                cur_fw["features"] = new_fw.get("features", {})
                cur_fw["migration_checks"] = new_fw.get("migration_checks", [])
                # upgrade.source: 保留用户已配置值，补充新字段
                cur_upgrade = cur_fw.setdefault("upgrade", {})
                new_upgrade = new_fw.get("upgrade", {})
                cur_source = cur_upgrade.setdefault("source", {})
                for k, v in new_upgrade.get("source", {}).items():
                    if k not in cur_source:
                        cur_source[k] = v
                # upgrade.state: 始终保留当前值
                if not dry_run:
                    with open(dst_fw, "w", encoding="utf-8") as f:
                        json.dump(cur_fw, f, ensure_ascii=False, indent=2)
                        f.write("\n")
                changes.append("  合并: .claude/framework.json")
            except (json.JSONDecodeError, OSError):
                changes.append("  跳过: .claude/framework.json (解析失败)")
        else:
            if not dry_run:
                shutil.copy2(src_fw, dst_fw)
            changes.append("  新增: .claude/framework.json")

    return changes


def merge_settings(source_path: str, dry_run: bool = False) -> list:
    """合并 settings.json: 保留 env/permissions, 合并 mcpServers, 替换 hooks"""
    changes = []
    src_file = os.path.join(source_path, ".claude", "settings.json")
    cur_file = os.path.join(".claude", "settings.json")

    if not os.path.exists(src_file):
        changes.append("  跳过: 新版无 settings.json")
        return changes

    if not os.path.exists(cur_file):
        if not dry_run:
            shutil.copy2(src_file, cur_file)
        changes.append("  新增: .claude/settings.json (从新版复制)")
        return changes

    new_settings = load_json_lenient(src_file)
    cur_settings = load_json_lenient(cur_file)
    merged = {}

    # $schema
    if "$schema" in new_settings:
        merged["$schema"] = new_settings["$schema"]
    elif "$schema" in cur_settings:
        merged["$schema"] = cur_settings["$schema"]

    # env: 保留当前，补充新增
    if "env" in cur_settings:
        merged["env"] = cur_settings["env"]
        if "env" in new_settings:
            for k, v in new_settings["env"].items():
                if k not in merged["env"]:
                    merged["env"][k] = v
                    changes.append(f"  新增 env: {k}")
    elif "env" in new_settings:
        merged["env"] = new_settings["env"]

    # permissions: 保留当前，追加新 allow
    if "permissions" in cur_settings:
        merged["permissions"] = cur_settings["permissions"]
        if "permissions" in new_settings:
            new_allow = set(new_settings.get("permissions", {}).get("allow", []))
            cur_allow = set(cur_settings.get("permissions", {}).get("allow", []))
            added = new_allow - cur_allow
            if added:
                merged["permissions"]["allow"] = list(cur_allow | new_allow)
                changes.append(f"  新增 permissions.allow: {len(added)} 条")
    elif "permissions" in new_settings:
        merged["permissions"] = new_settings["permissions"]

    # hooks: 合并（框架钩子更新，用户自定义钩子保留）
    cur_hooks = cur_settings.get("hooks", {})
    new_hooks = new_settings.get("hooks", {})
    if cur_hooks or new_hooks:
        merged_hooks = {}
        all_events = set(list(cur_hooks.keys()) + list(new_hooks.keys()))
        for event in all_events:
            new_event_list = new_hooks.get(event, [])
            cur_event_list = cur_hooks.get(event, [])
            # 如果事件类型的值不是列表（格式异常），直接使用新版
            if not isinstance(new_event_list, list) or not isinstance(
                cur_event_list, list
            ):
                merged_hooks[event] = (
                    new_event_list if event in new_hooks else cur_event_list
                )
                continue
            # 以新版框架钩子为基础，追加当前版本中独有的钩子（用户自定义）
            seen_keys = {json.dumps(h, sort_keys=True) for h in new_event_list}
            merged_event = list(new_event_list)
            for h in cur_event_list:
                hook_key = json.dumps(h, sort_keys=True)
                if hook_key not in seen_keys:
                    merged_event.append(h)
                    seen_keys.add(hook_key)
            merged_hooks[event] = merged_event
        merged["hooks"] = merged_hooks
        if cur_hooks != new_hooks:
            changes.append("  更新: hooks 配置（已保留用户自定义钩子）")

    # mcpServers: 合并（用户配置优先，防止覆盖用户对现有 server 的自定义参数）
    cur_servers = cur_settings.get("mcpServers", {})
    new_servers = new_settings.get("mcpServers", {})
    if cur_servers or new_servers:
        # 新版新增的 server 作为默认，用户当前配置覆盖同名 server
        merged_servers = {**new_servers, **cur_servers}
        merged["mcpServers"] = merged_servers
        added_servers = set(new_servers.keys()) - set(cur_servers.keys())
        kept_servers = set(cur_servers.keys()) - set(new_servers.keys())
        if added_servers:
            changes.append(f"  新增 mcpServers: {', '.join(added_servers)}")
        if kept_servers:
            changes.append(f"  保留用户 mcpServers: {', '.join(kept_servers)}")

    # 其他字段
    for key in set(list(new_settings.keys()) + list(cur_settings.keys())):
        if key not in merged:
            if key in new_settings:
                merged[key] = new_settings[key]
            else:
                merged[key] = cur_settings[key]

    if not dry_run:
        with open(cur_file, "w", encoding="utf-8") as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)
            f.write("\n")

    changes.append("  合并: .claude/settings.json")
    return changes


def extract_section(content: str, heading: str) -> str:
    """提取 ## heading 到下一个 ## 之间的内容（包含标题行）"""
    pattern = rf"(^## {re.escape(heading)}.*?)(?=^## |\Z)"
    match = re.search(pattern, content, re.MULTILINE | re.DOTALL)
    return match.group(1).rstrip() if match else ""


def extract_filled_values(content: str) -> dict:
    """扫描 `- key: value` 行，收集非占位符的值"""
    values = {}
    for line in content.split("\n"):
        match = re.match(r"^\s*-\s+(.+?):\s+(.+)$", line)
        if match:
            key = match.group(1).strip()
            value = match.group(2).strip()
            if (
                value
                and not re.match(r"^\{.*\}$", value)
                and not value.startswith("<!--")
            ):
                values[key] = value
    return values


def merge_claude_md(source_path: str, dry_run: bool = False) -> list:
    """全量替换 CLAUDE.md 模板，回填项目状态段和已填写字段"""
    changes = []
    src_file = os.path.join(source_path, "CLAUDE.md")
    cur_file = "CLAUDE.md"

    if not os.path.exists(src_file):
        changes.append("  跳过: 新版无 CLAUDE.md 模板")
        return changes

    if not os.path.exists(cur_file):
        if not dry_run:
            shutil.copy2(src_file, cur_file)
        changes.append("  新增: CLAUDE.md (从新版复制)")
        return changes

    with open(src_file, "r", encoding="utf-8") as f:
        template = f.read()
    with open(cur_file, "r", encoding="utf-8") as f:
        current = f.read()

    project_state = extract_section(current, "项目状态")
    # 从非项目状态区提取已填写值，避免跨段回填
    content_without_state = (
        current.replace(project_state, "") if project_state else current
    )
    filled_values = extract_filled_values(content_without_state)

    if project_state:
        changes.append(f"  保留: 项目状态段 ({len(project_state)} 字符)")
    if filled_values:
        changes.append(f"  保留: {len(filled_values)} 个已填写字段")
        for k in list(filled_values.keys())[:5]:
            changes.append(f"    - {k}: {filled_values[k][:30]}...")

    result = template

    if project_state:
        template_state = extract_section(template, "项目状态")
        if template_state:
            result = result.replace(template_state, project_state, 1)
        changes.append("  回填: 项目状态段")

    lines = result.split("\n")
    for i, line in enumerate(lines):
        match = re.match(r"^(\s*-\s+)(.+?):\s+(\{.*\})(.*)$", line)
        if match:
            prefix = match.group(1)
            key = match.group(2).strip()
            suffix = match.group(4)
            if key in filled_values:
                lines[i] = f"{prefix}{key}: {filled_values[key]}{suffix}"
                changes.append(f"  回填: {key} = {filled_values[key][:30]}")
    result = "\n".join(lines)

    new_ver = read_version(source_path)
    result = re.sub(
        r"(框架版本:\s*)\{.*?\}",
        rf"\g<1>{new_ver}",
        result,
    )

    if not dry_run:
        with open(cur_file, "w", encoding="utf-8") as f:
            f.write(result)

    changes.append("  替换: CLAUDE.md (全量模板+回填)")
    return changes


def get_local_git_head(repo_path: str) -> str:
    """读取本地 git 仓库的 HEAD commit SHA"""
    try:
        result = subprocess.run(
            ["git", "-C", repo_path, "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return ""


def save_upgrade_state(commit_sha: str, version: str):
    """升级成功后将 commit SHA、版本号、日期写入 framework.json 的 upgrade.state"""
    config = load_framework_config()

    upgrade = config.setdefault("upgrade", {})
    state = upgrade.setdefault("state", {})
    state["last_commit"] = commit_sha
    state["last_version"] = version
    state["last_upgrade_date"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    with open(FRAMEWORK_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
        f.write("\n")


def run_local_upgrade(
    source: str, dry_run: bool = False, backup_dir: str = None
) -> int:
    """执行本地升级流程"""
    if not os.path.isdir(source):
        print(f"错误: 源路径不存在: {source}", file=sys.stderr)
        return 1

    if not os.path.exists(os.path.join(source, ".claude")):
        print(
            f"错误: 源路径不是 CataForge 项目 (缺少 .claude/ 目录): {source}",
            file=sys.stderr,
        )
        return 1

    new_ver = read_version(source)
    cur_ver = read_version(".")

    print(f"当前版本: {cur_ver}")
    print(f"新版本:   {new_ver}")

    if parse_semver(new_ver) < parse_semver(cur_ver):
        print(f"警告: 新版本 ({new_ver}) 低于当前版本 ({cur_ver})，将继续执行降级。")
    elif parse_semver(new_ver) == parse_semver(cur_ver):
        print(f"提示: 版本号相同 ({cur_ver})，可能存在非版本号变更。")

    if dry_run:
        print(f"\n[DRY-RUN] 模拟升级 {cur_ver} → {new_ver}:\n")
    else:
        print(f"\n开始升级 {cur_ver} → {new_ver}...\n")

    # 备份
    bak_dir = backup_dir or os.path.join(
        tempfile.gettempdir(),
        f"cataforge-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
    )
    if not dry_run:
        os.makedirs(bak_dir, exist_ok=True)
    print(f"[备份] → {bak_dir}")
    for msg in backup_framework(bak_dir, dry_run):
        print(msg)

    # 覆盖框架文件
    print("\n[框架文件]")
    for msg in copy_framework(source, dry_run):
        print(msg)

    # 合并 settings.json
    print("\n[settings.json]")
    for msg in merge_settings(source, dry_run):
        print(msg)

    # 合并 CLAUDE.md
    print("\n[CLAUDE.md]")
    for msg in merge_claude_md(source, dry_run):
        print(msg)

    # 升级后验证
    if not dry_run:
        print("\n[升级后验证]")
        os.environ["CATAFORGE_OLD_VERSION"] = cur_ver
        # Late import to avoid circular dependency with upgrade.py
        from upgrade import run_verify

        run_verify()

    # 记录升级状态（local 升级尝试读取源路径的 git HEAD）
    if not dry_run:
        source_commit = get_local_git_head(source)
        save_upgrade_state(source_commit, new_ver)

    # 报告
    prefix = "[DRY-RUN] " if dry_run else ""
    label = "预览" if dry_run else "完成"
    print(f"\n{prefix}升级{label}: {cur_ver} → {new_ver}")
    if not dry_run:
        print("建议运行: git diff .claude/ 查看详细变更")
        print(
            "确认后: git add -A .claude/ pyproject.toml CLAUDE.md && git commit -m "
            f'"chore: upgrade CataForge to v{new_ver}"'
        )

    return 0
