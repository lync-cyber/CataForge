"""Factories for authoring strict typed platform-profile test fixtures."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def typed_profile(raw: dict[str, Any]) -> dict[str, Any]:
    profile = deepcopy(raw)
    for section in ("tool_map", "extended_capabilities"):
        mappings = profile.get(section)
        if not isinstance(mappings, dict):
            continue
        for capability, value in list(mappings.items()):
            if isinstance(value, str):
                mappings[capability] = {"tool": value, "kind": "native"}
            elif value is None:
                mappings[capability] = {"tool": None, "kind": "unsupported"}

    hooks = profile.get("hooks")
    if isinstance(hooks, dict):
        overrides = hooks.pop("tool_overrides", {})
        tool_map = profile.get("tool_map", {})
        if isinstance(overrides, dict) and isinstance(tool_map, dict):
            for capability, matcher in overrides.items():
                binding = tool_map.get(capability)
                if isinstance(binding, dict):
                    binding["hook_matchers"] = str(matcher).split("|")
        degradation = hooks.pop("degradation", {})
        if isinstance(degradation, dict):
            policies = hooks.setdefault("policies", {})
            for hook_name, mode in degradation.items():
                if mode == "degraded":
                    policies[hook_name] = {
                        "mode": "degraded",
                        "fallback": {
                            "strategy": "skip",
                            "coverage": "none",
                            "reason": "test fixture fallback",
                        },
                    }
                else:
                    policies[hook_name] = {"mode": mode}
    return profile
