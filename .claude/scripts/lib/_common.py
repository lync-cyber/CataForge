#!/usr/bin/env python3
"""CataForge shared utilities module.

Core infrastructure used across all scripts and hooks:
- Project root detection
- Windows UTF-8 stdout/stderr fix
- .env file parsing
- Platform detection
- Terminal colored output
- Command availability detection
- Port detection (cross-platform)
- GitHub / SSH tools

Configuration, version, and YAML parsing have been extracted to:
- _config.py  (framework.json, template registry, JSON utils)
- _version.py (semver parsing, phase management, validation)
- _yaml_parser.py (unified simple YAML parser)

For backward compatibility, all public names are re-exported here.
"""

import io
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import warnings
from typing import Dict, Optional, Tuple
from urllib.parse import urlparse

# ============================================================================
# Re-exports from extracted modules (backward compatibility)
# ============================================================================

from _config import (  # noqa: F401
    REGISTRY_FILE,
    build_doc_type_map,
    build_template_path_map,
    get_constant,
    load_framework_config,
    load_framework_constants,
    load_json_lenient,
    load_template_registry,
)
from _version import (  # noqa: F401
    PHASE_ORDER,
    VERSION_FILE,
    parse_semver,
    phase_index,
    read_version,
    validate_branch_name,
)

# Backward-compatible alias: old code references _common.FRAMEWORK_CONFIG_FILE
FRAMEWORK_CONFIG_FILE = os.path.join(".claude", "framework.json")

# ============================================================================
# Exit code constants
# ============================================================================

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_SKIP = 2


# ============================================================================
# Project root detection
# ============================================================================


def find_project_root(start: Optional[str] = None) -> str:
    """Locate the project root containing a .claude/ directory.

    Args:
        start: Starting search directory. Default: walk parents from this file
               until a directory containing `.claude/` is found (works for
               scripts/lib/, scripts/framework/, scripts/docs/).

    Returns:
        Absolute path to the project root.
    """
    if start is not None:
        d = os.path.abspath(start)
        for _ in range(10):
            if os.path.isdir(os.path.join(d, ".claude")) or os.path.isfile(
                os.path.join(d, "CLAUDE.md")
            ):
                return d
            parent = os.path.dirname(d)
            if parent == d:
                break
            d = parent
        fallback = os.path.abspath(start)
        warnings.warn(
            f"find_project_root: no .claude/ found, falling back to {fallback}",
            stacklevel=2,
        )
        return fallback

    d = os.path.dirname(os.path.abspath(__file__))
    while True:
        parent = os.path.dirname(d)
        if parent == d:
            warnings.warn(
                "find_project_root: no .claude/ in ancestors from _common.py location",
                stacklevel=2,
            )
            return d
        if os.path.isdir(os.path.join(d, ".claude")):
            return d
        d = parent


# ============================================================================
# UTF-8 stdio fix (Windows)
# ============================================================================


def ensure_utf8_stdio():
    """Ensure stdout/stderr use UTF-8 encoding.

    Windows console may default to cp936/cp1252, causing UnicodeEncodeError
    for non-ASCII output.
    """
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace"
        )
    if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
        sys.stderr = io.TextIOWrapper(
            sys.stderr.buffer, encoding="utf-8", errors="replace"
        )


# ============================================================================
# .env file parsing
# ============================================================================


def load_dotenv(
    env_path: Optional[str] = None, set_env: bool = False
) -> Dict[str, str]:
    """Parse a .env file and return key-value pairs.

    Supports: KEY=value, KEY="quoted", KEY='single', # comments, blank lines.

    Args:
        env_path: Path to .env file. Defaults to project root .env.
        set_env: If True, also set os.environ (only for unset variables).

    Returns:
        Parsed key-value dict.
    """
    if env_path is None:
        env_path = os.path.join(find_project_root(), ".env")

    result: Dict[str, str] = {}
    if not os.path.isfile(env_path):
        return result

    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", line)
                if not match:
                    continue
                key = match.group(1)
                val = match.group(2).strip()
                if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
                    val = val[1:-1]
                else:
                    if " #" in val:
                        val = val[: val.index(" #")].rstrip()
                result[key] = val
                if set_env and key not in os.environ:
                    os.environ[key] = val
    except OSError:
        pass

    return result


