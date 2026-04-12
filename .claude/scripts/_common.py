#!/usr/bin/env python3
"""CataForge 脚本共享工具模块。

提供跨脚本复用的基础设施，消除重复代码:
- 项目根目录定位
- Windows UTF-8 stdout/stderr 修复
- .env 文件解析
- 平台检测
- 终端彩色输出
- 命令可用性检测
"""

import io
import os
import re
import shutil
import subprocess
import sys
from typing import Dict, Optional


# ============================================================================
# 项目根目录定位
# ============================================================================


def find_project_root(start: Optional[str] = None) -> str:
    """从起始路径向上查找包含 .claude/ 目录的项目根。

    Args:
        start: 起始搜索目录。默认从本文件位置向上 2 级
               (scripts/ → .claude/ → project root)。

    Returns:
        项目根目录绝对路径。
    """
    if start is not None:
        d = os.path.abspath(start)
        # 向上查找含 .claude/ 或 CLAUDE.md 的目录
        for _ in range(10):
            if os.path.isdir(os.path.join(d, ".claude")) or os.path.isfile(
                os.path.join(d, "CLAUDE.md")
            ):
                return d
            parent = os.path.dirname(d)
            if parent == d:
                break
            d = parent
        return os.path.abspath(start)

    # 默认: 从本文件位置向上 2 级
    d = os.path.dirname(os.path.abspath(__file__))
    for _ in range(2):
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return d


# ============================================================================
# UTF-8 stdio 修复 (Windows)
# ============================================================================


def ensure_utf8_stdio():
    """确保 stdout/stderr 使用 UTF-8 编码。

    Windows 控制台默认可能使用 cp936/cp1252 等编码，
    导致中文输出乱码或 UnicodeEncodeError。
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
# .env 文件解析
# ============================================================================


def load_dotenv(env_path: Optional[str] = None, override: bool = False) -> Dict[str, str]:
    """解析 .env 文件，返回键值对字典。

    支持格式:
    - KEY=value
    - KEY="quoted value"
    - KEY='single quoted'
    - # 注释行
    - 空行

    Args:
        env_path: .env 文件路径。默认为项目根下的 .env。
        override: 为 True 时同时写入 os.environ（仅写入尚未设置的变量）。

    Returns:
        解析出的键值对字典。
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
                # 去除行内注释 (仅当 # 前有空格时)
                if " #" in line:
                    line = line[: line.index(" #")].rstrip()
                match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", line)
                if not match:
                    continue
                key = match.group(1)
                val = match.group(2).strip()
                # 去除引号
                if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
                    val = val[1:-1]
                result[key] = val
                if override and key not in os.environ:
                    os.environ[key] = val
    except OSError:
        pass

    return result


# ============================================================================
# 平台检测
# ============================================================================


def detect_platform() -> str:
    """检测运行平台。

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
# 终端彩色输出
# ============================================================================


def _supports_color() -> bool:
    """检测终端是否支持 ANSI 颜色。"""
    if os.environ.get("NO_COLOR"):
        return False
    return bool(
        (hasattr(sys.stdout, "isatty") and sys.stdout.isatty())
        or os.environ.get("TERM")
        or os.environ.get("WT_SESSION")
    )


_COLOR_ENABLED = _supports_color()

# ANSI 颜色码
GREEN = "\033[0;32m" if _COLOR_ENABLED else ""
RED = "\033[0;31m" if _COLOR_ENABLED else ""
YELLOW = "\033[1;33m" if _COLOR_ENABLED else ""
BLUE = "\033[0;34m" if _COLOR_ENABLED else ""
CYAN = "\033[0;36m" if _COLOR_ENABLED else ""
BOLD = "\033[1m" if _COLOR_ENABLED else ""
DIM = "\033[2m" if _COLOR_ENABLED else ""
NC = "\033[0m" if _COLOR_ENABLED else ""

# 状态标签
TICK = f"{GREEN}OK{NC}"
CROSS = f"{RED}FAIL{NC}"
WARN_LABEL = f"{YELLOW}WARN{NC}"
INFO_LABEL = f"{BLUE}INFO{NC}"
SKIP_LABEL = f"{DIM}SKIP{NC}"


def ok(msg: str):
    """打印成功消息。"""
    print(f"  [{TICK}] {msg}")


def fail(msg: str):
    """打印失败消息。"""
    print(f"  [{CROSS}] {msg}")


def warn(msg: str):
    """打印警告消息。"""
    print(f"  [{WARN_LABEL}] {msg}")


def info(msg: str):
    """打印信息消息。"""
    print(f"  [{INFO_LABEL}] {msg}")


def skip(msg: str):
    """打印跳过消息。"""
    print(f"  [{SKIP_LABEL}] {msg}")


def section(title: str):
    """打印章节标题。"""
    print(f"\n{BOLD}--- {title} ---{NC}")


# ============================================================================
# 命令检测
# ============================================================================


def has_command(name: str) -> bool:
    """检查命令是否在 PATH 中可用。"""
    return shutil.which(name) is not None


def get_command_version(cmd: list) -> str:
    """获取命令版本输出字符串。"""
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
    """执行命令的统一封装。

    Args:
        cmd: 命令及参数列表。
        timeout: 超时秒数。
        capture: 是否捕获输出。
        check: 是否在非零退出时抛出异常。
        cwd: 工作目录。

    Returns:
        CompletedProcess 对象。
    """
    return subprocess.run(
        cmd,
        capture_output=capture,
        text=True,
        timeout=timeout,
        check=check,
        cwd=cwd,
    )


# ============================================================================
# 端口检测 (跨平台)
# ============================================================================


def is_port_listening(port: int) -> bool:
    """检测本地端口是否有进程监听。跨平台支持。"""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", port)) == 0


def check_port_available(port: int, name: str = "") -> bool:
    """检查端口是否可用（未被占用）。

    Args:
        port: 端口号。
        name: 端口用途描述（用于输出）。

    Returns:
        True 表示端口可用。
    """
    if is_port_listening(port):
        label = f" ({name})" if name else ""
        warn(f"端口 {port}{label} 已被占用")
        return False
    return True
