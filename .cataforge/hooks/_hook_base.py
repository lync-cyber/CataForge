#!/usr/bin/env python3
"""CataForge Hook Infrastructure — 跨平台共享工具。

提供:
- read_hook_input(): 统一 stdin JSON 读取
- hook_main(): Hook 入口装饰器
- get_platform(): 当前运行时平台标识
- matches_capability(): 跨平台工具名匹配（从 profile.yaml 单源查询）
"""
import json
import os
import sys
from pathlib import Path


def read_hook_input() -> dict:
    """读取并解析 stdin JSON，带稳健的编码处理。"""
    try:
        raw = sys.stdin.buffer.read()
        text = raw.decode("utf-8", errors="replace")
        return json.loads(text)
    except (json.JSONDecodeError, ValueError, UnicodeDecodeError, AttributeError):
        return {}


def get_platform() -> str:
    """获取当前运行时平台标识。

    检测顺序:
    1. 环境变量 CATAFORGE_PLATFORM（显式覆盖）
    2. 环境变量特征检测
    3. framework.json fallback
    """
    explicit = os.environ.get("CATAFORGE_PLATFORM")
    if explicit:
        return explicit

    if os.environ.get("CURSOR_PROJECT_DIR"):
        return "cursor"
    if os.environ.get("CODEX_HOME"):
        return "codex"

    return _detect_from_framework_json()


def _detect_from_framework_json() -> str:
    """从 framework.json 读取平台标识。"""
    try:
        fj_path = Path(__file__).resolve().parent.parent / "framework.json"
        with open(fj_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        return config.get("runtime", {}).get("platform", "claude-code")
    except (OSError, json.JSONDecodeError):
        return "claude-code"


_CLAUDE_CODE_DEFAULTS = {
    "file_read": "Read", "file_write": "Write", "file_edit": "Edit",
    "file_glob": "Glob", "file_grep": "Grep", "shell_exec": "Bash",
    "web_search": "WebSearch", "web_fetch": "WebFetch",
    "user_question": "AskUserQuestion", "agent_dispatch": "Agent",
}

_tool_map_cache: dict | None = None


def _load_tool_map() -> dict:
    """加载当前平台的 tool_map，带缓存。"""
    global _tool_map_cache
    if _tool_map_cache is not None:
        return _tool_map_cache

    platform_id = get_platform()
    try:
        import yaml
        profile_path = (
            Path(__file__).resolve().parent.parent
            / "platforms" / platform_id / "profile.yaml"
        )
        with open(profile_path, "r", encoding="utf-8") as f:
            profile = yaml.safe_load(f)
        _tool_map_cache = profile.get("tool_map", {})
    except Exception:
        _tool_map_cache = dict(_CLAUDE_CODE_DEFAULTS)
    return _tool_map_cache


def get_platform_tool_name(capability: str) -> str | None:
    """获取当前平台的工具名。None 表示不支持。"""
    return _load_tool_map().get(capability)


def matches_capability(data: dict, capability: str) -> bool:
    """检查 Hook stdin 中的 tool_name 是否匹配指定能力。"""
    tool_name = data.get("tool_name", "")
    expected = get_platform_tool_name(capability)

    if expected is None:
        return False

    if capability == "file_edit":
        edit_tools = {expected}
        write_name = get_platform_tool_name("file_write")
        if write_name:
            edit_tools.add(write_name)
        return tool_name in edit_tools

    return tool_name == expected


_DISPLAY_NAMES = {
    "claude-code": "Claude Code",
    "cursor": "Cursor",
    "codex": "Codex CLI",
    "opencode": "OpenCode",
}


def get_platform_display_name() -> str:
    """获取当前平台的显示名。"""
    return _DISPLAY_NAMES.get(get_platform(), "CataForge")


def hook_main(func):
    """Hook 入口装饰器。异常捕获 + 保证 exit 0。"""
    def wrapper():
        try:
            return func()
        except SystemExit:
            raise
        except Exception as e:
            print(
                f"[HOOK-ERROR] {func.__module__}.{func.__name__}: {e}",
                file=sys.stderr,
            )
            sys.exit(0)
    return wrapper
