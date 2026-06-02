"""Verify deployed IDE artefacts are actually present and reachable.

The provenance report (``provenance.py``) is informational: it lists
present/absent paths but never gated the exit code. That left a class of
silent failures invisible — most notably ``.claude/skills/`` getting
deleted (or pointing through a junction whose source moved away), with
``doctor`` still happily exiting 0.

This module turns the same provenance map into a hard gate: when
``.deploy-state`` records a platform, every owned deploy artefact must
either be a real file/dir or, if it is a symlink/junction, must resolve.
"""

from __future__ import annotations

from pathlib import Path

import click

from cataforge.core.errors import ConfigError
from cataforge.core.io import read_json

from .provenance import _OWNED_DIRS_BY_PLATFORM


def check_deploy_integrity(cfg) -> int:
    """Returns the number of failures contributing to doctor's exit code.

    Skipped (returns 0) when no deploy has ever run — pre-deploy state is
    legitimate and is already reported by the provenance section.
    """
    deploy_state_path = cfg.paths.cataforge_dir / ".deploy-state"
    if not deploy_state_path.is_file():
        click.echo("  (no deploy has been run yet — skipping integrity gate)")
        return 0

    try:
        state = read_json(deploy_state_path)
    except ConfigError:
        # provenance.py already reports the parse failure; don't double-count.
        return 0

    platform_id = state.get("platform")
    owned = _OWNED_DIRS_BY_PLATFORM.get(platform_id, [])
    if not owned:
        click.echo(f"  (no integrity map declared for platform {platform_id!r})")
        return 0

    root = cfg.paths.root
    failures = 0
    missing: list[str] = []
    dangling: list[tuple[str, str]] = []

    for rel in owned:
        p = root / rel
        # ``.exists()`` follows symlinks; ``.lexists()`` does not. A dangling
        # link is the worst case — it looks present in ``ls`` but resolves to
        # nothing — and is the exact failure mode introduced when the source
        # under ``.cataforge/`` is deleted or moved.
        if p.is_symlink() or (hasattr(p, "is_junction") and p.is_junction()):
            if not p.exists():
                dangling.append((rel, _link_target(p)))
                failures += 1
                continue
            # Live link — fall through to per-child checks for skills dir.
        elif not p.exists():
            missing.append(rel)
            failures += 1
            continue

        # Deeper check for ``<platform>/skills/`` (currently only claude-code
        # exposes per-skill subdirs to the IDE): every child must be a real
        # dir or a link that resolves.
        if rel.endswith("/skills") and p.is_dir():
            for child in p.iterdir():
                if child.is_symlink() or (hasattr(child, "is_junction") and child.is_junction()):
                    if not child.exists():
                        dangling.append((f"{rel}/{child.name}", _link_target(child)))
                        failures += 1
                elif not child.exists():
                    missing.append(f"{rel}/{child.name}")
                    failures += 1

    if not failures:
        click.echo(f"  {len(owned)} owned path(s) verified for {platform_id} deploy")
        return 0

    if missing:
        click.echo(f"  {len(missing)} deploy artefact(s) missing:")
        for rel in missing:
            click.echo(f"    FAIL {rel} — re-run `cataforge deploy`")
    if dangling:
        click.echo(
            f"  {len(dangling)} deploy artefact(s) are dangling links (source moved or deleted):"
        )
        for rel, link_target in dangling:
            click.echo(
                f"    FAIL {rel} — broken link to {link_target!r}; "
                "re-run `cataforge deploy` to relink"
            )
    return failures


def check_deploy_source_orphans(cfg) -> int:
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


def _link_target(p: Path) -> str:
    """Best-effort readlink for a symlink or junction; '?' if unreadable."""
    import os

    try:
        return os.readlink(str(p))
    except (OSError, ValueError):
        return "?"
