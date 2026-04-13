#!/usr/bin/env python3
"""Docker utilities module.

Unified Docker Desktop detection, lifecycle management, and proxy configuration.
Extracted from _common.py to enforce single-responsibility and eliminate duplication
with setup_penpot.py.

Public API:
- Detection:  docker_status(), is_docker_desktop_installed(),
              is_docker_desktop_process_running(), is_docker_daemon_ready()
- Lifecycle:  find_docker_desktop_exe(), start_docker_desktop(),
              restart_docker_desktop(), ensure_docker_running(),
              install_docker_desktop_windows()
- Proxy:      configure_docker_cli_proxy(), configure_docker_desktop_proxy(),
              cleanup_dead_registry_mirrors(), ensure_docker_proxy()
- Constants:  DOCKER_STARTUP_TIMEOUT, DOCKER_STOP_TIMEOUT
"""

import json
import os
import socket
import subprocess
import sys
import time
from typing import Optional, Tuple
from urllib.parse import urlparse

from _common import (
    has_command,
    info,
    ok,
    warn,
    fail,
    resolve_proxy_url,
    run_cmd,
)

# ============================================================================
# Constants (replacing magic numbers)
# ============================================================================

DOCKER_STARTUP_TIMEOUT = 90  # seconds to wait for Docker daemon to become ready
DOCKER_STOP_TIMEOUT = 15  # seconds to wait for Docker daemon to fully stop
DOCKER_PULL_TIMEOUT = 300  # seconds per image pull attempt
DOCKER_RESTART_SETTLE = 2  # seconds to sleep after killing processes before relaunch


# ============================================================================
# Detection — layered: installed → process running → daemon ready
# ============================================================================


def find_docker_desktop_exe() -> str:
    """Locate Docker Desktop executable. Returns path or empty string.

    Searches platform-specific candidate paths. Unified implementation
    replacing duplicates in _common.py and setup_penpot.py.
    """
    if sys.platform == "win32":
        candidates = [
            os.path.join(
                os.environ.get("ProgramFiles", r"C:\Program Files"),
                "Docker",
                "Docker",
                "Docker Desktop.exe",
            ),
            os.path.join(
                os.environ.get("LOCALAPPDATA", ""),
                "Docker",
                "Docker Desktop.exe",
            ),
            # Hardcoded fallback for non-standard ProgramFiles env
            r"C:\Program Files\Docker\Docker\Docker Desktop.exe",
        ]
    elif sys.platform == "darwin":
        candidates = ["/Applications/Docker.app/Contents/MacOS/Docker Desktop"]
    else:
        candidates = []

    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return ""


def is_docker_desktop_installed() -> bool:
    """Check if Docker Desktop is installed (does NOT require daemon running)."""
    return bool(find_docker_desktop_exe())


