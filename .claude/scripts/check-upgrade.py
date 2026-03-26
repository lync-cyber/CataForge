#!/usr/bin/env python3
"""check-upgrade.py — CataForge 远程升级检测与拉取工具

用法:
  python .claude/scripts/check-upgrade.py --check              # 仅检测新版本
  python .claude/scripts/check-upgrade.py --dry-run            # 检测 + 预览变更
  python .claude/scripts/check-upgrade.py --apply              # 检测 + 执行升级

  # 指定远程源（覆盖配置文件）
  python .claude/scripts/check-upgrade.py --check --repo owner/CataForge
  python .claude/scripts/check-upgrade.py --apply --url https://gitlab.example.com/team/CataForge.git
  python .claude/scripts/check-upgrade.py --apply --branch release/v1

返回: exit 0=成功/有新版本, exit 1=失败, exit 2=已是最新
"""

import argparse
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

# Ensure UTF-8 output on Windows
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def parse_semver(ver_str: str) -> tuple:
    """解析 semver 字符串为 (major, minor, patch) 元组"""
    ver_str = ver_str.strip()
    match = re.match(r"^v?(\d+)\.(\d+)\.(\d+)", ver_str)
    if not match:
        return (0, 0, 0)
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def read_local_version() -> str:
    """读取本地 pyproject.toml 中的 [project].version"""
    ver_file = "pyproject.toml"
    if not os.path.exists(ver_file):
        return "0.0.0"
    with open(ver_file, "r", encoding="utf-8") as f:
        content = f.read()
    match = re.search(r'^version\s*=\s*"([^"]+)"', content, re.MULTILINE)
    return match.group(1) if match else "0.0.0"


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


# ============================================================================
# GitHub API 模式
# ============================================================================


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
        with urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            import base64

            content = base64.b64decode(data["content"]).decode("utf-8").strip()
            match = re.search(r'^version\s*=\s*"([^"]+)"', content, re.MULTILINE)
            return match.group(1) if match else ""
    except HTTPError as e:
        if e.code == 404:
            print(f"错误: GitHub 仓库 {repo} 或分支 {branch} 不存在", file=sys.stderr)
        elif e.code == 401 or e.code == 403:
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


def validate_branch_name(branch: str) -> bool:
    """校验分支名，防止注入异常字符"""
    return bool(re.match(r"^[a-zA-Z0-9._/-]+$", branch))


def get_github_clone_url(repo: str) -> str:
    """构造 GitHub 仓库的 clone URL（不嵌入 Token）"""
    return f"https://github.com/{repo}.git"


def build_clone_env(token: str) -> dict:
    """构建 git clone 环境变量，通过 GIT_ASKPASS 安全传递 Token（不嵌入 URL）"""
    env = os.environ.copy()
    if token:
        # 创建临时 askpass 脚本，git 通过此脚本获取密码
        # Token 不出现在 URL、进程参数或 .git/config 中
        askpass_script = os.path.join(
            tempfile.gettempdir(), f"cataforge_askpass_{os.getpid()}.py"
        )
        with open(askpass_script, "w", encoding="utf-8") as f:
            f.write(f'#!/usr/bin/env python3\nimport sys\nprint("{token}")\n')
        try:
            os.chmod(askpass_script, 0o700)
        except OSError:
            pass  # Windows 不支持 chmod，但脚本仍可执行
        env["GIT_ASKPASS"] = askpass_script
        env["GIT_TERMINAL_PROMPT"] = "0"
        env["_CATAFORGE_ASKPASS_SCRIPT"] = askpass_script  # 用于清理
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


# ============================================================================
# 通用 Git 模式
# ============================================================================


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
            # Match refs/tags/v1.2.3 or refs/tags/1.2.3 (exclude ^{})
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
        if os.path.exists(tmpdir):
            print(f"警告: 无法清理临时目录 {tmpdir}，请手动删除", file=sys.stderr)


# ============================================================================
# 克隆 + 升级
# ============================================================================