# ============================================================================
# Platform detection
# ============================================================================


def detect_platform() -> str:
    """Detect the running platform.

    Returns:
        "windows" | "macos" | "linux" | "unknown"
    """
    if sys.platform == "win32" or sys.platform == "cygwin":
        return "windows"
    elif sys.platform == "darwin":
        return "macos"
    elif sys.platform.startswith("linux"):
        return "linux"
    return "unknown"


# ============================================================================
# Terminal colored output
# ============================================================================


def _supports_color() -> bool:
    """Check if the terminal supports ANSI colors."""
    if os.environ.get("NO_COLOR"):
        return False
    return bool(
        (hasattr(sys.stdout, "isatty") and sys.stdout.isatty())
        or os.environ.get("TERM")
        or os.environ.get("WT_SESSION")
    )


_COLOR_ENABLED = _supports_color()

GREEN = "\033[0;32m" if _COLOR_ENABLED else ""
RED = "\033[0;31m" if _COLOR_ENABLED else ""
YELLOW = "\033[1;33m" if _COLOR_ENABLED else ""
BLUE = "\033[0;34m" if _COLOR_ENABLED else ""
CYAN = "\033[0;36m" if _COLOR_ENABLED else ""
BOLD = "\033[1m" if _COLOR_ENABLED else ""
DIM = "\033[2m" if _COLOR_ENABLED else ""
NC = "\033[0m" if _COLOR_ENABLED else ""

TICK = f"{GREEN}OK{NC}"
CROSS = f"{RED}FAIL{NC}"
WARN_LABEL = f"{YELLOW}WARN{NC}"
INFO_LABEL = f"{BLUE}INFO{NC}"
SKIP_LABEL = f"{DIM}SKIP{NC}"


def ok(msg: str):
    """Print a success message."""
    print(f"  [{TICK}] {msg}")


def fail(msg: str):
    """Print a failure message."""
    print(f"  [{CROSS}] {msg}")


def warn(msg: str):
    """Print a warning message."""
    print(f"  [{WARN_LABEL}] {msg}")


def info(msg: str):
    """Print an info message."""
    print(f"  [{INFO_LABEL}] {msg}")


def skip(msg: str):
    """Print a skip message."""
    print(f"  [{SKIP_LABEL}] {msg}")


def section(title: str):
    """Print a section header."""
    print(f"\n{BOLD}--- {title} ---{NC}")


# ============================================================================
# Command detection
# ============================================================================


def has_command(name: str) -> bool:
    """Check if a command is available on PATH."""
    return shutil.which(name) is not None


def get_command_version(cmd: list) -> str:
    """Get the version output string from a command."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return result.stdout.strip() or result.stderr.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return ""


def run_cmd(
    cmd: list,
    *,
    timeout: int = 120,
    capture: bool = True,
    check: bool = False,
    cwd: Optional[str] = None,
) -> subprocess.CompletedProcess:
    """Unified command execution wrapper.

    Args:
        cmd: Command and arguments list.
        timeout: Timeout in seconds.
        capture: Whether to capture output.
        check: Whether to raise on non-zero exit.
        cwd: Working directory.

    Returns:
        CompletedProcess object.
    """
    return subprocess.run(
        cmd,
        capture_output=capture,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=check,
        cwd=cwd,
    )


# ============================================================================
# Port detection (cross-platform)
# ============================================================================


def is_port_listening(port: int) -> bool:
    """Check if a local port has a listening process. Cross-platform."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        try:
            s.connect(("127.0.0.1", port))
            return True
        except (ConnectionRefusedError, TimeoutError, OSError):
            return False


def find_available_port(preferred: int, name: str = "", max_tries: int = 20) -> int:
    """Find an available port, starting from preferred.

    Args:
        preferred: Preferred port number.
        name: Port purpose description (for output).
        max_tries: Maximum number of ports to try.

    Returns:
        Available port number.
    """
    for offset in range(max_tries):
        port = preferred + offset
        if not is_port_listening(port):
            if offset > 0:
                label = f" ({name})" if name else ""
                warn(f"Port {preferred}{label} is occupied, switching to {port}")
            return port
    return preferred


