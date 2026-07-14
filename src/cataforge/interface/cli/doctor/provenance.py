"""Deployment provenance — which paths each deployed platform owns.

Manifest-driven: the per-platform deploy manifests are the single source
of truth for ownership, so this report can never disagree with what
deploy actually wrote (a static per-platform path table did, and required
artefacts that are only conditionally produced — e.g. MCP config files).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import click

from cataforge.runtime.deploy.manifest import (
    deployed_platforms,
    load_prior_manifest_for,
)

if TYPE_CHECKING:
    from cataforge.core.config import ConfigManager


def report_deployment_provenance(cfg: ConfigManager, platforms: list[str] | None = None) -> None:
    """Show what each deployed platform owns per its own manifest."""
    root = cfg.paths.root
    recorded = deployed_platforms(root)
    if not recorded:
        click.echo("  (no deploy has been run yet — run `cataforge deploy`)")
        return

    scope = [p for p in (platforms or recorded) if p in recorded]
    skipped = [p for p in (platforms or []) if p not in recorded]
    for platform_id in scope:
        owned = sorted(load_prior_manifest_for(root, platform_id))
        present = sum(1 for rel in owned if (root / rel).exists() or (root / rel).is_symlink())
        click.echo(
            f"  {platform_id}: {present}/{len(owned)} owned path(s) present (CataForge-managed)"
        )
        _note_cursor_mirror(cfg, root, platform_id)
    for platform_id in skipped:
        click.echo(f"  {platform_id}: not deployed")


def _note_cursor_mirror(cfg: ConfigManager, root: Path, platform_id: str) -> None:
    """Flag Cursor mirror state: .claude/rules present even though the mirror
    is off is usually a stale artifact from an older deploy."""
    if platform_id != "cursor":
        return
    mirror = root / ".claude" / "rules"
    if not (mirror.exists() or mirror.is_symlink()):
        return
    if "claude-code" in deployed_platforms(root):
        return  # claude-code legitimately owns .claude/rules here
    if not _read_cursor_mirror_flag(cfg.paths.platform_profile("cursor")):
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
