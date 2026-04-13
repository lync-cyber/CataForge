#!/usr/bin/env python3
"""_upgrade_remote.py -- Remote upgrade logic extracted from upgrade.py

This module contains all remote-detection and remote-upgrade functions
(GitHub API, Git tags, shallow clone, self-reexec, clone-and-upgrade).
It corresponds to "Module B" (remote detection) and the resolve/detect
helpers from the original monolithic upgrade.py.
"""

import base64
import hashlib
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

# ---------------------------------------------------------------------------
# Internal framework imports
# ---------------------------------------------------------------------------
_FRAMEWORK_DIR = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS_ROOT = os.path.dirname(_FRAMEWORK_DIR)
_LIB = os.path.join(_SCRIPTS_ROOT, "lib")
for _p in (_LIB, _FRAMEWORK_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from _common import (
    FRAMEWORK_CONFIG_FILE,
    check_ssh_available,
    ensure_utf8_stdio,
    get_github_token,
    load_dotenv,
)
from _config import load_framework_config
from _version import VERSION_FILE, parse_semver, read_version, validate_branch_name

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Self-upgrade environment variables (see upgrade.py self-upgrade mechanism)
SELF_UPGRADE_MARKER = "CATAFORGE_SELF_UPGRADED"
SELF_UPGRADE_SRC_ENV = "CATAFORGE_SELF_UPGRADE_SRC"


# ============================================================================
# Remote detection helpers
# ============================================================================


def load_upgrade_source() -> dict:
    """从 framework.json 读取升级源配置（兼容层）

    返回与旧 upgrade-source.json 相同的扁平结构:
    {type, repo, url, branch, token_env, last_commit, last_version, last_upgrade_date}
    """
    config = load_framework_config()
    upgrade = config.get("upgrade", {})
    source = upgrade.get("source", {})
    state = upgrade.get("state", {})
    return {**source, **state}


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


def get_github_clone_url(repo: str, prefer_ssh: bool = True) -> str:
    """构造 GitHub 仓库的 clone URL，优先使用 SSH 协议"""
    if prefer_ssh:
        return f"git@github.com:{repo}.git"
    return f"https://github.com/{repo}.git"


def build_clone_env(token: str, clone_url: str = "") -> dict:
    """构建 git clone 环境变量，通过 GIT_ASKPASS 安全传递 Token

    若 clone_url 是 SSH 协议，跳过 Token/ASKPASS 设置（SSH 使用密钥认证）。
    """
    env = os.environ.copy()
    # SSH URL 无需 Token 认证
    if clone_url.startswith("git@") or clone_url.startswith("ssh://"):
        env["GIT_TERMINAL_PROMPT"] = "0"
        return env
    if token:
        # 通过环境变量传递 token，避免明文写入磁盘
        env["_CATAFORGE_GIT_TOKEN"] = token
        askpass_script = os.path.join(
            tempfile.gettempdir(), f"cataforge_askpass_{os.getpid()}.py"
        )
        with open(askpass_script, "w", encoding="utf-8") as f:
            f.write(
                "#!/usr/bin/env python3\n"
                "import os\n"
                'print(os.environ.get("_CATAFORGE_GIT_TOKEN", ""))\n'
            )
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
    env = build_clone_env(token, clone_url=url)
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
      第一阶段 (旧脚本): 克隆远程 -> 检测新版 upgrade.py -> os.execve 到新脚本 -> 退出
      第二阶段 (新脚本): 读取 CATAFORGE_SELF_UPGRADE_SRC 获知已克隆目录 -> 跳过克隆 -> 直接 local 升级

    递归保护: 通过 SELF_UPGRADE_MARKER 环境变量防止无限 re-exec。
    """
    if os.environ.get(SELF_UPGRADE_MARKER):
        return  # 已是第二阶段，继续正常流程

    candidates = [
        os.path.join(tmpdir, ".claude", "scripts", "framework", "upgrade.py"),
        os.path.join(tmpdir, ".claude", "scripts", "upgrade.py"),
    ]
    new_script = next((p for p in candidates if os.path.isfile(p)), "")
    cur_script = os.path.abspath(sys.argv[0])
    if not new_script:
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

    cleanup_askpass(env)

    if sys.platform == "win32":
        # Windows 上 os.execve 无法正确处理路径中的空格，使用 subprocess 替代
        try:
            rc = subprocess.call(new_argv, env=env)
            sys.exit(rc)
        except OSError as e:
            print(f"[自升级] subprocess 启动失败，回退到当前脚本: {e}", file=sys.stderr)
    else:
        try:
            os.execve(sys.executable, new_argv, env)
        except OSError as e:
            print(f"[自升级] os.execve 失败，回退到当前脚本: {e}", file=sys.stderr)


def clone_and_upgrade(
    clone_url: str, branch: str, token: str = "", dry_run: bool = False
) -> int:
    """克隆远程仓库到临时目录，执行本地升级流程。

    自升级支持: 若第一阶段检测到 upgrade.py 有更新，os.execve 到新脚本继续。
    第二阶段通过 CATAFORGE_SELF_UPGRADE_SRC 环境变量复用已克隆目录。
    """
    from _upgrade_local import run_local_upgrade

    if not validate_branch_name(branch):
        print(f"错误: 无效的分支名: {branch}", file=sys.stderr)
        return 1

    tmpdir = tempfile.mkdtemp(prefix="cataforge-upgrade-")
    env = build_clone_env(token, clone_url=clone_url)
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
# High-level resolve / detect helpers
# ============================================================================


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
            "错误: 未配置远程源。请提供 --repo 或 --url 参数，或配置 .claude/framework.json",
            file=sys.stderr,
        )
        sys.exit(1)


def detect_remote_state(source_type, repo, url, branch, token_env):
    """检测远程状态，返回 (remote_ver, remote_commit, clone_url, token)

    对 GitHub 类型的远程源，优先尝试 SSH 协议。SSH 可用时 clone 使用
    git@github.com:owner/repo.git，版本检测仍走 GitHub API（更轻量）。
    SSH 不可用时回退到 HTTPS + Token。
    """
    token = get_github_token(token_env) if token_env else ""

    if source_type == "github":
        print(f"远程源: GitHub {repo} (分支: {branch})")

        # clone URL: 优先 SSH，不可用时回退 HTTPS
        ssh_ok = check_ssh_available()
        if ssh_ok:
            clone_url = get_github_clone_url(repo, prefer_ssh=True)
            print(f"传输协议: SSH (git@github.com:{repo}.git)")
        else:
            clone_url = get_github_clone_url(repo, prefer_ssh=False)
            proto_hint = "HTTPS + Token" if token else "HTTPS (无认证，仅限公开仓库)"
            print(f"传输协议: {proto_hint}")

        # 版本检测: 优先 GitHub API（轻量），失败时回退到 git 命令
        remote_ver = check_version_github(repo, branch, token)
        remote_commit = get_remote_commit_github(repo, branch, token)

        # GitHub API 失败 (rate limit / auth) 时，回退到 git 命令
        if not remote_commit:
            print("GitHub API 不可用，回退到 git ls-remote...")
            remote_commit = get_remote_commit_git(clone_url, branch)
        if not remote_ver:
            # 跳过 git tags — 标签常滞后于 pyproject.toml，直接浅克隆读取
            print("尝试通过浅克隆获取版本...")
            remote_ver = check_version_git_clone(clone_url, branch, token)
    else:
        print(f"远程源: Git {url} (分支: {branch})")
        remote_ver = check_version_git_tags(url)
        if not remote_ver:
            print("未找到 semver 标签，尝试读取分支上的版本文件...")
            remote_ver = check_version_git_clone(url, branch, token)
        remote_commit = get_remote_commit_git(url, branch)
        clone_url = url

    return remote_ver, remote_commit, clone_url, token
