"""Platform conformance checks."""

from __future__ import annotations

from pathlib import Path

from cataforge.core.types import (
    AGENT_FRONTMATTER_FIELDS,
    CAPABILITY_IDS,
    EXTENDED_CAPABILITY_IDS,
    OPTIONAL_CAPABILITY_IDS,
    PLATFORM_FEATURES,
)
from cataforge.platform.registry import get_adapter

REQUIRED_CAPABILITIES = CAPABILITY_IDS

ALL_PLATFORMS = ["claude-code", "cursor", "codex", "opencode"]


def check_conformance(platform_id: str, platforms_dir: Path | None = None) -> list[str]:
    """Check a single platform for conformance issues. Returns list of issues."""

    issues: list[str] = []
    try:
        adapter = get_adapter(platform_id, platforms_dir)
    except Exception as e:
        return [f"FAIL: cannot load {platform_id} adapter: {e}"]

    if adapter.platform_id != platform_id:
        issues.append(f"FAIL: platform_id mismatch ({adapter.platform_id} != {platform_id})")

    tool_map = adapter.get_tool_map()
    for cap in REQUIRED_CAPABILITIES:
        if cap not in tool_map or tool_map[cap] is None:
            level = "INFO" if cap in OPTIONAL_CAPABILITY_IDS else "WARN"
            issues.append(f"{level}: {platform_id} does not map capability {cap}")

    if not adapter.dispatch_info:
        issues.append(f"FAIL: {platform_id} missing dispatch config")

    return issues


def check_extended_conformance(
    platform_id: str, platforms_dir: Path | None = None
) -> list[str]:
    """Extended conformance check covering features, agent config, and more.

    Unlike :func:`check_conformance` which checks hard requirements, this
    reports informational coverage gaps for extended capabilities, agent
    configuration fields, platform features, and permission modes.
    """
    issues: list[str] = []
    try:
        adapter = get_adapter(platform_id, platforms_dir)
    except Exception as e:
        return [f"FAIL: cannot load {platform_id} adapter: {e}"]

    # --- extended capabilities ---
    ext_map = adapter.get_extended_tool_map()
    for cap in EXTENDED_CAPABILITY_IDS:
        if cap not in ext_map or ext_map[cap] is None:
            issues.append(f"INFO: {platform_id} does not map extended capability {cap}")

    # --- agent frontmatter fields ---
    supported_fields = adapter.agent_supported_fields
    if supported_fields:
        missing = [f for f in AGENT_FRONTMATTER_FIELDS if f not in supported_fields]
        if missing:
            issues.append(
                f"INFO: {platform_id} agent config missing fields: {', '.join(missing)}"
            )
    else:
        issues.append(f"INFO: {platform_id} does not declare agent_config.supported_fields")

    # --- platform features ---
    features = adapter.get_supported_features()
    if features:
        unsupported = [f for f in PLATFORM_FEATURES if not features.get(f, False)]
        if unsupported:
            issues.append(
                f"INFO: {platform_id} unsupported features: {', '.join(unsupported)}"
            )
    else:
        issues.append(f"INFO: {platform_id} does not declare features section")

    # --- permissions ---
    modes = adapter.permission_modes
    if not modes:
        issues.append(f"INFO: {platform_id} does not declare permission modes")

    # --- model routing ---
    models = adapter.available_models
    if not models:
        issues.append(f"INFO: {platform_id} does not declare available models")

    return issues


def check_all_conformance(platforms_dir: Path | None = None) -> list[str]:
    """Check all known platforms (core conformance)."""
    all_issues: list[str] = []
    for pid in ALL_PLATFORMS:
        issues = check_conformance(pid, platforms_dir)
        if issues:
            all_issues.append(f"\n[{pid}]")
            all_issues.extend(f"  {i}" for i in issues)
    return all_issues


def check_all_extended_conformance(platforms_dir: Path | None = None) -> list[str]:
    """Check all known platforms (extended conformance)."""
    all_issues: list[str] = []
    for pid in ALL_PLATFORMS:
        issues = check_extended_conformance(pid, platforms_dir)
        if issues:
            all_issues.append(f"\n[{pid}]")
            all_issues.extend(f"  {i}" for i in issues)
    return all_issues
