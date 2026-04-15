"""AGENT.md frontmatter capability ID translation.

Source AGENT.md files use capability IDs (file_read, file_edit, etc.).
At deploy time, these are translated to platform-native tool names.
"""

from __future__ import annotations

import logging
import re

from cataforge.platform.base import PlatformAdapter

logger = logging.getLogger("cataforge.agent.translator")


def translate_agent_md(content: str, adapter: PlatformAdapter) -> str:
    """Translate capability IDs in an AGENT.md to platform-native tool names.

    Only modifies `tools:` and `disallowedTools:` frontmatter fields.
    """
    tool_map = adapter.get_tool_map()

    def translate_field(match: re.Match[str]) -> str:
        field_name = match.group(1)
        caps_str = match.group(2).strip()

        # Normalize YAML flow-style list syntax: `[]` or `[a, b]` → `a, b`.
        # Without this, a literal `disallowedTools: []` would parse as the
        # single "capability" `[]`, get looked up in tool_map, and spam a
        # bogus "no platform mapping" warning.
        if caps_str.startswith("[") and caps_str.endswith("]"):
            caps_str = caps_str[1:-1]

        caps = [c.strip() for c in caps_str.split(",") if c.strip()]

        if not caps:
            return f"{field_name}: []"

        dropped = [c for c in caps if tool_map.get(c) is None]
        if dropped:
            logger.warning(
                "Skipping capabilities with no platform mapping (%s): %s",
                field_name,
                dropped,
            )

        native_names = [
            name for cap in caps if (name := tool_map.get(cap)) is not None
        ]
        return f"{field_name}: {', '.join(native_names)}"

    return re.sub(
        r"^(tools|disallowedTools):\s*(.+)$",
        translate_field,
        content,
        flags=re.MULTILINE,
    )
