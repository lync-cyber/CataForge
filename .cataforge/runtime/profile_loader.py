"""平台 profile 加载与工具名解析。

从 .cataforge/platforms/{platform_id}/profile.yaml 加载配置。
是工具名映射的单一事实来源。
"""
from __future__ import annotations
import json
import os
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]


_PLATFORMS_DIR = Path(__file__).resolve().parent.parent / "platforms"
_FRAMEWORK_JSON = Path(__file__).resolve().parent.parent / "framework.json"

_profile_cache: dict[str, dict] = {}


def detect_platform() -> str:
    """从环境变量或 framework.json 读取 runtime.platform，缺省 claude-code。"""
    explicit = os.environ.get("CATAFORGE_PLATFORM")
    if explicit:
        return explicit

    if os.environ.get("CURSOR_PROJECT_DIR"):
        return "cursor"
    if os.environ.get("CODEX_HOME"):
        return "codex"

    try:
        with open(_FRAMEWORK_JSON, "r", encoding="utf-8") as f:
            config = json.load(f)
        return config.get("runtime", {}).get("platform", "claude-code")
    except (OSError, json.JSONDecodeError):
        return "claude-code"


def load_profile(platform_id: str | None = None) -> dict:
    """加载指定平台的 profile.yaml（带缓存）。"""
    pid = platform_id or detect_platform()
    if pid in _profile_cache:
        return _profile_cache[pid]

    path = _PLATFORMS_DIR / pid / "profile.yaml"
    if yaml is not None:
        with open(path, "r", encoding="utf-8") as f:
            profile = yaml.safe_load(f)
    else:
        json_path = path.with_suffix(".json")
        if json_path.is_file():
            with open(json_path, "r", encoding="utf-8") as f:
                profile = json.load(f)
        else:
            raise ImportError(
                f"PyYAML not available and no JSON fallback at {json_path}"
            )

    _profile_cache[pid] = profile
    return profile


def get_tool_map(platform_id: str | None = None) -> dict[str, str | None]:
    """获取能力标识符 → 平台原生工具名映射。"""
    profile = load_profile(platform_id)
    return profile.get("tool_map", {})


def resolve_tool_name(capability: str, platform_id: str | None = None) -> str | None:
    """将单个能力标识符翻译为平台工具名。None 表示不支持。"""
    return get_tool_map(platform_id).get(capability)


def resolve_tools_list(
    capabilities: list[str], platform_id: str | None = None
) -> list[str]:
    """批量翻译，跳过不支持的能力。"""
    tool_map = get_tool_map(platform_id)
    return [name for cap in capabilities if (name := tool_map.get(cap)) is not None]


def get_dispatch_info(platform_id: str | None = None) -> dict:
    """获取调度工具信息。"""
    profile = load_profile(platform_id)
    return profile.get("dispatch", {})


def get_hook_degradation(platform_id: str | None = None) -> dict[str, str]:
    """获取 Hook 退化配置。"""
    profile = load_profile(platform_id)
    return profile.get("hooks", {}).get("degradation", {})
