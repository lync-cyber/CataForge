#!/usr/bin/env python3
"""CataForge 脚本共享工具模块。

提供跨脚本复用的基础设施，消除重复代码:
- 项目根目录定位
- Windows UTF-8 stdout/stderr 修复
- .env 文件解析
- 平台检测
- 终端彩色输出
- 命令可用性检测
- 框架配置读取 (framework.json)
- 版本解析 / 阶段管理
- SSH 可用性检测
"""

import io
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import warnings
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
        fallback = os.path.abspath(start)
        warnings.warn(
            f"find_project_root: 未找到包含 .claude/ 的项目根目录，"
            f"回退到起始路径 {fallback}",
            stacklevel=2,
        )
        return fallback

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


def load_dotenv(
    env_path: Optional[str] = None, set_env: bool = False
) -> Dict[str, str]:
    """解析 .env 文件，返回键值对字典。

    支持格式:
    - KEY=value
    - KEY="quoted value"
    - KEY='single quoted'
    - # 注释行
    - 空行

    Args:
        env_path: .env 文件路径。默认为项目根下的 .env。
        set_env: 为 True 时同时写入 os.environ（仅写入尚未设置的变量，
                 不会覆盖已有环境变量）。

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
                match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", line)
                if not match:
                    continue
                key = match.group(1)
                val = match.group(2).strip()
                # 去除引号
                if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
                    val = val[1:-1]
                else:
                    # 去除行内注释 (仅对未加引号的值，避免破坏含 # 的引号内容)
                    if " #" in val:
                        val = val[: val.index(" #")].rstrip()
                result[key] = val
                if set_env and key not in os.environ:
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
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=check,
        cwd=cwd,
    )


# ============================================================================
# 端口检测 (跨平台)
# ============================================================================


def is_port_listening(port: int) -> bool:
    """检测本地端口是否有进程监听。跨平台支持。

    Windows 上 settimeout + connect_ex 会返回 WSAEWOULDBLOCK (10035)
    而非阻塞等待，因此改用 connect() + 异常捕获。
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        try:
            s.connect(("127.0.0.1", port))
            return True
        except (ConnectionRefusedError, TimeoutError, OSError):
            return False


def find_available_port(preferred: int, name: str = "", max_tries: int = 20) -> int:
    """返回可用端口。优先使用 preferred，被占用则向上递增查找。

    Args:
        preferred: 首选端口号。
        name: 端口用途描述 (用于输出)。
        max_tries: 最大尝试次数。

    Returns:
        可用端口号。
    """
    for offset in range(max_tries):
        port = preferred + offset
        if not is_port_listening(port):
            if offset > 0:
                label = f" ({name})" if name else ""
                warn(f"端口 {preferred}{label} 已被占用，自动切换到 {port}")
            return port
    # 所有端口都被占用，返回首选端口 (后续部署会报错)
    return preferred


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


# ============================================================================
# 版本解析
# ============================================================================

VERSION_FILE = "pyproject.toml"


def parse_semver(ver_str: str) -> tuple:
    """解析 semver 字符串为 (major, minor, patch) 元组，支持可选 v 前缀"""
    ver_str = ver_str.strip()
    match = re.match(r"^v?(\d+)\.(\d+)\.(\d+)", ver_str)
    if not match:
        warnings.warn(f"parse_semver: 无法解析版本号 '{ver_str}'，回退到 (0,0,0)")
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
# JSON 工具
# ============================================================================


def load_json_lenient(file_path: str) -> dict:
    """加载 JSON 文件，容忍尾随逗号等常见格式问题"""
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        content = re.sub(r",\s*([}\]])", r"\1", content)
        return json.loads(content)


# ============================================================================
# 阶段管理
# ============================================================================

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


def phase_index(phase: str) -> int:
    """返回阶段在生命周期中的索引，未知阶段返回 -1"""
    try:
        return PHASE_ORDER.index(phase)
    except ValueError:
        return -1


# ============================================================================
# 输入校验
# ============================================================================


def validate_branch_name(branch: str) -> bool:
    """校验分支名，防止注入异常字符"""
    return bool(re.match(r"^[a-zA-Z0-9._/-]+$", branch))


# ============================================================================
# 框架配置 (framework.json)
# ============================================================================

FRAMEWORK_CONFIG_FILE = os.path.join(".claude", "framework.json")


