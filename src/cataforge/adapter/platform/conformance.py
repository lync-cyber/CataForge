"""Platform conformance checks."""

from __future__ import annotations

from pathlib import Path

from cataforge.adapter.platform.registry import BUILTIN_PLATFORM_IDS, get_adapter
from cataforge.core.types import (
    AGENT_FRONTMATTER_FIELDS,
    CAPABILITY_IDS,
    EXTENDED_CAPABILITY_IDS,
    OPTIONAL_CAPABILITY_IDS,
    PLATFORM_FEATURES,
)

REQUIRED_CAPABILITIES = CAPABILITY_IDS

ALL_PLATFORMS = list(BUILTIN_PLATFORM_IDS)


def check_conformance(platform_id: str, platforms_dir: Path | None = None) -> list[str]:
    """Check a single platform for conformance issues. Returns list of issues."""

    issues: list[str] = []
    try:
        adapter = get_adapter(platform_id, platforms_dir)
    except Exception as e:
        return [f"FAIL: cannot load {platform_id} adapter: {e}"]

    if adapter.platform_id != platform_id:
        issues.append(f"FAIL: platform_id mismatch ({adapter.platform_id} != {platform_id})")

    for cap in REQUIRED_CAPABILITIES:
        resolution = adapter.resolve_capability(cap)
        if resolution.status == "unsupported":
            level = "INFO" if cap in OPTIONAL_CAPABILITY_IDS else "WARN"
            issues.append(f"{level}: {platform_id} does not map capability {cap}")
        elif resolution.status == "conditional":
            issues.append(
                f"INFO: {platform_id} capability {cap} is conditional: {resolution.reason}"
            )
        elif resolution.status == "replacement":
            issues.append(
                f"INFO: {platform_id} capability {cap} uses replacement tool {resolution.tool!r}"
            )

    if not adapter.dispatch_info:
        issues.append(f"FAIL: {platform_id} missing dispatch config")

    return issues


def check_extended_conformance(platform_id: str, platforms_dir: Path | None = None) -> list[str]:
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
    for cap in EXTENDED_CAPABILITY_IDS:
        if adapter.resolve_capability(cap).status == "unsupported":
            issues.append(f"INFO: {platform_id} does not map extended capability {cap}")

    # --- agent frontmatter fields ---
    supported_fields = adapter.agent_supported_fields
    if supported_fields:
        missing = [f for f in AGENT_FRONTMATTER_FIELDS if f not in supported_fields]
        if missing:
            issues.append(f"INFO: {platform_id} agent config missing fields: {', '.join(missing)}")
    else:
        issues.append(f"INFO: {platform_id} does not declare agent_config.supported_fields")

    # --- platform features ---
    features = adapter.get_supported_features()
    if features:
        unsupported = [f for f in PLATFORM_FEATURES if not features.get(f, False)]
        if unsupported:
            issues.append(f"INFO: {platform_id} unsupported features: {', '.join(unsupported)}")
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


def check_platform_consistency(platform_id: str, platforms_dir: Path | None = None) -> list[str]:
    """WARN-level cross-field consistency checks within one profile.

    Where :func:`check_extended_conformance` reports INFO coverage gaps, these
    surface contradictions a profile can declare against itself: a capability
    routed to a substitute tool, or a feature flag whose activation surface the
    routing layer cannot see. Cross-platform contradictions (a lone ``native``
    claim) live in :func:`check_hook_native_outliers`.
    """
    issues: list[str] = []
    try:
        adapter = get_adapter(platform_id, platforms_dir)
    except Exception as e:
        return [f"FAIL: cannot load {platform_id} adapter: {e}"]

    web_fetch = adapter.get_capability_binding("web_fetch")
    if web_fetch is not None and web_fetch.kind == "replacement":
        issues.append(
            f"WARN: {platform_id} routes web_fetch to replacement tool {web_fetch.tool!r} — "
            "a tool replacement, not native fetch semantics (no success/failure signal; "
            "blocked under read_only sandbox)"
        )

    browser_preview = adapter.resolve_capability("browser_preview")
    if adapter.supports_feature("computer_use") and browser_preview.available is False:
        issues.append(
            f"WARN: {platform_id} declares feature computer_use but extended capability "
            "browser_preview is unmapped — the capability is invisible to the routing layer"
        )

    if adapter.supports_feature("worktree_isolation") and (
        "isolation" not in adapter.agent_supported_fields
    ):
        issues.append(
            f"WARN: {platform_id} declares feature worktree_isolation but "
            "agent_config.supported_fields lacks 'isolation' — the field is dropped at "
            "deploy and cannot activate the feature"
        )

    scan_dirs = adapter.get_agent_scan_dirs()
    if scan_dirs and len(Path(scan_dirs[0]).parent.parts) != 1:
        issues.append(
            f"WARN: {platform_id} agent scan dir {scan_dirs[0]!r} is not a "
            "<platform>/agents path — deploy_rules derives the rules target from its "
            "parent and would write rules to an unexpected location"
        )

    profile_root = (
        Path(platforms_dir) / platform_id
        if platforms_dir is not None
        else Path(__file__).resolve().parents[4] / ".cataforge" / "platforms" / platform_id
    )
    for hook_name, policy in adapter.hook_policies.items():
        fallback = policy.fallback
        if fallback is None or fallback.asset is None:
            continue
        if not (profile_root / fallback.asset).is_file():
            issues.append(
                f"FAIL: {platform_id} hook {hook_name!r} fallback asset is missing: "
                f"{fallback.asset}"
            )

    return issues


def check_all_consistency(platforms_dir: Path | None = None) -> list[str]:
    """All WARN-level platform consistency checks (per-platform + cross-platform)."""
    all_issues: list[str] = []
    for pid in ALL_PLATFORMS:
        issues = check_platform_consistency(pid, platforms_dir)
        if issues:
            all_issues.append(f"\n[{pid}]")
            all_issues.extend(f"  {i}" for i in issues)
    return all_issues
