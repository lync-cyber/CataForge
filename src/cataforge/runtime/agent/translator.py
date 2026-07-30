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
from typing import TYPE_CHECKING

from cataforge.runtime.agent.policy import compile_agent_policy, parse_agent_policy

if TYPE_CHECKING:
    from cataforge.adapter.platform.adapter import PlatformAdapter

logger = logging.getLogger("cataforge.runtime.agent.translator")

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

# Frontmatter fields whose silent removal changes the agent's privilege
# posture. When a platform does not declare support for one of these, dropping
# it means a high-privilege declaration in source becomes unenforced on that
# platform — the deploy must surface a WARN rather than drop quietly.
_SECURITY_SENSITIVE_FIELDS = frozenset({"permissionMode"})


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
    return ("---\n", m.group(1), content[m.end() :])


def _replace_frontmatter_sequence_fields(
    content: str,
    replacements: dict[str, list[str]],
) -> str:
    """Replace top-level sequence fields without leaving block-list residue."""
    match = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n?", content, re.DOTALL)
    if match is None:
        return content

    lines = match.group(1).splitlines()
    top_level_key = re.compile(r"^([A-Za-z_][\w-]*):(?:\s.*)?$")
    rendered: list[str] = []
    index = 0
    while index < len(lines):
        key_match = top_level_key.match(lines[index])
        key = key_match.group(1) if key_match else None
        if key not in replacements:
            rendered.append(lines[index])
            index += 1
            continue

        values = replacements[key]
        rendered.append(f"{key}: {', '.join(values) if values else '[]'}")
        index += 1
        while index < len(lines) and top_level_key.match(lines[index]) is None:
            index += 1

    suffix = content[match.end() :]
    return f"---\n{chr(10).join(rendered)}\n---\n{suffix}"


