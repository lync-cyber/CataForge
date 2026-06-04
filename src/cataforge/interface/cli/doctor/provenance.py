"""Deployment provenance — which platform directories CataForge wrote."""

from __future__ import annotations

from pathlib import Path

import click

from cataforge.core.errors import ConfigError
from cataforge.core.io import read_json

# Single source of truth for "what does CataForge own under each platform?"
# Shared with :mod:`deploy_integrity` so the informational report and the
# hard gate cannot drift apart.
_OWNED_DIRS_BY_PLATFORM: dict[str, list[str]] = {
    "claude-code": [
        ".claude/agents",
        ".claude/rules",
        ".claude/skills",
        ".claude/commands",
        ".claude/settings.json",
    ],
    "cursor": [
        ".cursor/agents",
        ".cursor/rules",
        ".cursor/hooks.json",
        ".cursor/mcp.json",
        ".cursor/commands",
    ],
    "codex": [".codex/agents", ".codex/hooks.json", ".codex/config.toml"],
    "opencode": [".opencode/agents", ".opencode/plugins", "opencode.json"],
}


def report_deployment_provenance(cfg) -> None:
    """Show which platform directories were created by the last deploy.

    Reads ``.cataforge/.deploy-state`` (written at the end of each
    ``cataforge deploy``) plus the target platform's profile to compute
    the directory namespace that CataForge owns, then reports which of
    those paths actually exist on disk vs which are user/IDE native.
    """

    deploy_state_path = cfg.paths.cataforge_dir / ".deploy-state"
    if not deploy_state_path.is_file():
        click.echo("  (no deploy has been run yet — run `cataforge deploy`)")
        return

    try:
        state = read_json(deploy_state_path)
    except ConfigError as e:
        click.echo(f"  (could not parse {deploy_state_path}: {e})")
        return

    platform_id = state.get("platform")
    if not platform_id:
        click.echo(f"  (malformed deploy state: {state})")
        return

    click.echo(f"  Last deploy target: {platform_id}")

    # Map platform → directories CataForge *may* own under that platform.
    # See :data:`_OWNED_DIRS_BY_PLATFORM` for the shared definition.
    root = cfg.paths.root
    entries = _OWNED_DIRS_BY_PLATFORM.get(platform_id, [])
    if not entries:
        click.echo(f"  (no provenance map declared for platform {platform_id!r})")
        return

    commands_optional = not (cfg.paths.cataforge_dir / "commands").is_dir()
    for rel in entries:
        p = root / rel
        present = p.exists() or p.is_symlink()
        if rel.endswith("/commands") and commands_optional and not present:
            click.echo(f"  [n/a] {rel}  (no command sources)")
            continue
        marker = "present" if present else "absent"
        click.echo(f"  [{marker}] {rel}  (CataForge-managed)")

    # Flag Cursor mirror state: .claude/rules present even though the mirror
    # is off is usually a stale artifact from an older deploy.
    if platform_id == "cursor":
        mirror = root / ".claude" / "rules"
        if mirror.exists() or mirror.is_symlink():
            profile_path = cfg.paths.platform_profile("cursor")
            mirror_enabled = _read_cursor_mirror_flag(profile_path)
            if not mirror_enabled:
                click.echo(
                    "  NOTE: .claude/rules exists but rules.cross_platform_mirror "
                    "is false — likely a stale artifact from a pre-M5 deploy. "
                    "Safe to delete."
                )


def _read_cursor_mirror_flag(profile_path: Path) -> bool:
    """Best-effort read of ``rules.cross_platform_mirror`` from a YAML profile."""
    if not profile_path.is_file():
        return False
    try:
        import yaml as _yaml

        data = _yaml.safe_load(profile_path.read_text()) or {}
    except Exception:
        return False
    if not isinstance(data, dict):
        return False
    rules = data.get("rules") or {}
    if not isinstance(rules, dict):
        return False
    return bool(rules.get("cross_platform_mirror", False))
