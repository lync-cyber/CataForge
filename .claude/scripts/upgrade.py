#!/usr/bin/env python3
"""upgrade.py — CataForge 统一升级工具

子命令:
  local   <source_path>   从本地路径升级框架文件
  check                   检测远程是否有新版本
  upgrade                 检测 + 执行远程升级
  verify                  升级后验证（文件完整性 + 功能适用性）

用法:
  python .claude/scripts/upgrade.py local /path/to/new [--dry-run] [--backup-dir <dir>]
  python .claude/scripts/upgrade.py check [--repo owner/repo] [--url URL] [--branch main]
  python .claude/scripts/upgrade.py upgrade [--repo owner/repo] [--url URL] [--dry-run]
  python .claude/scripts/upgrade.py verify

返回: exit 0=成功, exit 1=失败, exit 2=无需升级/已是最新
"""

import argparse
import base64
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener, urlopen

# ============================================================================
# 公共工具
# ============================================================================

# 共享工具
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import ensure_utf8_stdio, load_dotenv

ensure_utf8_stdio()

FRAMEWORK_DIRS = ["agents", "skills", "rules", "hooks", "scripts", "schemas"]
VERSION_FILE = "pyproject.toml"

# 自升级相关环境变量（见 §自升级机制）
SELF_UPGRADE_MARKER = "CATAFORGE_SELF_UPGRADED"
SELF_UPGRADE_SRC_ENV = "CATAFORGE_SELF_UPGRADE_SRC"
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
    """解析 semver 字符串为 (major, minor, patch) 元组，支持可选 v 前缀"""
    ver_str = ver_str.strip()
    match = re.match(r"^v?(\d+)\.(\d+)\.(\d+)", ver_str)
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


def load_json_lenient(file_path: str) -> dict:
    """加载 JSON 文件，容忍尾随逗号等常见格式问题"""
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    content = re.sub(r",\s*([}\]])", r"\1", content)
    return json.loads(content)


def phase_index(phase: str) -> int:
    """返回阶段在生命周期中的索引，未知阶段返回 -1"""
    try:
        return PHASE_ORDER.index(phase)
    except ValueError:
        return -1


def validate_branch_name(branch: str) -> bool:
    """校验分支名，防止注入异常字符"""
    return bool(re.match(r"^[a-zA-Z0-9._/-]+$", branch))


# ============================================================================
# 模块 A: 本地升级 (backup / copy / merge)
# ============================================================================


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

    # 复制 compat-matrix.json
    src_compat = os.path.join(source_path, ".claude", "compat-matrix.json")
    dst_compat = os.path.join(".claude", "compat-matrix.json")
    if os.path.exists(src_compat):
        if not dry_run:
            shutil.copy2(src_compat, dst_compat)
        changes.append("  更新: .claude/compat-matrix.json")

    # 合并 upgrade-source.json
    src_upgrade_source = os.path.join(source_path, ".claude", "upgrade-source.json")
    dst_upgrade_source = os.path.join(".claude", "upgrade-source.json")
    if os.path.exists(src_upgrade_source):
        if os.path.exists(dst_upgrade_source):
            try:
                with open(src_upgrade_source, "r", encoding="utf-8") as f:
                    new_source = json.load(f)
                with open(dst_upgrade_source, "r", encoding="utf-8") as f:
                    cur_source = json.load(f)
                # last_* 字段为项目本地状态，始终保留当前值
                local_state_keys = {"last_commit", "last_version", "last_upgrade_date"}
                for k, v in new_source.items():
                    if k in local_state_keys:
                        continue  # 不覆盖本地升级状态
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
    filled_values = extract_filled_values(current)

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
            result = result.replace(template_state, project_state)
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


# ============================================================================
# 模块 B: 远程检测 (GitHub API / Git tags / shallow clone)
# ============================================================================


def _load_dotenv():
    """从 .env 文件加载配置到 os.environ。委托 _common.load_dotenv()。"""
    load_dotenv()


