"""Compile canonical agent capability policy to platform-native enforcement."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from cataforge.adapter.platform.adapter import PlatformAdapter

_WRITE_CAPABILITIES = frozenset({"file_write", "file_edit"})


@dataclass(frozen=True)
class AgentPolicy:
    allowed: frozenset[str] = frozenset()
    denied: frozenset[str] = frozenset()


@dataclass
class CompiledAgentPolicy:
    allowed_tools: list[str] = field(default_factory=list)
    denied_tools: list[str] = field(default_factory=list)
    dropped: set[str] = field(default_factory=set)
    unenforced: set[str] = field(default_factory=set)
    sandbox_mode: str | None = None


def parse_agent_policy(content: str) -> AgentPolicy:
    """Read canonical allow/deny capability sets from AGENT.md frontmatter."""
    import re

    import yaml

    match = re.match(r"^---\n(.*?)\n---\n", content, re.DOTALL)
    if match is None:
        return AgentPolicy()
    raw = yaml.safe_load(match.group(1)) or {}
    if not isinstance(raw, dict):
        return AgentPolicy()
    return AgentPolicy(
        allowed=frozenset(_capability_values(raw.get("tools"))),
        denied=frozenset(_capability_values(raw.get("disallowedTools"))),
    )


def _capability_values(raw: Any) -> list[str]:
    if isinstance(raw, str):
        s = raw.strip()
        # A quoted flow-list (``tools: '[]'``) parses as the string "[]";
        # unwrap the brackets so the empty-list forms yield no capabilities
        # rather than a spurious token named "[]".
        if s.startswith("[") and s.endswith("]"):
            s = s[1:-1].strip()
        return [item.strip() for item in s.split(",") if item.strip()]
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    return []


def compile_agent_policy(
    policy: AgentPolicy,
    adapter: PlatformAdapter,
) -> CompiledAgentPolicy:
    """Compile policy without silently widening ambiguous permissions."""
    overlap = policy.allowed & policy.denied
    if overlap:
        raise ValueError(
            f"capabilities declared in both tools and disallowedTools: {sorted(overlap)}"
        )

    compiled = CompiledAgentPolicy()
    if adapter.agent_tool_policy == "inherit_only":
        compiled.unenforced.update(policy.allowed | policy.denied)
        if _WRITE_CAPABILITIES.issubset(policy.denied) and not (
            _WRITE_CAPABILITIES & policy.allowed
        ):
            compiled.sandbox_mode = "read-only"
            compiled.unenforced.difference_update(_WRITE_CAPABILITIES)
        return compiled

    decisions: dict[str, dict[str, set[str]]] = {}
    for decision, capabilities in (("allow", policy.allowed), ("deny", policy.denied)):
        for capability in capabilities:
            binding = adapter.get_capability_binding(capability)
            if binding is None or binding.kind == "unsupported" or binding.tool is None:
                compiled.dropped.add(capability)
                continue
            by_decision = decisions.setdefault(binding.tool, {"allow": set(), "deny": set()})
            by_decision[decision].add(capability)

    for native_tool, native_decisions in sorted(decisions.items()):
        if native_decisions["allow"] and native_decisions["deny"]:
            conflicting_capabilities = sorted(native_decisions["allow"] | native_decisions["deny"])
            raise ValueError(
                f"native tool {native_tool!r} has mixed allow/deny decisions "
                f"from capabilities {conflicting_capabilities}"
            )
        if native_decisions["allow"]:
            compiled.allowed_tools.append(native_tool)
        elif adapter.agent_tool_policy == "allow_deny":
            compiled.denied_tools.append(native_tool)
        else:
            compiled.unenforced.update(native_decisions["deny"])

    return compiled