def load_framework_config() -> dict:
    """读取 .claude/framework.json 统一框架配置"""
    if not os.path.exists(FRAMEWORK_CONFIG_FILE):
        return {}
    with open(FRAMEWORK_CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def load_framework_constants() -> dict:
    """从 framework.json 加载 constants 节，返回 {常量名: 值} 字典。

    未找到配置文件或无 constants 节时返回空字典。
    """
    config = load_framework_config()
    return config.get("constants", {})


def get_constant(name: str, default=None):
    """按名称获取单个框架常量值，缺失时返回 default。"""
    return load_framework_constants().get(name, default)


# ============================================================================
# 模板注册表 (_registry.yaml)
# ============================================================================

_REGISTRY_CACHE: Optional[dict] = None
REGISTRY_FILE = os.path.join(
    ".claude", "skills", "doc-gen", "templates", "_registry.yaml"
)


def load_template_registry(project_root: Optional[str] = None) -> dict:
    """加载 .claude/skills/doc-gen/templates/_registry.yaml 模板注册表。

    返回 {template_id: {path, doc_type, mode, role, ...}} 字典。
    结果在进程内缓存。
    """
    global _REGISTRY_CACHE
    if _REGISTRY_CACHE is not None:
        return _REGISTRY_CACHE

    if project_root is None:
        project_root = find_project_root()

    reg_path = os.path.join(project_root, REGISTRY_FILE)
    if not os.path.isfile(reg_path):
        return {}

    with open(reg_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 简易 YAML 解析（避免依赖 PyYAML）
    templates: Dict[str, dict] = {}
    current_id: Optional[str] = None
    current_dict: Optional[dict] = None
    current_list_key: Optional[str] = None

    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        # 顶级键跳过
        if stripped in ("templates:", 'version: "1"', "version: '1'"):
            continue

        indent = len(line) - len(line.lstrip())

        # template_id 行 (indent=2): "  prd:"
        if indent == 2 and stripped.endswith(":") and not stripped.startswith("-"):
            if current_id and current_dict:
                templates[current_id] = current_dict
            current_id = stripped[:-1].strip()
            current_dict = {}
            current_list_key = None
            continue

        # 属性行 (indent=4): "    path: standard/prd.md"
        if indent == 4 and ":" in stripped and current_dict is not None:
            key, _, val = stripped.partition(":")
            key = key.strip()
            val = val.strip()
            if val.startswith("[") and val.endswith("]"):
                items = val[1:-1].split(",")
                current_dict[key] = [
                    i.strip().strip('"').strip("'") for i in items if i.strip()
                ]
                current_list_key = None
            elif not val:
                current_dict[key] = []
                current_list_key = key
            else:
                current_dict[key] = val.strip('"').strip("'")
                current_list_key = None
            continue

        # 列表续行 (indent=4+): "    - item"
        if stripped.startswith("- ") and current_list_key and current_dict is not None:
            current_dict.setdefault(current_list_key, []).append(
                stripped[2:].strip().strip('"').strip("'")
            )

    if current_id and current_dict:
        templates[current_id] = current_dict

    _REGISTRY_CACHE = templates
    return templates


def build_doc_type_map(project_root: Optional[str] = None) -> Dict[str, str]:
    """从模板注册表构建 doc_id → doc_type 映射（替代硬编码 DOC_TYPE_MAP）。"""
    registry = load_template_registry(project_root)
    result: Dict[str, str] = {}
    for template_id, meta in registry.items():
        doc_type = meta.get("doc_type", "")
        if doc_type:
            result[template_id] = doc_type
    return result


def build_template_path_map(
    project_root: Optional[str] = None,
) -> Dict[str, Dict[str, str]]:
    """从模板注册表构建 doc_type → {volume_type → relative_path} 映射（替代硬编码 _TEMPLATE_MAP）。

    返回的 path 是相对于 templates/ 目录的路径（如 "standard/prd.md"）。
    """
    registry = load_template_registry(project_root)
    result: Dict[str, Dict[str, str]] = {}
    for template_id, meta in registry.items():
        doc_type = meta.get("doc_type", "")
        role = meta.get("role", "main")
        path = meta.get("path", "")
        if not doc_type or not path:
            continue
        if doc_type not in result:
            result[doc_type] = {}
        if role == "volume":
            vol_type = meta.get("volume_type", "")
            if vol_type:
                result[doc_type][vol_type] = path
        else:
            result[doc_type]["main"] = path
    return result


# ============================================================================
# GitHub / SSH 工具
# ============================================================================


def get_github_token(token_env: str) -> str:
    """从环境变量获取 GitHub token（.env 已由 load_dotenv(set_env=True) 预加载）"""
    if not token_env:
        return ""
    return os.environ.get(token_env, "")


def check_ssh_available(host: str = "github.com") -> bool:
    """检测 SSH 是否可连接到目标主机（用于判断是否优先使用 SSH 协议）

    通过 `ssh -T git@host` 测试。GitHub 在认证成功时返回 exit 1（正常行为），
    stderr 包含 "successfully authenticated" 表示 SSH 可用。
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