def check_port_available(port: int, name: str = "") -> bool:
    """Check if a port is available (not occupied).

    Args:
        port: Port number.
        name: Port purpose description (for output).

    Returns:
        True if the port is available.
    """
    if is_port_listening(port):
        label = f" ({name})" if name else ""
        warn(f"Port {port}{label} is occupied")
        return False
    return True


# ============================================================================
# Proxy utilities
# ============================================================================

# Cooldown state for auto-detect
_proxy_last_check: float = 0.0
_proxy_last_state: str = ""
_PROXY_CHECK_INTERVAL = 30  # seconds


def resolve_proxy_url() -> str:
    """Resolve proxy URL from environment variables or .env file.

    Priority:
      1. os.environ HTTP_PROXY / HTTPS_PROXY (case-insensitive)
      2. .env file at project root (parsed but NOT injected into os.environ)

    Returns:
        Proxy URL string, or "" if none found.
    """
    for var in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        val = os.environ.get(var, "")
        if val:
            return val

    # Fallback: read from .env
    dotenv = load_dotenv()
    for var in ("HTTPS_PROXY", "HTTP_PROXY", "https_proxy", "http_proxy"):
        val = dotenv.get(var, "")
        if val:
            return val

    return ""


def parse_proxy_host_port(proxy_url: str = "") -> Tuple[str, int]:
    """Extract (host, port) from a proxy URL.

    Args:
        proxy_url: e.g. "http://proxy-prc.intel.com:912". If empty,
                   calls resolve_proxy_url().

    Returns:
        (host, port) tuple. ("", 0) if parsing fails or no proxy configured.
    """
    if not proxy_url:
        proxy_url = resolve_proxy_url()
    if not proxy_url:
        return ("", 0)

    parsed = urlparse(proxy_url)
    host = parsed.hostname or ""
    port = parsed.port or 0
    return (host, port)


def is_proxy_reachable(host: str = "", port: int = 0, timeout: float = 1.0) -> bool:
    """Check if the proxy host:port is reachable via TCP connect.

    Args:
        host: Proxy hostname. If empty, auto-resolved from env/.env.
        port: Proxy port. If 0, auto-resolved.
        timeout: Connection timeout in seconds.

    Returns:
        True if the proxy port accepts connections.
    """
    if not host or not port:
        host, port = parse_proxy_host_port()
    if not host or not port:
        return False

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        try:
            s.connect((host, port))
            return True
        except (ConnectionRefusedError, TimeoutError, OSError):
            return False


def proxy_on(proxy_url: str = "", quiet: bool = False):
    """Enable proxy: set env vars + git global config.

    Args:
        proxy_url: Proxy URL. If empty, auto-resolved.
        quiet: Suppress output if True.
    """
    if not proxy_url:
        proxy_url = resolve_proxy_url()
    if not proxy_url:
        if not quiet:
            warn("未找到代理配置 (HTTP_PROXY / .env)")
        return

    no_proxy = "localhost,127.0.0.1,::1"
    os.environ["http_proxy"] = proxy_url
    os.environ["https_proxy"] = proxy_url
    os.environ["HTTP_PROXY"] = proxy_url
    os.environ["HTTPS_PROXY"] = proxy_url
    os.environ["no_proxy"] = no_proxy
    os.environ["NO_PROXY"] = no_proxy

    # Configure git global proxy
    if has_command("git"):
        try:
            run_cmd(["git", "config", "--global", "http.proxy", proxy_url], timeout=5)
            run_cmd(["git", "config", "--global", "https.proxy", proxy_url], timeout=5)
        except Exception:
            pass

    if not quiet:
        ok(f"代理已启用: {proxy_url}")


def proxy_off(quiet: bool = False):
    """Disable proxy: unset env vars + git global config.

    Args:
        quiet: Suppress output if True.
    """
    for var in (
        "http_proxy",
        "https_proxy",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "no_proxy",
        "NO_PROXY",
    ):
        os.environ.pop(var, None)

    if has_command("git"):
        try:
            run_cmd(["git", "config", "--global", "--unset", "http.proxy"], timeout=5)
            run_cmd(["git", "config", "--global", "--unset", "https.proxy"], timeout=5)
        except Exception:
            pass

    if not quiet:
        ok("代理已关闭")


