"""Persist deploy-time capability and agent-policy enforcement diagnostics."""

from __future__ import annotations

import json
from collections.abc import Collection, Iterable
from pathlib import Path
from typing import Any

from cataforge.adapter.platform.adapter import PlatformAdapter
from cataforge.core.errors import ConfigError
from cataforge.core.io import read_json
from cataforge.core.types import CAPABILITY_IDS, OPTIONAL_CAPABILITY_IDS
from cataforge.runtime.agent.policy import compile_agent_policy, parse_agent_policy
from cataforge.utils.atomic_write import atomic_write_text

REPORT_VERSION = 1


def build_capability_report(
    adapter: PlatformAdapter,
    agents_source: Path,
) -> dict[str, Any]:
    capabilities: dict[str, Any] = {}
    for capability in sorted(adapter.capability_ids()):
        capabilities[capability] = adapter.resolve_capability(capability).model_dump(mode="json")

    hooks: dict[str, Any] = {}
    for hook_name, policy in sorted(adapter.hook_policies.items()):
        hooks[hook_name] = policy.model_dump(mode="json", exclude_none=True)

    agents: dict[str, Any] = {}
    if agents_source.is_dir():
        for agent_dir in sorted(agents_source.iterdir()):
            source = agent_dir / "AGENT.md"
            if not source.is_file():
                continue
            compiled = compile_agent_policy(parse_agent_policy(source.read_text()), adapter)
            agents[agent_dir.name] = {
                "allowed_tools": compiled.allowed_tools,
                "denied_tools": compiled.denied_tools,
                "sandbox_mode": compiled.sandbox_mode,
                "dropped": sorted(compiled.dropped),
                "unenforced": sorted(compiled.unenforced),
            }

    return {
        "report_version": REPORT_VERSION,
        "platform": adapter.platform_id,
        "capabilities": capabilities,
        "hooks": hooks,
        "agent_tool_policy": adapter.agent_tool_policy,
        "agents": agents,
    }


def write_capability_report(
    path: Path,
    adapter: PlatformAdapter,
    agents_source: Path,
) -> None:
    payload = build_capability_report(adapter, agents_source)
    write_capability_report_payload(path, payload)


def write_capability_report_payload(path: Path, payload: dict[str, Any]) -> None:
    """Persist an already built capability report atomically."""
    atomic_write_text(path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def load_capability_report(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = read_json(path)
    except ConfigError:
        return None
    return payload if isinstance(payload, dict) else None


def summarize_capability_report(report: dict[str, Any]) -> dict[str, int | str]:
    """Return the stable summary consumed by doctor and other diagnostics."""
    capabilities = report.get("capabilities")
    agents = report.get("agents")
    capability_values = capabilities.values() if isinstance(capabilities, dict) else []
    agent_values = agents.values() if isinstance(agents, dict) else []
    return {
        "tool_policy": str(report.get("agent_tool_policy", "unknown")),
        "conditional": sum(
            1
            for item in capability_values
            if isinstance(item, dict) and item.get("status") == "conditional"
        ),
        "unenforced_agents": sum(
            1 for item in agent_values if isinstance(item, dict) and item.get("unenforced")
        ),
    }


def evaluate_capability_report(
    report: dict[str, Any],
    platform_id: str,
    required_capabilities: Iterable[str] = CAPABILITY_IDS,
    optional_capabilities: Collection[str] = OPTIONAL_CAPABILITY_IDS,
) -> list[str]:
    """Evaluate deployed capability state using the same rules as conformance."""
    issues: list[str] = []
    if report.get("report_version") != REPORT_VERSION:
        issues.append(
            f"FAIL: {platform_id} capability report version is unsupported "
            f"({report.get('report_version')!r})"
        )
    if report.get("platform") != platform_id:
        issues.append(
            f"FAIL: capability report platform mismatch "
            f"({report.get('platform')!r} != {platform_id!r})"
        )

    capabilities = report.get("capabilities")
    if not isinstance(capabilities, dict):
        return [*issues, f"FAIL: {platform_id} capability report has no capabilities map"]

    for capability in sorted(required_capabilities):
        resolution = capabilities.get(capability)
        if not isinstance(resolution, dict):
            issues.append(f"FAIL: {platform_id} capability report is missing {capability}")
            continue
        status = resolution.get("status")
        if status == "unsupported":
            level = "INFO" if capability in optional_capabilities else "WARN"
            issues.append(f"{level}: {platform_id} does not map capability {capability}")
        elif status == "conditional":
            issues.append(
                f"INFO: {platform_id} capability {capability} is conditional: "
                f"{resolution.get('reason')}"
            )
        elif status == "replacement":
            issues.append(
                f"INFO: {platform_id} capability {capability} uses replacement tool "
                f"{resolution.get('tool')!r}"
            )
        elif status not in {"native", "available"}:
            issues.append(
                f"FAIL: {platform_id} capability {capability} has unknown status {status!r}"
            )

    summary = summarize_capability_report(report)
    if summary["unenforced_agents"]:
        issues.append(
            f"WARN: {platform_id} has {summary['unenforced_agents']} agent(s) with "
            "unenforced capability policy"
        )
    return issues