def translate_agent_md(
    content: str,
    adapter: PlatformAdapter,
    *,
    agent_id: str | None = None,
    dropped_collector: dict[str, set[str]] | None = None,
    warnings_collector: list[str] | None = None,
    policy_unenforced_collector: dict[str, set[str]] | None = None,
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

    Diagnostics that are not plain unmapped-capability drops — a native tool
    that resolves into BOTH ``tools`` and ``disallowedTools`` (allow/deny
    collision), and a dropped security-sensitive field — are routed to
    ``warnings_collector`` so the deployer can surface them.

    Parameters
    ----------
    dropped_collector:
        Optional dict that accumulates ``{field_name: {capability, ...}}``
        across many calls. When provided, this function does **not** emit
        per-agent log warnings — the caller is expected to emit a single
        aggregated message after processing all agents. When not provided,
        falls back to the historical per-agent ``logger.warning`` behaviour
        (still de-duplicated within a single call and gated on real noise).
    warnings_collector:
        Optional list that accumulates free-form WARN strings across many
        calls (allow/deny tool collisions, dropped security-sensitive
        fields). The deployer appends these to its returned action lines.
    """
    local_dropped: dict[str, set[str]] = {}
    compiled = compile_agent_policy(parse_agent_policy(content), adapter)
    if compiled.dropped:
        local_dropped["agent_policy"] = set(compiled.dropped)
    if compiled.unenforced:
        if policy_unenforced_collector is not None:
            policy_unenforced_collector.setdefault(agent_id or "<unknown>", set()).update(
                compiled.unenforced
            )
        elif warnings_collector is not None:
            warnings_collector.append(
                f"WARN: {adapter.platform_id}: per-agent tool policy is not enforced "
                f"for capabilities {sorted(compiled.unenforced)}."
            )

    rendered_policy = {
        "tools": compiled.allowed_tools,
        "disallowedTools": compiled.denied_tools,
    }

    content = _replace_frontmatter_sequence_fields(content, rendered_policy)
    if compiled.sandbox_mode:
        content = _set_frontmatter_scalar(content, "sandbox_mode", compiled.sandbox_mode)

    # ---- model_tier → native model resolution -------------------------
    content = _translate_model_tier(content, adapter)

    # ---- skills degradation (platforms without a skills surface) ------
    content = _inject_skills_fallback(content, adapter)

    # ---- supported_fields filter --------------------------------------
    content = _filter_unsupported_fields(content, adapter, warnings_collector)

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


def _capabilities_from_field(content: str, field_name: str) -> list[str]:
    match = re.search(rf"^{re.escape(field_name)}:\s*(.+)$", content, flags=re.MULTILINE)
    if match is None:
        return []
    inner = _clean_cap_list_str(match.group(1))
    return [
        capability
        for raw in inner.split(",")
        if (capability := raw.strip()) and capability not in _NOISE_TOKENS
    ]


def _set_frontmatter_scalar(content: str, key: str, value: str) -> str:
    fm_split = _split_frontmatter(content)
    if fm_split is None:
        return content
    prefix, fm_body, body = fm_split
    pattern = re.compile(rf"^{re.escape(key)}:\s*.*$", re.MULTILINE)
    if pattern.search(fm_body):
        fm_body = pattern.sub(f"{key}: {value}", fm_body, count=1)
    else:
        fm_body += f"{key}: {value}\n"
    return prefix + fm_body + "---\n" + body


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
        new_fm = _MODEL_TIER_LINE_RE.sub(f"model: {resolved}", fm_body, count=1)

    new_fm = re.sub(r"\n{2,}", "\n", new_fm)
    return prefix + new_fm + "---\n" + body


_FIELD_LINE_RE = re.compile(r"^([A-Za-z_][\w-]*):", re.MULTILINE)


def _filter_unsupported_fields(
    content: str,
    adapter: PlatformAdapter,
    warnings_collector: list[str] | None = None,
) -> str:
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

    Dropping a field in :data:`_SECURITY_SENSITIVE_FIELDS` (e.g.
    ``permissionMode``) on a platform that does not declare support for it
    means a high-privilege source declaration becomes unenforced. Such drops
    are routed to ``warnings_collector`` (when provided) so the deployer can
    surface a WARN rather than removing them silently.
    """
    fm_split = _split_frontmatter(content)
    if not fm_split:
        return content
    prefix, fm_body, body = fm_split

    supported = set(adapter.agent_supported_fields)
    if not supported:
        return _drop_internal_only(adapter.platform_id, prefix, fm_body, body, warnings_collector)

    # Always allow the universal pair regardless of profile declaration.
    supported.update({"name", "description"})

    out_lines: list[str] = []
    drop_active = False
    for line in fm_body.splitlines():
        m = _FIELD_LINE_RE.match(line)
        if m:
            key = m.group(1)
            if key in _INTERNAL_FIELDS or key not in supported:
                if key not in _INTERNAL_FIELDS:
                    _warn_security_sensitive_drop(adapter.platform_id, key, warnings_collector)
                    _warn_skills_drop(adapter, key, warnings_collector)
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


def _warn_security_sensitive_drop(
    platform_id: str, key: str, warnings_collector: list[str] | None
) -> None:
    """Record a WARN when an unsupported field is security-sensitive."""
    if warnings_collector is None or key not in _SECURITY_SENSITIVE_FIELDS:
        return
    warnings_collector.append(
        f"WARN: {platform_id}: agent field {key!r} is not supported on this "
        "platform and was dropped — the high-privilege declaration is "
        "unenforced here."
    )


def _declared_skills(content: str) -> list[str]:
    """Skill ids from the frontmatter ``skills:`` field ([] when absent)."""
    fm_split = _split_frontmatter(content)
    if fm_split is None:
        return []
    try:
        import yaml

        data = yaml.safe_load(fm_split[1]) or {}
    except Exception:
        return []
    skills = data.get("skills") if isinstance(data, dict) else None
    if isinstance(skills, str):
        # AGENT.md convention allows a bare comma-separated scalar
        # (``skills: research, doc-gen``) alongside YAML list forms.
        skills = [part.strip() for part in skills.split(",")]
    if not isinstance(skills, list):
        return []
    return [str(s).strip() for s in skills if str(s).strip()]


def _inject_skills_fallback(content: str, adapter: PlatformAdapter) -> str:
    """Degradation contract for platforms without a skills surface.

    The frontmatter ``skills:`` list is unenforceable there, so the agent
    body gains an explicit read-first instruction pointing at the canonical
    ``.cataforge/skills/<id>/SKILL.md`` sources — the skill context stays
    reachable instead of being dropped silently.
    """
    if adapter.needs_skill_deploy:
        return content
    skills = _declared_skills(content)
    if not skills:
        return content
    fm_split = _split_frontmatter(content)
    if fm_split is None:
        return content
    prefix, fm_body, body = fm_split
    lines = "\n".join(f"> - `.cataforge/skills/{sid}/SKILL.md`" for sid in skills)
    note = (
        "> **Skill 依赖（本平台无原生 skills 面）**：执行任务前先读取下列"
        " SKILL.md 获取对应工作流方法：\n" + lines + "\n\n"
    )
    return prefix + fm_body + "---\n" + note + body.lstrip("\n")


def _warn_skills_drop(
    adapter: PlatformAdapter, key: str, warnings_collector: list[str] | None
) -> None:
    """Record a note when an agent's ``skills`` field is dropped on a platform
    that does not deploy skills — the read-first fallback injected by
    :func:`_inject_skills_fallback` carries the context instead."""
    if warnings_collector is None or key != "skills" or adapter.needs_skill_deploy:
        return
    warnings_collector.append(
        f"NOTE: {adapter.platform_id}: no native skills surface — agent skill "
        "context degraded to explicit `.cataforge/skills/<id>/SKILL.md` "
        "read-first instructions in the agent body."
    )


def _drop_internal_only(
    platform_id: str,
    prefix: str,
    fm_body: str,
    body: str,
    warnings_collector: list[str] | None = None,
) -> str:
    """Fallback when the platform declared no supported_fields — drop only
    CataForge-internal fields and leave everything else as-is.

    Nothing security-sensitive is dropped on this path (non-internal fields
    pass through), so no WARN is emitted here; the parameter is accepted for a
    uniform call signature with :func:`_filter_unsupported_fields`."""
    del warnings_collector  # no field is dropped that warrants a WARN here
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
