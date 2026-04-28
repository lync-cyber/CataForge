"""AGENT.md frontmatter capability ID translation.

Source AGENT.md files use capability IDs (file_read, file_edit, etc.) and
platform-agnostic model tiers (``model_tier: light|standard|heavy``).
At deploy time, both are translated to platform-native equivalents and any
frontmatter fields the platform does not declare in
``agent_config.supported_fields`` are dropped.
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

# Internal-only frontmatter fields — never deployed to any platform. They
# describe CataForge's own dispatch contract, not platform behavior.
# ``allowed_paths`` is enforced by ``agent-dispatch`` skill at write time;
# ``model_tier`` is consumed by the translator and replaced with a native
# ``model:`` (or dropped).
_INTERNAL_FIELDS = frozenset({"allowed_paths", "model_tier"})


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


_FRONTMATTER_RE = re.compile(r"^---\n(.*?\n)---\n", re.DOTALL)


def _split_frontmatter(content: str) -> tuple[str, str, str] | None:
    """Return ``(prefix, frontmatter_body, body)`` or ``None`` if no FM."""
    m = _FRONTMATTER_RE.match(content)
    if not m:
        return None
    return ("---\n", m.group(1), content[m.end():])


def translate_agent_md(
    content: str,
    adapter: PlatformAdapter,
    *,
    dropped_collector: dict[str, set[str]] | None = None,
) -> str:
    """Translate capability IDs and model tier in AGENT.md to platform-native.

    Three transforms:

    1. ``tools:`` / ``disallowedTools:`` capability ids → native tool names
       (or dropped if unmapped). Unmapped caps go to ``dropped_collector``.
    2. ``model_tier: <tier>`` → native ``model: <id>``, or dropped entirely
       when the platform doesn't support per-agent models / resolves at
       runtime / tier is ``inherit`` or ``none``.
    3. Frontmatter keys not in :pyattr:`PlatformAdapter.agent_supported_fields`
       are dropped (after step 2 normalizes ``model_tier`` to ``model``).
       Internal-only fields like ``allowed_paths`` are dropped on every
       platform regardless.

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

    content = re.sub(
        r"^(tools|disallowedTools):\s*(.+)$",
        translate_field,
        content,
        flags=re.MULTILINE,
    )

    # ---- model_tier → native model resolution -------------------------
    content = _translate_model_tier(content, adapter)

    # ---- supported_fields filter --------------------------------------
    content = _filter_unsupported_fields(content, adapter)

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

    return content


_MODEL_TIER_LINE_RE = re.compile(r"^model_tier:\s*(\S+).*$", re.MULTILINE)
_MODEL_LINE_RE = re.compile(r"^model:\s*\S+.*$", re.MULTILINE)


def _translate_model_tier(content: str, adapter: PlatformAdapter) -> str:
    """Replace ``model_tier:`` line with a resolved ``model:`` line, or drop.

    Direct-migration semantics (no legacy fallback):

    * ``model_tier:`` resolved to a native id → write ``model: <native>``.
    * ``model_tier:`` resolves to ``None`` (unsupported / inherit / none) →
      drop the line.
    * Pre-existing legacy ``model: <literal>`` lines are **always dropped**,
      whether or not ``model_tier:`` is present. The literal value can't be
      trusted to translate across platforms; B7-β audit makes this a FAIL
      so source AGENT.md drift is caught before deploy.
    """
    fm_split = _split_frontmatter(content)
    if not fm_split:
        return content
    prefix, fm_body, body = fm_split

    # Strip any legacy ``model:`` line first — direct migration, no carry.
    fm_body = _MODEL_LINE_RE.sub("", fm_body)

    tier_match = _MODEL_TIER_LINE_RE.search(fm_body)
    if not tier_match:
        new_fm = re.sub(r"\n{2,}", "\n", fm_body)
        return prefix + new_fm + "---\n" + body

    tier = tier_match.group(1).strip("'\"")
    resolved = adapter.resolve_agent_model(tier)

    if resolved is None:
        new_fm = _MODEL_TIER_LINE_RE.sub("", fm_body, count=1)
    else:
        new_fm = _MODEL_TIER_LINE_RE.sub(
            f"model: {resolved}", fm_body, count=1
        )

    new_fm = re.sub(r"\n{2,}", "\n", new_fm)
    return prefix + new_fm + "---\n" + body


_FIELD_LINE_RE = re.compile(r"^([A-Za-z_][\w-]*):", re.MULTILINE)


def _filter_unsupported_fields(content: str, adapter: PlatformAdapter) -> str:
    """Drop frontmatter top-level keys not in ``agent_supported_fields``.

    Always-kept fields:
      * ``name`` / ``description`` — universal across platforms.

    Always-dropped fields:
      * Anything in :data:`_INTERNAL_FIELDS` (CataForge-internal, e.g.
        ``allowed_paths`` enforced by agent-dispatch, ``model_tier`` already
        consumed by :func:`_translate_model_tier`).

    When ``agent_supported_fields`` is empty (platform didn't declare it) we
    treat that as "pass through everything except internal" so we don't
    accidentally regress platforms with no profile config.
    """
    fm_split = _split_frontmatter(content)
    if not fm_split:
        return content
    prefix, fm_body, body = fm_split

    supported = set(adapter.agent_supported_fields)
    if not supported:
        return _drop_internal_only(prefix, fm_body, body)

    # Always allow the universal pair regardless of profile declaration.
    supported.update({"name", "description"})

    out_lines: list[str] = []
    drop_active = False
    for line in fm_body.splitlines():
        m = _FIELD_LINE_RE.match(line)
        if m:
            key = m.group(1)
            if key in _INTERNAL_FIELDS or key not in supported:
                drop_active = True
                continue
            drop_active = False
            out_lines.append(line)
        elif drop_active:
            # Continuation line of a dropped multi-line value (list / map).
            if line.startswith((" ", "\t", "-")) or line.strip() == "":
                continue
            # Any non-indented, non-empty line ends the dropped block.
            drop_active = False
            out_lines.append(line)
        else:
            out_lines.append(line)

    new_fm = "\n".join(out_lines)
    if not new_fm.endswith("\n"):
        new_fm += "\n"
    return prefix + new_fm + "---\n" + body


def _drop_internal_only(prefix: str, fm_body: str, body: str) -> str:
    """Fallback when the platform declared no supported_fields — drop only
    CataForge-internal fields and leave everything else as-is."""
    out_lines: list[str] = []
    drop_active = False
    for line in fm_body.splitlines():
        m = _FIELD_LINE_RE.match(line)
        if m:
            key = m.group(1)
            if key in _INTERNAL_FIELDS:
                drop_active = True
                continue
            drop_active = False
            out_lines.append(line)
        elif drop_active:
            if line.startswith((" ", "\t", "-")) or line.strip() == "":
                continue
            drop_active = False
            out_lines.append(line)
        else:
            out_lines.append(line)
    new_fm = "\n".join(out_lines)
    if not new_fm.endswith("\n"):
        new_fm += "\n"
    return prefix + new_fm + "---\n" + body
