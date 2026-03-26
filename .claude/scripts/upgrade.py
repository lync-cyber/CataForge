#!/usr/bin/env python3
"""upgrade.py — CataForge 框架升级工具

用法: python .claude/scripts/upgrade.py <source_path> [--dry-run] [--backup-dir <path>]
  source_path: CataForge 新版本的根目录路径
  --dry-run:   仅显示将要执行的操作，不实际修改
  --backup-dir: 自定义备份目录（默认 .claude/backup-{timestamp}）

返回: exit 0=成功, exit 1=失败, exit 2=无需升级
"""

import argparse
import io
import json
import os
import re
import shutil
import sys
from datetime import datetime

# Ensure UTF-8 output on Windows
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

FRAMEWORK_DIRS = ["agents", "skills", "rules", "hooks", "scripts", "schemas"]
VERSION_FILE = "pyproject.toml"


def load_json_lenient(file_path: str) -> dict:
    """加载 JSON 文件，容忍尾随逗号等常见格式问题"""
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    # 移除尾随逗号 (逗号后跟 ] 或 })
    content = re.sub(r",\s*([}\]])", r"\1", content)
    return json.loads(content)


# ============================================================================
# 模块 1: 版本比较
# ============================================================================


def parse_semver(ver_str: str) -> tuple[int, int, int]:
    """解析 semver 字符串为 (major, minor, patch) 元组"""
    ver_str = ver_str.strip()
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)", ver_str)
    if not match:
        return (0, 0, 0)
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def read_version(base_path: str) -> str:
    """从目录读取 pyproject.toml 中的 [project].version"""
    ver_file = os.path.join(base_path, VERSION_FILE)
    if not os.path.exists(ver_file):
        return "0.0.0"
    with open(ver_file, "r", encoding="utf-8") as f:
        content = f.read()
    match = re.search(r'^version\s*=\s*"([^"]+)"', content, re.MULTILINE)
    return match.group(1) if match else "0.0.0"


# ============================================================================
# 模块 2: 框架文件覆盖
# ============================================================================


def backup_framework(backup_dir: str, dry_run: bool = False) -> list[str]:
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

    # 备份版本文件
    if os.path.exists(VERSION_FILE):
        dst = os.path.join(backup_dir, VERSION_FILE)
        if not dry_run:
            shutil.copy2(VERSION_FILE, dst)
        backed_up.append(f"  备份: {VERSION_FILE} → {dst}")

    # 备份 settings.json
    settings = os.path.join(claude_dir, "settings.json")
    if os.path.exists(settings):
        dst = os.path.join(backup_dir, "settings.json")
        if not dry_run:
            shutil.copy2(settings, dst)
        backed_up.append(f"  备份: {settings} → {dst}")

    return backed_up


def copy_framework(source_path: str, dry_run: bool = False) -> list[str]:
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
            # 统计文件变化
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
            # 仅更新 version 字段，保留用户可能添加的其他配置
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

    # 复制 compat-matrix.json
    src_compat = os.path.join(source_path, ".claude", "compat-matrix.json")
    dst_compat = os.path.join(".claude", "compat-matrix.json")
    if os.path.exists(src_compat):
        if not dry_run:
            shutil.copy2(src_compat, dst_compat)
        changes.append("  更新: .claude/compat-matrix.json")

    # 合并 upgrade-source.json（保留用户已配置的 repo/url，补充新字段）
    src_upgrade_source = os.path.join(source_path, ".claude", "upgrade-source.json")
    dst_upgrade_source = os.path.join(".claude", "upgrade-source.json")
    if os.path.exists(src_upgrade_source):
        if os.path.exists(dst_upgrade_source):
            # 保留用户已配置的值，仅补充新字段
            try:
                with open(src_upgrade_source, "r", encoding="utf-8") as f:
                    new_source = json.load(f)
                with open(dst_upgrade_source, "r", encoding="utf-8") as f:
                    cur_source = json.load(f)
                for k, v in new_source.items():
                    if k not in cur_source:
                        cur_source[k] = v
                if not dry_run:
                    with open(dst_upgrade_source, "w", encoding="utf-8") as f:
                        json.dump(cur_source, f, ensure_ascii=False, indent=2)
                        f.write("\n")
                changes.append("  合并: .claude/upgrade-source.json")
            except (json.JSONDecodeError, OSError):
                changes.append("  跳过: .claude/upgrade-source.json (解析失败)")
        else:
            if not dry_run:
                shutil.copy2(src_upgrade_source, dst_upgrade_source)
            changes.append("  新增: .claude/upgrade-source.json")

    return changes


