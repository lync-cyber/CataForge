"""Verify deployed IDE artefacts are actually present and reachable.

Hard gate over the per-platform deploy manifests: every path a platform's
last deploy recorded must either be a real file/dir or, if it is a
symlink/junction, must resolve. The manifest is the ownership truth, so
conditionally-produced artefacts (MCP config files) are only required
when a deploy actually wrote them.
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


def _check_owned_path(
    root: Path,
    rel: str,
    missing: list[str],
    dangling: list[tuple[str, str]],
) -> int:
    """Check one owned deploy path; return the number of new failures."""
    p = root / rel
    is_link = p.is_symlink() or (hasattr(p, "is_junction") and p.is_junction())
    if is_link:
        if not p.exists():
            dangling.append((rel, _link_target(p)))
            return 1
        return 0
    if not p.exists():
        missing.append(rel)
        return 1
    return 0


def check_deploy_integrity(cfg: ConfigManager, platforms: list[str] | None = None) -> int:
    """Returns the number of failures contributing to doctor's exit code.

    Skipped (returns 0) when no deploy has ever run — pre-deploy state is
    legitimate and is already reported by the provenance section.
    """
    root = cfg.paths.root
    recorded = deployed_platforms(root)
    if not recorded:
        click.echo("  (no deploy has been run yet — skipping integrity gate)")
        return 0

    scope = [p for p in (platforms or recorded) if p in recorded]
    failures = 0
    for platform_id in scope:
        owned = sorted(load_prior_manifest_for(root, platform_id))
        if not owned:
            click.echo(f"  {platform_id}: (empty manifest — nothing to verify)")
            continue
        missing: list[str] = []
        dangling: list[tuple[str, str]] = []
        for rel in owned:
            failures += _check_owned_path(root, rel, missing, dangling)
        if not missing and not dangling:
            click.echo(f"  {platform_id}: {len(owned)} owned path(s) verified")
            continue
        for rel in missing:
            click.echo(
                f"    FAIL {platform_id}: {rel} missing — "
                f"re-run `cataforge deploy --platform {platform_id}`"
            )
        for rel, link_target in dangling:
            click.echo(
                f"    FAIL {platform_id}: {rel} — broken link to {link_target!r}; "
                f"re-run `cataforge deploy --platform {platform_id}` to relink"
            )
    for platform_id in [p for p in (platforms or []) if p not in recorded]:
        click.echo(f"  {platform_id}: not deployed — skipping")
    return failures


def check_deploy_source_orphans(cfg: ConfigManager) -> int:
    """Warn when the deploy manifest owns a skill whose source was removed.

    A skill recorded under ``<platform>/skills/<name>`` whose source
    ``.cataforge/skills/<name>`` no longer exists is a ghost: the next
    ``cataforge deploy`` prunes it (it is in the prior manifest and absent
    from source). Always non-gating — this is a self-healing artefact, not a
    failure — so it is wired into doctor with ``gating=False``.
    """
    from cataforge.runtime.deploy.manifest import load_prior_manifest

    root = cfg.paths.root
    owned = load_prior_manifest(root)
    if not owned:
        click.echo("  (no deploy manifest — skipping source-orphan scan)")
        return 0

    # The manifest records each deployed skill as ``<dir>/skills/<name>``
    # (e.g. ``.claude/skills/code-review``). Matching the ``skills/<name>``
    # tail keeps this platform-agnostic.
    deployed: dict[str, str] = {}
    for rel in owned:
        parts = rel.split("/")
        if len(parts) >= 2 and parts[-2] == "skills":
            deployed[parts[-1]] = rel
    if not deployed:
        click.echo("  (no skills recorded in deploy manifest)")
        return 0

    try:
        from cataforge.runtime.skill.loader import SkillLoader

        valid_ids = {m.id for m in SkillLoader(project_root=root).discover()}
    except Exception:
        click.echo("  (skill loader unavailable — skipping source-orphan scan)")
        return 0

    ghosts = sorted(name for name in deployed if name not in valid_ids)
    if not ghosts:
        click.echo(f"  {len(deployed)} deployed skill(s) all have sources")
        return 0

    click.echo(
        f"  {len(ghosts)} deployed skill(s) have no source (next `cataforge deploy` self-heals):"
    )
    for name in ghosts:
        click.echo(
            f"    WARN {deployed[name]} — no source skill {name!r}; "
            "re-run `cataforge deploy` to prune"
        )
    return 0


def check_deploy_drift(cfg: ConfigManager, platforms: list[str] | None = None) -> int:
    """Nudge (never gate) when deployed IDE artefacts are stale.

    Compares the current ``.cataforge/`` source digest + installed
    ``cataforge`` version against the baseline each platform's last deploy
    recorded in its own manifest. Drift is a "run ``cataforge deploy``"
    reminder, not a failure, so this always returns 0 and is wired with
    ``gating=False``.
    """
    from cataforge.runtime.deploy.drift import detect_drift, drift_hint_lines

    recorded = deployed_platforms(cfg.paths.root)
    scope = [p for p in (platforms or recorded) if p in recorded]
    if not scope:
        click.echo("  (no deploy baseline yet — skipping drift check)")
        return 0
    for platform_id in scope:
        report = detect_drift(cfg.paths, platform_id=platform_id)
        if not report.deployed:
            click.echo(f"  {platform_id}: (no drift baseline yet)")
            continue
        if not report.any_drift:
            click.echo(f"  {platform_id}: in sync with source + package version")
            continue
        for line in drift_hint_lines(report):
            click.echo(f"    WARN {platform_id}: {line}")
    return 0


def _link_target(p: Path) -> str:
    """Best-effort readlink for a symlink or junction; '?' if unreadable."""
    import os

    try:
        return os.readlink(str(p))
    except (OSError, ValueError):
        return "?"