def clone_and_upgrade(
    clone_url: str, branch: str, token: str = "", dry_run: bool = False
) -> int:
    """克隆远程仓库到临时目录，调用 upgrade.py 执行升级"""
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

        # 调用 upgrade.py
        upgrade_script = os.path.join(".claude", "scripts", "upgrade.py")
        if not os.path.exists(upgrade_script):
            print(f"错误: 升级脚本不存在: {upgrade_script}", file=sys.stderr)
            return 1

        cmd = [sys.executable, upgrade_script, tmpdir]
        if dry_run:
            cmd.append("--dry-run")

        result = subprocess.run(cmd, timeout=300)
        return result.returncode

    except subprocess.TimeoutExpired:
        print("错误: git clone 或升级脚本超时", file=sys.stderr)
        return 1
    except FileNotFoundError:
        print("错误: git 命令不可用", file=sys.stderr)
        return 1
    finally:
        cleanup_askpass(env)
        print(f"\n清理临时目录: {tmpdir}")
        shutil.rmtree(tmpdir, ignore_errors=True)
        if os.path.exists(tmpdir):
            print(f"警告: 无法清理临时目录 {tmpdir}，请手动删除", file=sys.stderr)


# ============================================================================
# 主流程
# ============================================================================


def main():
    parser = argparse.ArgumentParser(
        description="CataForge remote upgrade detection and pull tool",
        epilog="Example: python .claude/scripts/check-upgrade.py --check --repo owner/CataForge",
    )

    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument("--check", action="store_true", help="仅检测是否有新版本")
    mode_group.add_argument(
        "--dry-run", action="store_true", help="检测 + 预览变更（不执行升级）"
    )
    mode_group.add_argument("--apply", action="store_true", help="检测 + 执行升级")

    source_group = parser.add_mutually_exclusive_group()
    source_group.add_argument(
        "--repo", type=str, default=None, help="GitHub 仓库 (owner/repo)，覆盖配置文件"
    )
    source_group.add_argument(
        "--url", type=str, default=None, help="Git 仓库 URL，覆盖配置文件"
    )

    parser.add_argument(
        "--branch", type=str, default=None, help="分支名，覆盖配置文件 (默认: main)"
    )
    parser.add_argument(
        "--token-env",
        type=str,
        default=None,
        help="存放 token 的环境变量名，覆盖配置文件",
    )

    args = parser.parse_args()

    # 加载配置
    config = load_upgrade_source()

    # 确定远程源参数（命令行优先于配置文件）
    source_type = None
    repo = None
    url = None
    branch = args.branch or config.get("branch", "main")
    token_env = args.token_env or config.get("token_env", "")

    if args.repo:
        source_type = "github"
        repo = args.repo
    elif args.url:
        source_type = "git"
        url = args.url
    elif config.get("type") == "github" and config.get("repo"):
        source_type = "github"
        repo = config["repo"]
    elif config.get("type") == "git" and config.get("url"):
        source_type = "git"
        url = config["url"]
    else:
        print(
            "错误: 未配置远程源。请提供 --repo 或 --url 参数，或配置 .claude/upgrade-source.json",
            file=sys.stderr,
        )
        sys.exit(1)

    # 读取本地版本
    local_ver = read_local_version()
    print(f"当前版本: {local_ver}")

    # 检测远程版本
    remote_ver = ""
    clone_url = ""

    # 校验分支名
    if not validate_branch_name(branch):
        print(
            f"错误: 无效的分支名 '{branch}'，仅允许字母、数字、点、下划线、斜杠、连字符",
            file=sys.stderr,
        )
        sys.exit(1)

    token = ""
    if source_type == "github":
        token = get_github_token(token_env)
        print(f"远程源: GitHub {repo} (分支: {branch})")
        remote_ver = check_version_github(repo, branch, token)
        clone_url = get_github_clone_url(repo)
    elif source_type == "git":
        print(f"远程源: Git {url} (分支: {branch})")
        # 先尝试 tags 检测
        remote_ver = check_version_git_tags(url)
        if not remote_ver:
            # fallback 到浅克隆读取版本文件
            print("未找到 semver 标签，尝试读取分支上的版本文件...")
            remote_ver = check_version_git_clone(url, branch, token)
        clone_url = url

    if not remote_ver:
        print("错误: 无法获取远程版本", file=sys.stderr)
        sys.exit(1)

    print(f"远程版本: {remote_ver}")

    # 版本比较
    if parse_semver(remote_ver) <= parse_semver(local_ver):
        print(f"\n当前已是最新版本 ({local_ver})，无需升级。")
        sys.exit(2)

    print(f"\n发现新版本: {local_ver} → {remote_ver}")

    # 仅检测模式
    if args.check:
        print("\n可运行以下命令升级:")
        print("  python .claude/scripts/check-upgrade.py --dry-run  # 预览变更")
        print("  python .claude/scripts/check-upgrade.py --apply    # 执行升级")
        sys.exit(0)

    # 预览或执行升级
    exit_code = clone_and_upgrade(clone_url, branch, token=token, dry_run=args.dry_run)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