def load_upgrade_source() -> dict:
    """加载 .claude/upgrade-source.json 配置"""
    config_file = os.path.join(".claude", "upgrade-source.json")
    if not os.path.exists(config_file):
        return {}
    with open(config_file, "r", encoding="utf-8") as f:
        return json.load(f)


def get_github_token(token_env: str) -> str:
    """从环境变量获取 GitHub token（.env 已由 _load_dotenv 预加载）"""
    if not token_env:
        return ""
    return os.environ.get(token_env, "")


def _build_url_opener():
    """构建支持代理的 URL opener（从环境变量读取，.env 已预加载）"""
    proxies = {}
    for var in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        val = os.environ.get(var)
        if val:
            proxies.setdefault("https", val)
            proxies.setdefault("http", val)
    if proxies:
        return build_opener(ProxyHandler(proxies))
    return None


def check_version_github(repo: str, branch: str, token: str) -> str:
    """通过 GitHub API 读取远程 pyproject.toml 中的版本号（无需 clone）"""
    url = f"https://api.github.com/repos/{repo}/contents/pyproject.toml?ref={branch}"
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "CataForge-Upgrade-Checker",
    }
    if token:
        headers["Authorization"] = f"token {token}"

    try:
        req = Request(url, headers=headers)
        opener = _build_url_opener()
        if opener:
            resp = opener.open(req, timeout=30)
        else:
            resp = urlopen(req, timeout=30)
        with resp:
            data = json.loads(resp.read().decode("utf-8"))
            content = base64.b64decode(data["content"]).decode("utf-8").strip()
            match = re.search(r'^version\s*=\s*"([^"]+)"', content, re.MULTILINE)
            return match.group(1) if match else ""
    except HTTPError as e:
        if e.code == 404:
            print(f"错误: GitHub 仓库 {repo} 或分支 {branch} 不存在", file=sys.stderr)
        elif e.code in (401, 403):
            print(
                f"错误: GitHub API 认证失败 (HTTP {e.code})。如为私有仓库，请设置 token_env 环境变量",
                file=sys.stderr,
            )
        else:
            print(f"错误: GitHub API 返回 HTTP {e.code}", file=sys.stderr)
        return ""
    except URLError as e:
        print(f"错误: 无法连接 GitHub API ({e.reason})", file=sys.stderr)
        return ""
    except Exception as e:
        print(f"错误: GitHub API 调用失败 ({e})", file=sys.stderr)
        return ""


def get_github_clone_url(repo: str) -> str:
    """构造 GitHub 仓库的 clone URL"""
    return f"https://github.com/{repo}.git"


def build_clone_env(token: str) -> dict:
    """构建 git clone 环境变量，通过 GIT_ASKPASS 安全传递 Token"""
    env = os.environ.copy()
    if token:
        askpass_script = os.path.join(
            tempfile.gettempdir(), f"cataforge_askpass_{os.getpid()}.py"
        )
        with open(askpass_script, "w", encoding="utf-8") as f:
            f.write(f'#!/usr/bin/env python3\nimport sys\nprint("{token}")\n')
        try:
            os.chmod(askpass_script, 0o700)
        except OSError:
            pass  # Windows
        env["GIT_ASKPASS"] = askpass_script
        env["GIT_TERMINAL_PROMPT"] = "0"
        env["_CATAFORGE_ASKPASS_SCRIPT"] = askpass_script
    return env


def cleanup_askpass(env: dict):
    """清理临时 askpass 脚本"""
    askpass_script = env.get("_CATAFORGE_ASKPASS_SCRIPT", "")
    if askpass_script and os.path.exists(askpass_script):
        try:
            os.unlink(askpass_script)
        except OSError:
            print(
                f"警告: 无法清理临时文件 {askpass_script}，请手动删除", file=sys.stderr
            )


def get_remote_commit_github(repo: str, branch: str, token: str) -> str:
    """通过 GitHub API 获取远程分支的最新 commit SHA"""
    url = f"https://api.github.com/repos/{repo}/commits/{branch}"
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "CataForge-Upgrade-Checker",
    }
    if token:
        headers["Authorization"] = f"token {token}"

    try:
        req = Request(url, headers=headers)
        opener = _build_url_opener()
        if opener:
            resp = opener.open(req, timeout=30)
        else:
            resp = urlopen(req, timeout=30)
        with resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("sha", "")
    except (HTTPError, URLError, Exception) as e:
        print(f"警告: 无法获取远程 commit SHA ({e})", file=sys.stderr)
        return ""