# ============================================================================
# 模块 3: settings.json 合并
# ============================================================================


def merge_settings(source_path: str, dry_run: bool = False) -> list[str]:
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

    # $schema: 从新版
    if "$schema" in new_settings:
        merged["$schema"] = new_settings["$schema"]
    elif "$schema" in cur_settings:
        merged["$schema"] = cur_settings["$schema"]

    # env: 保留当前
    if "env" in cur_settings:
        merged["env"] = cur_settings["env"]
        # 新版有新 env 则补充
        if "env" in new_settings:
            for k, v in new_settings["env"].items():
                if k not in merged["env"]:
                    merged["env"][k] = v
                    changes.append(f"  新增 env: {k}")
    elif "env" in new_settings:
        merged["env"] = new_settings["env"]

    # permissions: 保留当前
    if "permissions" in cur_settings:
        merged["permissions"] = cur_settings["permissions"]
        # 新版有新 allow 条目则追加
        if "permissions" in new_settings:
            new_allow = set(new_settings.get("permissions", {}).get("allow", []))
            cur_allow = set(cur_settings.get("permissions", {}).get("allow", []))
            added = new_allow - cur_allow
            if added:
                merged["permissions"]["allow"] = list(cur_allow | new_allow)
                changes.append(f"  新增 permissions.allow: {len(added)} 条")
    elif "permissions" in new_settings:
        merged["permissions"] = new_settings["permissions"]

    # hooks: 从新版替换
    if "hooks" in new_settings:
        merged["hooks"] = new_settings["hooks"]
        if "hooks" in cur_settings and cur_settings["hooks"] != new_settings["hooks"]:
            changes.append("  更新: hooks 配置")

    # mcpServers: 合并 (同名覆盖, 独有保留)
    cur_servers = cur_settings.get("mcpServers", {})
    new_servers = new_settings.get("mcpServers", {})
    if cur_servers or new_servers:
        merged_servers = {**cur_servers, **new_servers}
        merged["mcpServers"] = merged_servers
        added_servers = set(new_servers.keys()) - set(cur_servers.keys())
        kept_servers = set(cur_servers.keys()) - set(new_servers.keys())
        if added_servers:
            changes.append(f"  新增 mcpServers: {', '.join(added_servers)}")
        if kept_servers:
            changes.append(f"  保留用户 mcpServers: {', '.join(kept_servers)}")

    # 其他字段: 新版优先, 当前独有保留
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


# ============================================================================
# 模块 4: CLAUDE.md 全量替换+回填
# ============================================================================


def extract_section(content: str, heading: str) -> str:
    """提取 ## heading 到下一个 ## 之间的内容（包含标题行）"""
    pattern = rf"(^## {re.escape(heading)}.*?)(?=^## |\Z)"
    match = re.search(pattern, content, re.MULTILINE | re.DOTALL)
    return match.group(1).rstrip() if match else ""


def extract_filled_values(content: str) -> dict[str, str]:
    """扫描 `- key: value` 行，收集非占位符的值。返回 {key: value}"""
    values = {}
    for line in content.split("\n"):
        # 匹配 `- key: value` 格式（支持前导空格）
        match = re.match(r"^\s*-\s+(.+?):\s+(.+)$", line)
        if match:
            key = match.group(1).strip()
            value = match.group(2).strip()
            # 跳过占位符 {xxx} 和 HTML注释
            if (
                value
                and not re.match(r"^\{.*\}$", value)
                and not value.startswith("<!--")
            ):
                values[key] = value
    return values