def is_docker_desktop_process_running() -> bool:
    """Check if Docker Desktop backend process is alive (does NOT require daemon ready).

    On Windows, checks for com.docker.backend.exe.
    On macOS, checks for 'Docker Desktop' process.
    """
    try:
        if sys.platform == "win32":
            result = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq com.docker.backend.exe", "/NH"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return "com.docker.backend" in result.stdout
        elif sys.platform == "darwin":
            result = subprocess.run(
                ["pgrep", "-f", "Docker Desktop"],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        else:
            # Linux: Docker Desktop uses docker-desktop process
            result = subprocess.run(
                ["pgrep", "-f", "docker-desktop"],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


def is_docker_daemon_ready() -> bool:
    """Check if Docker daemon is responding to commands."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


def is_docker_desktop_engine() -> bool:
    """Check if the running Docker daemon is Docker Desktop (not standalone/colima/etc).

    Requires daemon to be running. Falls back to process detection if daemon
    is not yet ready.
    """
    if is_docker_daemon_ready():
        try:
            result = subprocess.run(
                ["docker", "info", "--format", "{{.OperatingSystem}}"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if "Docker Desktop" in result.stdout:
                return True
        except (subprocess.TimeoutExpired, OSError):
            pass

    # Fallback: process-based detection (works even when daemon is starting up)
    return is_docker_desktop_process_running()


def docker_status() -> str:
    """Return Docker status as a three-level enum.

    Returns:
        'not_installed'          — Docker command not found and no Desktop exe
        'installed_not_running'  — Docker installed but daemon not responding
        'running'                — Docker daemon is ready
    """
    if is_docker_daemon_ready():
        return "running"
    if has_command("docker") or is_docker_desktop_installed():
        return "installed_not_running"
    return "not_installed"


# ============================================================================
# Lifecycle management
# ============================================================================


def _wait_docker_ready(timeout: int = DOCKER_STARTUP_TIMEOUT) -> bool:
    """Poll until Docker daemon is ready or timeout.

    Args:
        timeout: Maximum seconds to wait.

    Returns:
        True if daemon became ready within timeout.
    """
    for i in range(timeout):
        if is_docker_daemon_ready():
            ok(f"Docker daemon 已就绪 (等待了 {i + 1}s)")
            return True
        time.sleep(1)
        if (i + 1) % 15 == 0:
            info(f"  已等待 {i + 1}s...")
    return False


def _wait_docker_stopped(timeout: int = DOCKER_STOP_TIMEOUT) -> bool:
    """Poll until Docker daemon stops responding.

    Args:
        timeout: Maximum seconds to wait.

    Returns:
        True if daemon stopped within timeout.
    """
    for _ in range(timeout):
        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                timeout=3,
            )
            if result.returncode != 0:
                return True
        except (subprocess.TimeoutExpired, OSError):
            return True
        time.sleep(1)
    return False


def _kill_docker_desktop_windows():
    """Kill all Docker Desktop processes on Windows."""
    for proc_name in [
        "Docker Desktop.exe",
        "com.docker.backend.exe",
        "com.docker.build.exe",
        "com.docker.proxy.exe",
    ]:
        subprocess.run(
            ["taskkill", "/IM", proc_name, "/F"],
            capture_output=True,
            timeout=15,
        )


def _launch_docker_desktop_exe(exe_path: str):
    """Launch Docker Desktop executable in detached mode."""
    if sys.platform == "win32":
        subprocess.Popen(
            [exe_path],
            creationflags=(
                subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
            ),
            close_fds=True,
        )
    elif sys.platform == "darwin":
        subprocess.run(["open", "-a", "Docker"], capture_output=True, timeout=10)
    else:
        subprocess.run(
            ["systemctl", "--user", "restart", "docker-desktop"],
            capture_output=True,
            timeout=30,
        )


def start_docker_desktop(timeout: int = DOCKER_STARTUP_TIMEOUT) -> bool:
    """Start Docker Desktop and wait for daemon to become ready.

    Args:
        timeout: Maximum seconds to wait after launching.

    Returns:
        True if Docker daemon is ready.
    """
    exe = find_docker_desktop_exe()
    if not exe and sys.platform not in ("darwin",):
        fail("无法定位 Docker Desktop 可执行文件")
        return False

    info("启动 Docker Desktop...")
    _launch_docker_desktop_exe(exe)

    info(f"等待 Docker daemon 就绪 (最多 {timeout}s)...")
    if _wait_docker_ready(timeout):
        return True

    warn("Docker Desktop 启动超时")
    return False


def restart_docker_desktop(timeout: int = DOCKER_STARTUP_TIMEOUT) -> bool:
    """Restart Docker Desktop to apply configuration changes.

    Kills existing processes, waits for full stop, then relaunches.

    Returns:
        True if Docker became available after restart.
    """
    info("重启 Docker Desktop 以应用配置变更...")

    if sys.platform == "win32":
        _kill_docker_desktop_windows()

        info("  等待 Docker 停止...")
        if not _wait_docker_stopped():
            warn("Docker 进程未完全停止，继续尝试重启...")

        time.sleep(DOCKER_RESTART_SETTLE)

        exe = find_docker_desktop_exe()
        if exe:
            _launch_docker_desktop_exe(exe)
        else:
            warn("无法定位 Docker Desktop.exe，请手动重启 Docker Desktop")
            return False

    elif sys.platform == "darwin":
        subprocess.run(
            ["osascript", "-e", 'quit app "Docker"'],
            capture_output=True,
            timeout=10,
        )
        time.sleep(3)
        subprocess.run(["open", "-a", "Docker"], capture_output=True, timeout=10)

    else:
        subprocess.run(
            ["systemctl", "--user", "restart", "docker-desktop"],
            capture_output=True,
            timeout=30,
        )

    info(f"  等待 Docker 就绪 (最多 {timeout}s)...")
    if _wait_docker_ready(timeout):
        return True

    warn("Docker Desktop 重启超时，请手动检查")
    return False


def install_docker_desktop_windows() -> bool:
    """Install Docker Desktop via winget on Windows.

    Returns:
        True if installation succeeded.
    """
    if sys.platform != "win32":
        fail("仅支持 Windows 平台")
        return False

    if not has_command("winget"):
        fail("winget 未找到，无法自动安装 Docker Desktop")
        info("请手动下载安装: https://docs.docker.com/desktop/install/windows-install/")
        return False

    info("通过 winget 安装 Docker Desktop (需要管理员权限)...")
    result = subprocess.run(
        [
            "winget",
            "install",
            "--id",
            "Docker.DockerDesktop",
            "--accept-package-agreements",
            "--accept-source-agreements",
        ],
        timeout=600,
    )
    if result.returncode != 0:
        fail(f"winget 安装失败 (exit={result.returncode})")
        info("请手动下载安装: https://docs.docker.com/desktop/install/windows-install/")
        return False

    ok("Docker Desktop 安装完成")
    return True


def ensure_docker_running() -> bool:
    """Ensure Docker daemon is running. Auto-starts Docker Desktop if needed.

    Does NOT auto-install. Use install_docker_desktop_windows() separately
    if installation is desired (requires user confirmation).

    Returns:
        True if Docker daemon is ready.
    """
    if is_docker_daemon_ready():
        ok("Docker daemon 运行中")
        return True

    platform = sys.platform

    if platform == "win32":
        if find_docker_desktop_exe():
            warn("Docker daemon 未运行，尝试自动启动 Docker Desktop...")
            return start_docker_desktop()
        fail("Docker Desktop 未安装")
        return False

    elif platform == "darwin":
        warn("Docker daemon 未运行，尝试启动 Docker Desktop...")
        return start_docker_desktop()

    else:
        # Linux: try systemctl / service
        warn("Docker daemon 未运行，尝试通过 systemctl 启动...")
        started = False
        if has_command("systemctl"):
            r = subprocess.run(
                ["sudo", "systemctl", "start", "docker"],
                capture_output=True,
                timeout=30,
            )
            started = r.returncode == 0
        if not started and has_command("service"):
            r = subprocess.run(
                ["sudo", "service", "docker", "start"],
                capture_output=True,
                timeout=30,
            )
            started = r.returncode == 0
        if not started:
            fail("无法自动启动 Docker daemon。请运行: sudo systemctl start docker")
            return False

        info("等待 Docker daemon 就绪...")
        if _wait_docker_ready(15):
            return True
        fail("Docker daemon 启动后未就绪，请检查: sudo systemctl status docker")
        return False


# ============================================================================
# Proxy configuration
# ============================================================================


def _get_docker_desktop_settings_path() -> str:
    """Return platform-specific path to Docker Desktop settings-store.json."""
    if sys.platform == "win32":
        return os.path.join(
            os.environ.get("APPDATA", ""),
            "Docker",
            "settings-store.json",
        )
    elif sys.platform == "darwin":
        return os.path.join(
            os.path.expanduser("~"),
            "Library",
            "Group Containers",
            "group.com.docker",
            "settings-store.json",
        )
    return ""


def configure_docker_cli_proxy(http_proxy: str, https_proxy: str) -> bool:
    """Configure Docker CLI client proxy in ~/.docker/config.json.

    Args:
        http_proxy: HTTP proxy URL.
        https_proxy: HTTPS proxy URL.

    Returns:
        True if configuration was changed, False if already up-to-date.
    """
    docker_config_path = os.path.join(
        os.path.expanduser("~"),
        ".docker",
        "config.json",
    )
    docker_config: dict = {}
    existing_proxies: dict = {}

    if os.path.isfile(docker_config_path):
        try:
            with open(docker_config_path, "r", encoding="utf-8") as f:
                docker_config = json.load(f)
            existing_proxies = docker_config.get("proxies", {}).get("default", {})
        except (json.JSONDecodeError, OSError):
            docker_config = {}

    # Already configured and matching
    if (
        existing_proxies.get("httpProxy", "") == http_proxy
        and existing_proxies.get("httpsProxy", "") == https_proxy
    ):
        ok(f"Docker CLI 代理已配置: {https_proxy or http_proxy}")
        return False

    proxies_config: dict = {}
    if http_proxy:
        proxies_config["httpProxy"] = http_proxy
    if https_proxy:
        proxies_config["httpsProxy"] = https_proxy
    proxies_config["noProxy"] = "localhost,127.0.0.1"

    docker_config.setdefault("proxies", {})["default"] = proxies_config
    os.makedirs(os.path.dirname(docker_config_path), exist_ok=True)
    try:
        with open(docker_config_path, "w", encoding="utf-8") as f:
            json.dump(docker_config, f, indent=2, ensure_ascii=False)
            f.write("\n")
        ok(f"Docker CLI 代理已配置: {https_proxy or http_proxy}")
        return True
    except OSError as e:
        warn(f"写入 Docker 配置失败: {e}")
        return False


def configure_docker_desktop_proxy(http_proxy: str, https_proxy: str) -> bool:
    """Configure Docker Desktop manual proxy via settings-store.json.

    Docker Desktop uses its own internal proxy forwarder. When set to
    'automatic' mode, it may fail to detect system proxy. This switches
    to 'manual' mode with the given proxy URLs.

    Returns:
        True if settings were changed (Docker Desktop restart needed).
    """
    settings_path = _get_docker_desktop_settings_path()
    if not settings_path or not os.path.isfile(settings_path):
        return False

    try:
        with open(settings_path, "r", encoding="utf-8") as f:
            settings = json.load(f)
    except (json.JSONDecodeError, OSError):
        return False

    # proxyHttpMode: 0=system/auto, 1=manual, 2=none
    current_mode = settings.get("proxyHttpMode", 0)
    current_http = settings.get("overrideProxyHttp", "")
    current_https = settings.get("overrideProxyHttps", "")

    if (
        current_mode == 1
        and current_http == http_proxy
        and current_https == https_proxy
    ):
        ok(f"Docker Desktop 代理已配置: {https_proxy or http_proxy}")
        return False

    settings["proxyHttpMode"] = 1
    settings["overrideProxyHttp"] = http_proxy
    settings["overrideProxyHttps"] = https_proxy
    settings["overrideProxyExclude"] = "localhost,127.0.0.1"

    try:
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
            f.write("\n")
        ok(f"Docker Desktop 代理已配置: {https_proxy or http_proxy}")
        return True
    except OSError as e:
        warn(f"写入 Docker Desktop 设置失败: {e}")
        return False


def cleanup_dead_registry_mirrors() -> bool:
    """Remove unreachable registry mirrors from daemon.json.

    Many Docker mirror registries have been shut down. Dead mirrors cause
    Docker to waste time on connection attempts before falling back.

    Returns:
        True if daemon.json was modified (Docker restart needed).
    """
    daemon_json_path = os.path.join(
        os.path.expanduser("~"),
        ".docker",
        "daemon.json",
    )
    if not os.path.isfile(daemon_json_path):
        return False

    try:
        with open(daemon_json_path, "r", encoding="utf-8") as f:
            daemon_config = json.load(f)
    except (json.JSONDecodeError, OSError):
        return False

    mirrors = daemon_config.get("registry-mirrors", [])
    if not mirrors:
        return False

    alive = []
    for mirror_url in mirrors:
        parsed = urlparse(mirror_url)
        host = parsed.hostname or ""
        port = parsed.port or 443
        if not host:
            continue
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(2)
            try:
                s.connect((host, port))
                alive.append(mirror_url)
                info(f"  镜像源可用: {mirror_url}")
            except (ConnectionRefusedError, TimeoutError, OSError):
                warn(f"  镜像源不可达，已移除: {mirror_url}")

    if len(alive) == len(mirrors):
        return False

    if alive:
        daemon_config["registry-mirrors"] = alive
    else:
        del daemon_config["registry-mirrors"]

    try:
        with open(daemon_json_path, "w", encoding="utf-8") as f:
            json.dump(daemon_config, f, indent=2, ensure_ascii=False)
            f.write("\n")
        ok("daemon.json 已更新 (移除不可达镜像源)")
        return True
    except OSError as e:
        warn(f"写入 daemon.json 失败: {e}")
        return False


def ensure_docker_proxy(proxy_url: str = "") -> bool:
    """Configure Docker daemon proxy (CLI + Desktop + mirror cleanup).

    Handles both standalone Docker and Docker Desktop. Restarts Docker
    Desktop automatically when settings change.

    Args:
        proxy_url: Proxy URL. If empty, auto-resolved from env/.env.

    Returns:
        True if Docker Desktop was restarted (caller should wait before
        performing Docker operations).
    """
    http_proxy = os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy") or ""
    https_proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or ""

    if proxy_url:
        http_proxy = http_proxy or proxy_url
        https_proxy = https_proxy or proxy_url

    if not http_proxy and not https_proxy:
        resolved = resolve_proxy_url()
        if resolved:
            http_proxy = resolved
            https_proxy = resolved
        else:
            return False

    needs_restart = False

    # 1. CLI client proxy (~/.docker/config.json)
    configure_docker_cli_proxy(http_proxy, https_proxy)

    # 2. Docker Desktop specific
    if is_docker_desktop_engine():
        if configure_docker_desktop_proxy(http_proxy, https_proxy):
            needs_restart = True

        if cleanup_dead_registry_mirrors():
            needs_restart = True

        # 3. Restart if config changed
        if needs_restart:
            restart_docker_desktop()

    return needs_restart