def get_remote_commit_git(url: str, branch: str) -> str:
    """通过 git ls-remote 获取远程分支的最新 commit SHA"""
    try:
        result = subprocess.run(
            ["git", "ls-remote", url, f"refs/heads/{branch}"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            print(f"警告: git ls-remote 失败: {result.stderr.strip()}", file=sys.stderr)
            return ""
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) >= 2:
                return parts[0].strip()
        return ""
    except subprocess.TimeoutExpired:
        print("警告: git ls-remote 超时", file=sys.stderr)
        return ""
    except FileNotFoundError:
        print("错误: git 命令不可用", file=sys.stderr)
        return ""


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
    """升级成功后将 commit SHA、版本号、日期写入 upgrade-source.json"""
    config_file = os.path.join(".claude", "upgrade-source.json")
    config = {}
    if os.path.exists(config_file):
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                config = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass

    config["last_commit"] = commit_sha
    config["last_version"] = version
    config["last_upgrade_date"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
        f.write("\n")


def check_version_git_tags(url: str) -> str:
    """通过 git ls-remote --tags 检测最新 semver 标签"""
    try:
        result = subprocess.run(
            ["git", "ls-remote", "--tags", url],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            print(f"警告: git ls-remote 失败: {result.stderr.strip()}", file=sys.stderr)
            return ""

        versions = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            ref = parts[1].strip()
            tag_match = re.search(r"refs/tags/(v?\d+\.\d+\.\d+)$", ref)
            if tag_match:
                tag = tag_match.group(1)
                versions.append((parse_semver(tag), tag))

        if not versions:
            return ""
        versions.sort(key=lambda x: x[0], reverse=True)
        return versions[0][1].lstrip("v")
    except subprocess.TimeoutExpired:
        print("警告: git ls-remote 超时", file=sys.stderr)
        return ""
    except FileNotFoundError:
        print("错误: git 命令不可用", file=sys.stderr)
        return ""


def check_version_git_clone(url: str, branch: str, token: str = "") -> str:
    """通过浅克隆读取远程 pyproject.toml 中的版本号（最后手段）"""
    if not validate_branch_name(branch):
        print(f"错误: 无效的分支名: {branch}", file=sys.stderr)
        return ""
    tmpdir = tempfile.mkdtemp(prefix="cataforge-check-")
    env = build_clone_env(token)
    try:
        result = subprocess.run(
            [
                "git",
                "clone",
                "--depth",
                "1",
                "--single-branch",
                "-b",
                branch,
                url,
                tmpdir,
            ],
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
        )
        if result.returncode != 0:
            print(f"警告: git clone 失败: {result.stderr.strip()}", file=sys.stderr)
            return ""
        ver_file = os.path.join(tmpdir, "pyproject.toml")
        if not os.path.exists(ver_file):
            return ""
        with open(ver_file, "r", encoding="utf-8") as f:
            content = f.read()
        match = re.search(r'^version\s*=\s*"([^"]+)"', content, re.MULTILINE)
        return match.group(1) if match else ""
    except subprocess.TimeoutExpired:
        print("警告: git clone 超时", file=sys.stderr)
        return ""
    except FileNotFoundError:
        print("错误: git 命令不可用", file=sys.stderr)
        return ""
    finally:
        cleanup_askpass(env)
        shutil.rmtree(tmpdir, ignore_errors=True)


def _file_sha256(path: str) -> str:
    """计算文件 SHA256 哈希，文件不存在返回空字符串"""
    if not os.path.isfile(path):
        return ""
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except OSError:
        return ""


def maybe_self_reexec(tmpdir: str, dry_run: bool) -> None:
    """自升级机制: 若远程 upgrade.py 与当前运行的脚本内容不同，exec 到新版本继续。

    两阶段升级流程:
      第一阶段 (旧脚本): 克隆远程 → 检测新版 upgrade.py → os.execve 到新脚本 → 退出
      第二阶段 (新脚本): 读取 CATAFORGE_SELF_UPGRADE_SRC 获知已克隆目录 → 跳过克隆 → 直接 local 升级

    递归保护: 通过 SELF_UPGRADE_MARKER 环境变量防止无限 re-exec。
    """
    if os.environ.get(SELF_UPGRADE_MARKER):
        return  # 已是第二阶段，继续正常流程

    new_script = os.path.join(tmpdir, ".claude", "scripts", "upgrade.py")
    cur_script = os.path.abspath(sys.argv[0])
    if not os.path.isfile(new_script):
        return  # 新版本不含 upgrade.py（异常情况，跳过自升级）

    new_hash = _file_sha256(new_script)
    cur_hash = _file_sha256(cur_script)
    if not new_hash or new_hash == cur_hash:
        return  # 哈希相同或读取失败，无需自升级

    print("\n[自升级] 检测到 upgrade.py 自身有更新，切换到新版本继续执行...")
    print(f"  当前: {cur_script[:12]}... (sha256: {cur_hash[:12]})")
    print(f"  新版: {new_script[:12]}... (sha256: {new_hash[:12]})")

    env = os.environ.copy()
    env[SELF_UPGRADE_MARKER] = "1"
    env[SELF_UPGRADE_SRC_ENV] = tmpdir  # 告知第二阶段复用已克隆目录

    # 第二阶段以 local 子命令接管: 源路径=tmpdir
    new_argv = [sys.executable, new_script, "local", tmpdir]
    if dry_run:
        new_argv.append("--dry-run")

    try:
        os.execve(sys.executable, new_argv, env)
    except OSError as e:
        # exec 失败 → 回退到当前脚本继续执行（兜底）
        print(f"[自升级] os.execve 失败，回退到当前脚本: {e}", file=sys.stderr)


def clone_and_upgrade(
    clone_url: str, branch: str, token: str = "", dry_run: bool = False
) -> int:
    """克隆远程仓库到临时目录，执行本地升级流程。

    自升级支持: 若第一阶段检测到 upgrade.py 有更新，os.execve 到新脚本继续。
    第二阶段通过 CATAFORGE_SELF_UPGRADE_SRC 环境变量复用已克隆目录。
    """
    if not validate_branch_name(branch):
        print(f"错误: 无效的分支名: {branch}", file=sys.stderr)
        return 1

    tmpdir = tempfile.mkdtemp(prefix="cataforge-upgrade-")
    env = build_clone_env(token)
    print("\n正在克隆远程仓库到临时目录...")

    try:
        result = subprocess.run(
            [
                "git",
                "clone",
                "--depth",
                "1",
                "--single-branch",
                "-b",
                branch,
                clone_url,
                tmpdir,
            ],
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
        )
        if result.returncode != 0:
            print(f"错误: git clone 失败: {result.stderr.strip()}", file=sys.stderr)
            return 1

        print(f"克隆完成: {tmpdir}")

        # 自升级检测: 若新版 upgrade.py 与当前不同，exec 到新脚本（不返回）
        maybe_self_reexec(tmpdir, dry_run)

        return run_local_upgrade(tmpdir, dry_run)

    except subprocess.TimeoutExpired:
        print("错误: git clone 超时", file=sys.stderr)
        return 1
    except FileNotFoundError:
        print("错误: git 命令不可用", file=sys.stderr)
        return 1
    finally:
        cleanup_askpass(env)
        # 若已 exec 到第二阶段，此 finally 不会触发（os.execve 替换进程镜像）
        print(f"\n清理临时目录: {tmpdir}")
        shutil.rmtree(tmpdir, ignore_errors=True)


# ============================================================================
# 模块 C: 升级后验证
# ============================================================================


def read_project_phase() -> str:
    """从 CLAUDE.md 读取当前项目阶段"""
    claude_md = "CLAUDE.md"
    if not os.path.exists(claude_md):
        return ""
    with open(claude_md, "r", encoding="utf-8") as f:
        content = f.read()
    match = re.search(r"当前阶段:\s*(\S+)", content)
    return match.group(1) if match else ""


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


def check_migration_artifacts() -> list:
    """数据驱动的迁移检查: 从 compat-matrix.json 的 `migration_checks` 字段
    读取每次 release 声明的强制约束并执行。

    每个 migration check 声明:
      {
        "id": "mc-0.6.0-001",
        "description": "...",
        "release_version": "0.6.0",
        "type": "file_must_exist" | "file_must_contain" | "file_must_not_contain",
        "path": ".claude/rules/COMMON-RULES.md",
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
    current_phase = read_project_phase()
    has_issues = False

    print(f"\n框架版本: {current_version}")
    print(f"项目阶段: {current_phase or '(未设置/新项目)'}")

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
        print("\n--- 未找到 compat-matrix.json，跳过功能适用性检查 ---")

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

    # 迁移检查 (数据驱动: 读取 compat-matrix.json 的 migration_checks 字段)
    print("\n--- 迁移检查 (compat-matrix.migration_checks) ---")
    mig_issues = check_migration_artifacts()
    if mig_issues:
        has_issues = True
        print(f"  发现 {len(mig_issues)} 个问题:")
        for issue in mig_issues:
            print(f"  [错误] {issue}")
    else:
        matrix = load_compat_matrix()
        mc_count = len(matrix.get("migration_checks", []))
        if mc_count > 0:
            print(f"  通过 {mc_count} 项迁移检查。")
        else:
            print("  compat-matrix.json 未声明 migration_checks，跳过。")

    print("\n" + "=" * 60)
    if has_issues:
        print("验证结果: 发现问题，请检查上方输出")
        return 1
    else:
        print("验证结果: 通过")
        return 0


# ============================================================================
# 子命令入口
# ============================================================================


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
    bak_dir = backup_dir or f".claude/backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
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


def resolve_remote_source(args) -> tuple:
    """解析远程源参数，返回 (source_type, repo, url, branch, token_env)"""
    config = load_upgrade_source()

    branch = getattr(args, "branch", None) or config.get("branch", "main")
    token_env = getattr(args, "token_env", None) or config.get("token_env", "")

    repo_arg = getattr(args, "repo", None)
    url_arg = getattr(args, "url", None)

    if repo_arg:
        return "github", repo_arg, None, branch, token_env
    elif url_arg:
        return "git", None, url_arg, branch, token_env
    elif config.get("type") == "github" and config.get("repo"):
        return "github", config["repo"], None, branch, token_env
    elif config.get("type") == "git" and config.get("url"):
        return "git", None, config["url"], branch, token_env
    else:
        print(
            "错误: 未配置远程源。请提供 --repo 或 --url 参数，或配置 .claude/upgrade-source.json",
            file=sys.stderr,
        )
        sys.exit(1)


def detect_remote_state(source_type, repo, url, branch, token_env):
    """检测远程状态，返回 (remote_ver, remote_commit, clone_url, token)"""
    token = get_github_token(token_env) if token_env else ""

    if source_type == "github":
        print(f"远程源: GitHub {repo} (分支: {branch})")
        remote_ver = check_version_github(repo, branch, token)
        remote_commit = get_remote_commit_github(repo, branch, token)
        clone_url = get_github_clone_url(repo)
    else:
        print(f"远程源: Git {url} (分支: {branch})")
        remote_ver = check_version_git_tags(url)
        if not remote_ver:
            print("未找到 semver 标签，尝试读取分支上的版本文件...")
            remote_ver = check_version_git_clone(url, branch, token)
        remote_commit = get_remote_commit_git(url, branch)
        clone_url = url

    return remote_ver, remote_commit, clone_url, token


def cmd_local(args):
    """子命令: local — 从本地路径升级。

    自升级第二阶段兜底: 若 CATAFORGE_SELF_UPGRADE_SRC 指向当前 source_path，
    说明该目录是上阶段克隆的临时目录，升级成功后需主动清理（第一阶段 finally
    因 os.execve 替换进程未触发）。
    """
    exit_code = run_local_upgrade(args.source_path, args.dry_run, args.backup_dir)

    self_upgrade_src = os.environ.get(SELF_UPGRADE_SRC_ENV, "")
    if (
        self_upgrade_src
        and os.path.abspath(self_upgrade_src) == os.path.abspath(args.source_path)
        and os.path.isdir(self_upgrade_src)
    ):
        try:
            shutil.rmtree(self_upgrade_src, ignore_errors=True)
            print(f"\n[自升级] 清理临时目录: {self_upgrade_src}")
        except OSError:
            pass

    sys.exit(exit_code)


def cmd_check(args):
    """子命令: check — 检测远程是否有新版本（优先使用 commit SHA 比较）"""
    source_type, repo, url, branch, token_env = resolve_remote_source(args)

    if not validate_branch_name(branch):
        print(f"错误: 无效的分支名 '{branch}'", file=sys.stderr)
        sys.exit(1)

    local_ver = read_version(".")
    config = load_upgrade_source()
    last_commit = config.get("last_commit", "")

    print(f"当前版本: {local_ver}")
    if last_commit:
        print(f"上次升级 commit: {last_commit[:12]}")

    remote_ver, remote_commit, _, _ = detect_remote_state(
        source_type, repo, url, branch, token_env
    )

    if not remote_ver and not remote_commit:
        print("错误: 无法获取远程版本和 commit 信息", file=sys.stderr)
        sys.exit(1)

    if remote_ver:
        print(f"远程版本: {remote_ver}")
    if remote_commit:
        print(f"远程 commit: {remote_commit[:12]}")

    # 优先使用 commit SHA 比较
    if remote_commit and last_commit:
        if remote_commit == last_commit:
            print(f"\n当前已是最新 (commit: {last_commit[:12]})，无需升级。")
            sys.exit(2)
        else:
            print(f"\n发现更新: commit {last_commit[:12]} → {remote_commit[:12]}")
            if remote_ver:
                print(f"版本: {local_ver} → {remote_ver}")
    elif not last_commit:
        # 首次检测（无历史记录），视为有更新
        print("\n首次检测，无历史升级记录。")
        if remote_commit:
            print(f"远程 commit: {remote_commit[:12]}")
    elif remote_ver:
        # 无法获取 remote_commit，回退到版本号比较
        if parse_semver(remote_ver) <= parse_semver(local_ver):
            print(f"\n当前已是最新版本 ({local_ver})，无需升级。")
            sys.exit(2)
        print(f"\n发现新版本: {local_ver} → {remote_ver}")
    else:
        print(f"\n检测到远程 commit 变更: {remote_commit[:12]}")

    print("\n可运行以下命令升级:")
    print("  python .claude/scripts/upgrade.py upgrade --dry-run  # 预览变更")
    print("  python .claude/scripts/upgrade.py upgrade             # 执行升级")
    sys.exit(0)


def cmd_upgrade(args):
    """子命令: upgrade — 检测 + 执行远程升级（优先使用 commit SHA 比较）。

    注: 自升级第二阶段由 maybe_self_reexec 以 `local <tmpdir>` 形式重启，
    落点是 cmd_local 而非 cmd_upgrade。临时目录清理在 cmd_local 完成。
    """
    source_type, repo, url, branch, token_env = resolve_remote_source(args)
    force = getattr(args, "force", False)

    if not validate_branch_name(branch):
        print(f"错误: 无效的分支名 '{branch}'", file=sys.stderr)
        sys.exit(1)

    local_ver = read_version(".")
    config = load_upgrade_source()
    last_commit = config.get("last_commit", "")

    print(f"当前版本: {local_ver}")
    if last_commit:
        print(f"上次升级 commit: {last_commit[:12]}")

    remote_ver, remote_commit, clone_url, token = detect_remote_state(
        source_type, repo, url, branch, token_env
    )

    if not remote_ver and not remote_commit:
        print("错误: 无法获取远程版本和 commit 信息", file=sys.stderr)
        sys.exit(1)

    if remote_ver:
        print(f"远程版本: {remote_ver}")
    if remote_commit:
        print(f"远程 commit: {remote_commit[:12]}")

    # 判断是否需要升级
    needs_upgrade = True
    if remote_commit and last_commit:
        if remote_commit == last_commit:
            if force:
                print("\ncommit 相同，但 --force 强制升级。")
            else:
                print(f"\n当前已是最新 (commit: {last_commit[:12]})，无需升级。")
                sys.exit(2)
            needs_upgrade = force
    elif not last_commit:
        # 首次升级（无历史记录），始终执行
        print("\n首次升级，无历史升级记录。")
    elif remote_ver:
        # 无法获取 remote_commit，回退到版本号比较
        if parse_semver(remote_ver) <= parse_semver(local_ver):
            if force:
                print("\n版本相同或更低，但 --force 强制升级。")
            else:
                print(f"\n当前已是最新版本 ({local_ver})，无需升级。")
                sys.exit(2)
            needs_upgrade = force

    if needs_upgrade:
        ver_info = f"{local_ver} → {remote_ver}" if remote_ver else ""
        commit_info = ""
        if remote_commit:
            commit_info = f"commit {last_commit[:12] if last_commit else '(首次)'} → {remote_commit[:12]}"
        summary = " | ".join(filter(None, [ver_info, commit_info]))
        if summary:
            print(f"\n升级: {summary}")

    exit_code = clone_and_upgrade(clone_url, branch, token=token, dry_run=args.dry_run)

    # 升级成功后记录状态
    if exit_code == 0 and not args.dry_run:
        new_ver = read_version(".")
        save_upgrade_state(remote_commit or "", new_ver)
        print("\n已记录升级状态到 .claude/upgrade-source.json")

    sys.exit(exit_code)


def cmd_verify(args):
    """子命令: verify — 升级后验证"""
    sys.exit(run_verify())


# ============================================================================
# CLI 主入口
# ============================================================================


def main():
    # 优先从 .env 文件加载配置（代理、GITHUB_TOKEN 等）
    _load_dotenv()

    parser = argparse.ArgumentParser(
        description="CataForge 统一升级工具",
        epilog=(
            "示例:\n"
            "  python .claude/scripts/upgrade.py local /path/to/new --dry-run\n"
            "  python .claude/scripts/upgrade.py check --repo owner/CataForge\n"
            "  python .claude/scripts/upgrade.py upgrade --repo owner/CataForge\n"
            "  python .claude/scripts/upgrade.py verify\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # local
    p_local = subparsers.add_parser("local", help="从本地路径升级框架文件")
    p_local.add_argument("source_path", help="CataForge 新版本的根目录路径")
    p_local.add_argument(
        "--dry-run", action="store_true", help="仅显示变更，不实际修改"
    )
    p_local.add_argument("--backup-dir", default=None, help="自定义备份目录路径")
    p_local.set_defaults(func=cmd_local)

    # 远程源参数（check 和 upgrade 共享）
    def add_remote_args(p):
        source_group = p.add_mutually_exclusive_group()
        source_group.add_argument(
            "--repo", type=str, default=None, help="GitHub 仓库 (owner/repo)"
        )
        source_group.add_argument("--url", type=str, default=None, help="Git 仓库 URL")
        p.add_argument("--branch", type=str, default=None, help="分支名 (默认: main)")
        p.add_argument(
            "--token-env", type=str, default=None, help="存放 token 的环境变量名"
        )

    # check
    p_check = subparsers.add_parser("check", help="检测远程是否有新版本")
    add_remote_args(p_check)
    p_check.set_defaults(func=cmd_check)

    # upgrade
    p_upgrade = subparsers.add_parser("upgrade", help="检测 + 执行远程升级")
    add_remote_args(p_upgrade)
    p_upgrade.add_argument(
        "--dry-run", action="store_true", help="仅预览变更，不实际修改"
    )
    p_upgrade.add_argument(
        "--force", action="store_true", help="忽略 commit SHA 比较，强制执行升级"
    )
    p_upgrade.set_defaults(func=cmd_upgrade)

    # verify
    p_verify = subparsers.add_parser(
        "verify", help="升级后验证（文件完整性 + 功能适用性）"
    )
    p_verify.set_defaults(func=cmd_verify)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
