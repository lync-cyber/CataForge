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
import os
import re
import shutil
import socket
import subprocess
import sys
import warnings
from typing import Dict, Optional

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