def proxy_status() -> str:
    """Return current proxy status string.

    Returns:
        "ON → <url>" or "OFF (direct)".
    """
    url = os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy") or ""
    if url:
        return f"ON → {url}"
    return "OFF (direct)"


def ensure_proxy(quiet: bool = False) -> bool:
    """Auto-detect proxy reachability and enable/disable accordingly.

    Uses cooldown to avoid repeated network probes.

    Args:
        quiet: Suppress output if True.

    Returns:
        True if proxy is now enabled, False otherwise.
    """
    global _proxy_last_check, _proxy_last_state

    now = time.time()
    if (now - _proxy_last_check) < _PROXY_CHECK_INTERVAL and _proxy_last_state:
        return _proxy_last_state == "on"

    _proxy_last_check = now
    host, port = parse_proxy_host_port()
    if not host:
        _proxy_last_state = "off"
        return False

    reachable = is_proxy_reachable(host, port)
    new_state = "on" if reachable else "off"

    if new_state != _proxy_last_state:
        _proxy_last_state = new_state
        if reachable:
            proxy_on(quiet=quiet)
            if not quiet:
                info(f"auto → 代理可达 ({host}:{port})")
        else:
            proxy_off(quiet=quiet)
            if not quiet:
                info(f"auto → 代理不可达 ({host}:{port})")
    else:
        _proxy_last_state = new_state

    return reachable


def ensure_docker_proxy(proxy_url: str = ""):
    """Configure Docker daemon proxy via ~/.docker/config.json.

    Docker daemon does not inherit shell HTTP_PROXY. This writes the
    proxy settings into Docker's config file (cross-platform).

    Args:
        proxy_url: Proxy URL. If empty, auto-resolved from env/.env.
    """
    http_proxy = os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy") or ""
    https_proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or ""

    # If a specific URL is given, use it for both
    if proxy_url:
        http_proxy = http_proxy or proxy_url
        https_proxy = https_proxy or proxy_url

    if not http_proxy and not https_proxy:
        # Try resolving from .env
        resolved = resolve_proxy_url()
        if resolved:
            http_proxy = resolved
            https_proxy = resolved
        else:
            return

    docker_config_path = os.path.join(os.path.expanduser("~"), ".docker", "config.json")
    docker_config: dict = {}
    existing_proxies: dict = {}

    if os.path.isfile(docker_config_path):
        try:
            with open(docker_config_path, "r", encoding="utf-8") as f:
                docker_config = json.load(f)
            existing_proxies = docker_config.get("proxies", {}).get("default", {})
        except (json.JSONDecodeError, OSError):
            docker_config = {}

    # Already configured and matching — skip
    if (
        existing_proxies.get("httpProxy", "") == http_proxy
        and existing_proxies.get("httpsProxy", "") == https_proxy
    ):
        ok(f"Docker 代理已配置: {https_proxy or http_proxy}")
        return

    # Build new proxy config
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
        ok(f"Docker 代理已配置: {https_proxy or http_proxy}")
    except OSError as e:
        warn(f"写入 Docker 配置失败: {e}")


# ============================================================================
# GitHub / SSH tools
# ============================================================================


def get_github_token(token_env: str) -> str:
    """Get GitHub token from environment variable."""
    if not token_env:
        return ""
    return os.environ.get(token_env, "")


def check_ssh_available(host: str = "github.com") -> bool:
    """Check if SSH can connect to the target host.

    Tests via ``ssh -T git@host``. GitHub returns exit 1 on success,
    with stderr containing "successfully authenticated".
    """
    try:
        result = subprocess.run(
            [
                "ssh",
                "-T",
                "-o",
                "StrictHostKeyChecking=accept-new",
                "-o",
                "ConnectTimeout=5",
                f"git@{host}",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        combined = (result.stdout + result.stderr).lower()
        return "successfully authenticated" in combined
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False
