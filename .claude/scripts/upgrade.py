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
from urllib.request import Request, urlopen

# ============================================================================
# 公共工具
# ============================================================================

# Ensure UTF-8 output on Windows
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

FRAMEWORK_DIRS = ["agents", "skills", "rules", "hooks", "scripts", "schemas"]
VERSION_FILE = "pyproject.toml"
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

    # hooks: 从新版替换
    if "hooks" in new_settings:
        merged["hooks"] = new_settings["hooks"]
        if "hooks" in cur_settings and cur_settings["hooks"] != new_settings["hooks"]:
            changes.append("  更新: hooks 配置")

    # mcpServers: 合并
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


def load_upgrade_source() -> dict:
    """加载 .claude/upgrade-source.json 配置"""
    config_file = os.path.join(".claude", "upgrade-source.json")
    if not os.path.exists(config_file):
        return {}
    with open(config_file, "r", encoding="utf-8") as f:
        return json.load(f)


def get_github_token(token_env: str) -> str:
    """从环境变量获取 GitHub token"""
    if not token_env:
        return ""
    return os.environ.get(token_env, "")


def _build_url_opener():
    """构建支持代理的 URL opener（从环境变量读取 HTTP_PROXY/HTTPS_PROXY）"""
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


def clone_and_upgrade(
    clone_url: str, branch: str, token: str = "", dry_run: bool = False
) -> int:
    """克隆远程仓库到临时目录，执行本地升级流程"""
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
        return run_local_upgrade(tmpdir, dry_run)

    except subprocess.TimeoutExpired:
        print("错误: git clone 超时", file=sys.stderr)
        return 1
    except FileNotFoundError:
        print("错误: git 命令不可用", file=sys.stderr)
        return 1
    finally:
        cleanup_askpass(env)
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

    if parse_semver(new_ver) <= parse_semver(cur_ver):
        print(f"当前已是最新版本 ({cur_ver})，无需升级。")
        return 2

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


def detect_remote_version(source_type, repo, url, branch, token_env):
    """检测远程版本，返回 (remote_ver, clone_url, token)"""
    token = get_github_token(token_env) if token_env else ""

    if source_type == "github":
        print(f"远程源: GitHub {repo} (分支: {branch})")
        remote_ver = check_version_github(repo, branch, token)
        clone_url = get_github_clone_url(repo)
    else:
        print(f"远程源: Git {url} (分支: {branch})")
        remote_ver = check_version_git_tags(url)
        if not remote_ver:
            print("未找到 semver 标签，尝试读取分支上的版本文件...")
            remote_ver = check_version_git_clone(url, branch, token)
        clone_url = url

    return remote_ver, clone_url, token


def cmd_local(args):
    """子命令: local — 从本地路径升级"""
    sys.exit(run_local_upgrade(args.source_path, args.dry_run, args.backup_dir))


def cmd_check(args):
    """子命令: check — 检测远程是否有新版本"""
    source_type, repo, url, branch, token_env = resolve_remote_source(args)

    if not validate_branch_name(branch):
        print(f"错误: 无效的分支名 '{branch}'", file=sys.stderr)
        sys.exit(1)

    local_ver = read_version(".")
    print(f"当前版本: {local_ver}")

    remote_ver, _, _ = detect_remote_version(source_type, repo, url, branch, token_env)

    if not remote_ver:
        print("错误: 无法获取远程版本", file=sys.stderr)
        sys.exit(1)

    print(f"远程版本: {remote_ver}")

    if parse_semver(remote_ver) <= parse_semver(local_ver):
        print(f"\n当前已是最新版本 ({local_ver})，无需升级。")
        sys.exit(2)

    print(f"\n发现新版本: {local_ver} → {remote_ver}")
    print("\n可运行以下命令升级:")
    print("  python .claude/scripts/upgrade.py upgrade --dry-run  # 预览变更")
    print("  python .claude/scripts/upgrade.py upgrade             # 执行升级")
    sys.exit(0)


def cmd_upgrade(args):
    """子命令: upgrade — 检测 + 执行远程升级"""
    source_type, repo, url, branch, token_env = resolve_remote_source(args)

    if not validate_branch_name(branch):
        print(f"错误: 无效的分支名 '{branch}'", file=sys.stderr)
        sys.exit(1)

    local_ver = read_version(".")
    print(f"当前版本: {local_ver}")

    remote_ver, clone_url, token = detect_remote_version(
        source_type, repo, url, branch, token_env
    )

    if not remote_ver:
        print("错误: 无法获取远程版本", file=sys.stderr)
        sys.exit(1)

    print(f"远程版本: {remote_ver}")

    if parse_semver(remote_ver) <= parse_semver(local_ver):
        print(f"\n当前已是最新版本 ({local_ver})，无需升级。")
        sys.exit(2)

    print(f"\n发现新版本: {local_ver} → {remote_ver}")
    exit_code = clone_and_upgrade(clone_url, branch, token=token, dry_run=args.dry_run)
    sys.exit(exit_code)


def cmd_verify(args):
    """子命令: verify — 升级后验证"""
    sys.exit(run_verify())


# ============================================================================
# CLI 主入口
# ============================================================================


def main():
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