def merge_claude_md(source_path: str, dry_run: bool = False) -> list[str]:
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

    # 提取需要保留的数据
    project_state = extract_section(current, "项目状态")
    filled_values = extract_filled_values(current)

    if project_state:
        changes.append(f"  保留: 项目状态段 ({len(project_state)} 字符)")
    if filled_values:
        changes.append(f"  保留: {len(filled_values)} 个已填写字段")
        for k in list(filled_values.keys())[:5]:
            changes.append(f"    - {k}: {filled_values[k][:30]}...")

    # 用模板替换，然后回填
    result = template

    # 回填项目状态段
    if project_state:
        template_state = extract_section(template, "项目状态")
        if template_state:
            result = result.replace(template_state, project_state)
        changes.append("  回填: 项目状态段")

    # 回填已填写字段（逐行扫描模板，匹配 key 后替换占位符值）
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

    # 回填框架版本
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


# ============================================================================
# 主流程
# ============================================================================


def main():
    parser = argparse.ArgumentParser(
        description="CataForge framework upgrade tool",
        epilog="Example: python .claude/scripts/upgrade.py /path/to/CataForge-new --dry-run",
    )
    parser.add_argument(
        "source_path", help="Path to new CataForge version root directory"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Show changes without modifying files"
    )
    parser.add_argument(
        "--backup-dir", default=None, help="Custom backup directory path"
    )
    args = parser.parse_args()

    source = args.source_path
    dry_run = args.dry_run

    # 验证源路径
    if not os.path.isdir(source):
        print(f"错误: 源路径不存在: {source}", file=sys.stderr)
        sys.exit(1)

    if not os.path.exists(os.path.join(source, ".claude")):
        print(
            f"错误: 源路径不是 CataForge 项目 (缺少 .claude/ 目录): {source}",
            file=sys.stderr,
        )
        sys.exit(1)

    # 1. 版本比较
    new_ver = read_version(source)
    cur_ver = read_version(".")

    print(f"当前版本: {cur_ver}")
    print(f"新版本:   {new_ver}")

    if parse_semver(new_ver) <= parse_semver(cur_ver):
        print(f"当前已是最新版本 ({cur_ver})，无需升级。")
        sys.exit(2)

    if dry_run:
        print(f"\n[DRY-RUN] 模拟升级 {cur_ver} → {new_ver}:\n")
    else:
        print(f"\n开始升级 {cur_ver} → {new_ver}...\n")

    # 2. 备份
    backup_dir = (
        args.backup_dir or f".claude/backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    )
    if not dry_run:
        os.makedirs(backup_dir, exist_ok=True)
    print(f"[备份] → {backup_dir}")
    for msg in backup_framework(backup_dir, dry_run):
        print(msg)

    # 3. 覆盖框架文件
    print("\n[框架文件]")
    for msg in copy_framework(source, dry_run):
        print(msg)

    # 4. 合并 settings.json
    print("\n[settings.json]")
    for msg in merge_settings(source, dry_run):
        print(msg)

    # 5. 合并 CLAUDE.md
    print("\n[CLAUDE.md]")
    for msg in merge_claude_md(source, dry_run):
        print(msg)

    # 6. 升级后验证
    if not dry_run:
        post_check = os.path.join(".claude", "scripts", "post_upgrade_check.py")
        if os.path.exists(post_check):
            print("\n[升级后验证]")
            import subprocess

            env = os.environ.copy()
            env["CATAFORGE_OLD_VERSION"] = cur_ver
            result = subprocess.run([sys.executable, post_check], env=env, timeout=120)
            if result.returncode != 0:
                print("\n警告: 升级后验证发现问题，请检查上方输出")

    # 7. 报告
    print(
        f"\n{'[DRY-RUN] ' if dry_run else ''}升级{'预览' if dry_run else '完成'}: {cur_ver} → {new_ver}"
    )
    if not dry_run:
        print("建议运行: git diff .claude/ 查看详细变更")
        print(
            '确认后: git add -A .claude/ pyproject.toml CLAUDE.md && git commit -m "chore: upgrade CataForge to v'
            + new_ver
            + '"'
        )

    sys.exit(0)


if __name__ == "__main__":
    main()
