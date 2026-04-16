"""AGENT.md frontmatter capability ID translation.

Source AGENT.md files use capability IDs (file_read, file_edit, etc.).
At deploy time, these are translated to platform-native tool names.
"""

from __future__ import annotations

import logging
import re

from cataforge.platform.base import PlatformAdapter

logger = logging.getLogger("cataforge.agent.translator")

# Tokens that are never valid capability identifiers but sometimes slip into
# the parsed list when the source YAML uses flow-style or quoted-empty
# values (e.g. ``tools: '[]'`` / ``tools: [ ]  # comment``). Filtering them
# here prevents spurious "no platform mapping" warnings.
_NOISE_TOKENS = frozenset({"", "[]", "''", '""', "null", "~"})


def _clean_cap_list_str(raw: str) -> str:
    """Strip YAML-ish decoration around a flow-style capability list.

    Handles:

    * Surrounding whitespace.
    * Outer single/double quotes (``'[...]'`` / ``"[...]"``).
    * Trailing ``# comment``.
    * Outer square brackets (``[a, b]`` → ``a, b``).

    Returns the inner comma-separated capability text, possibly empty.
    """
    s = raw.strip()

    # Drop trailing YAML comment if present (comment cannot be mid-token for
    # the simple capability-list grammar we accept).
    if "#" in s:
        hash_idx = s.index("#")
        s = s[:hash_idx].rstrip()

    # Unwrap outer quotes.
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
        s = s[1:-1].strip()

    # Unwrap flow-style list brackets.
    if s.startswith("[") and s.endswith("]"):
        s = s[1:-1].strip()

    return s


def translate_agent_md(
    content: str,
    adapter: PlatformAdapter,
    *,
    dropped_collector: dict[str, set[str]] | None = None,
) -> str:
    """Translate capability IDs in an AGENT.md to platform-native tool names.

    Only modifies ``tools:`` and ``disallowedTools:`` frontmatter fields.

    Parameters
    ----------
    dropped_collector:
        Optional dict that accumulates ``{field_name: {capability, ...}}``
        across many calls. When provided, this function does **not** emit
        per-agent log warnings — the caller is expected to emit a single
        aggregated message after processing all agents. When not provided,
        falls back to the historical per-agent ``logger.warning`` behaviour
        (still de-duplicated within a single call and gated on real noise).
    """
    tool_map = adapter.get_tool_map()
    # Per-call aggregation so a single agent with the same missing cap in
    # both ``tools:`` and ``disallowedTools:`` logs at most once.
    local_dropped: dict[str, set[str]] = {}

    def translate_field(match: re.Match[str]) -> str:
        field_name = match.group(1)
        inner = _clean_cap_list_str(match.group(2))

        caps = [c.strip() for c in inner.split(",")]
        # Filter blanks + well-known noise tokens that could never be valid
        # capability identifiers.
        caps = [c for c in caps if c and c not in _NOISE_TOKENS]

        if not caps:
            return f"{field_name}: []"

        dropped = [c for c in caps if tool_map.get(c) is None]
        if dropped:
            local_dropped.setdefault(field_name, set()).update(dropped)

        native_names = [
            name for cap in caps if (name := tool_map.get(cap)) is not None
        ]
        return f"{field_name}: {', '.join(native_names)}"

    result = re.sub(
        r"^(tools|disallowedTools):\s*(.+)$",
        translate_field,
        content,
        flags=re.MULTILINE,
    )

    if local_dropped:
        if dropped_collector is not None:
            # Defer to caller: aggregate across all agents and emit once.
            for field, caps in local_dropped.items():
                dropped_collector.setdefault(field, set()).update(caps)
        else:
            # Legacy per-agent path: one line per field, de-duplicated.
            for field, caps in local_dropped.items():
                logger.warning(
                    "Skipping capabilities with no platform mapping (%s): %s",
                    field,
                    sorted(caps),
                )

    return result
