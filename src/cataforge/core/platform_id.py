"""Default-platform resolution from framework.json data (schema v2 + v1).

Dependency-free so the hook runtime and adapter registry can resolve the
platform without importing the full ConfigManager stack.
"""

from __future__ import annotations

from typing import Any

FALLBACK_PLATFORM = "claude-code"


def default_platform_from_config_data(data: dict[str, Any]) -> str | None:
    """Declared default platform: ``deployment.default_platform`` with
    legacy ``runtime.platform`` fallback; ``None`` when neither declares."""
    deployment = data.get("deployment")
    if isinstance(deployment, dict):
        platform = deployment.get("default_platform")
        if platform:
            return str(platform)
    runtime = data.get("runtime")
    if isinstance(runtime, dict):
        platform = runtime.get("platform")
        if platform:
            return str(platform)
    return None


def deployment_targets_from_config_data(data: dict[str, Any]) -> list[str]:
    """Declared enabled-platform set; falls back to the single default."""
    deployment = data.get("deployment")
    if isinstance(deployment, dict):
        targets = deployment.get("targets")
        if isinstance(targets, list) and targets:
            return [str(t) for t in targets]
    declared = default_platform_from_config_data(data)
    return [declared] if declared else [FALLBACK_PLATFORM]
