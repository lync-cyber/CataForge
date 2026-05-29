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

import json
from pathlib import Path

import click

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
        state = json.loads(deploy_state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        # provenance.py already reports the parse failure; don't double-count.
        return 0

    platform_id = state.get("platform")
    owned = _OWNED_DIRS_BY_PLATFORM.get(platform_id, [])
    if not owned:
        click.echo(
            f"  (no integrity map declared for platform {platform_id!r})"
        )
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
                if child.is_symlink() or (
                    hasattr(child, "is_junction") and child.is_junction()
                ):
                    if not child.exists():
                        dangling.append(
                            (f"{rel}/{child.name}", _link_target(child))
                        )
                        failures += 1
                elif not child.exists():
                    missing.append(f"{rel}/{child.name}")
                    failures += 1

    if not failures:
        click.echo(
            f"  {len(owned)} owned path(s) verified for {platform_id} deploy"
        )
        return 0

    if missing:
        click.echo(f"  {len(missing)} deploy artefact(s) missing:")
        for rel in missing:
            click.echo(f"    FAIL {rel} — re-run `cataforge deploy`")
    if dangling:
        click.echo(
            f"  {len(dangling)} deploy artefact(s) are dangling links "
            "(source moved or deleted):"
        )
        for rel, link_target in dangling:
            click.echo(
                f"    FAIL {rel} — broken link to {link_target!r}; "
                "re-run `cataforge deploy` to relink"
            )
    return failures


def _link_target(p: Path) -> str:
    """Best-effort readlink for a symlink or junction; '?' if unreadable."""
    import os

    try:
        return os.readlink(str(p))
    except (OSError, ValueError):
        return "?"
