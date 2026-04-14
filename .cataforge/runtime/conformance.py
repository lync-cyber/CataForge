"""平台合规检查。"""
from __future__ import annotations
from .profile_loader import load_profile
from .types import CAPABILITY_IDS


REQUIRED_CAPABILITIES = [
    "file_read", "file_write", "file_edit", "file_glob",
    "file_grep", "shell_exec", "agent_dispatch",
]


def check_conformance(platform_id: str) -> list[str]:
    """检查平台 profile 合规性，返回问题列表（空列表=合规）。"""
    issues: list[str] = []

    try:
        profile = load_profile(platform_id)
    except Exception as e:
        return [f"FAIL: 无法加载 {platform_id} profile: {e}"]

    if profile.get("platform_id") != platform_id:
        issues.append("FAIL: platform_id 不匹配")

    tool_map = profile.get("tool_map", {})
    for cap in REQUIRED_CAPABILITIES:
        if cap not in tool_map or tool_map[cap] is None:
            issues.append(f"WARN: {platform_id} 未映射必需能力 {cap}")

    if "dispatch" not in profile:
        issues.append("FAIL: 缺少 dispatch 配置")

    if "hooks" not in profile:
        issues.append("FAIL: 缺少 hooks 配置")

    return issues
