"""AGENT.md frontmatter 能力标识符翻译。

源 AGENT.md 使用能力标识符（file_read, file_edit 等）。
deploy 时翻译为平台原生工具名（Read, StrReplace 等）。
"""
from __future__ import annotations
import re
from .profile_loader import get_tool_map


def translate_agent_md(content: str, platform_id: str) -> str:
    """翻译 AGENT.md 的 tools 和 disallowedTools 字段。

    Args:
        content: AGENT.md 全文
        platform_id: 目标平台

    Returns:
        翻译后的 AGENT.md 全文（仅 frontmatter 变更）。
    """
    tool_map = get_tool_map(platform_id)

    def translate_field(match: re.Match) -> str:
        field_name = match.group(1)
        caps_str = match.group(2)
        caps = [c.strip() for c in caps_str.split(",") if c.strip()]

        native_names = []
        for cap in caps:
            name = tool_map.get(cap)
            if name is not None:
                native_names.append(name)

        return f"{field_name}: {', '.join(native_names)}"

    content = re.sub(
        r"^(tools|disallowedTools):\s*(.+)$",
        translate_field,
        content,
        flags=re.MULTILINE,
    )
    return content
