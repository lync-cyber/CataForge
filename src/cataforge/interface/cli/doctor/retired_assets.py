"""Warn when a retired framework skill source dir lingers in a project.

A project carried across many upgrades can keep a removed skill's source under
``.cataforge/skills/<id>/`` (see :mod:`cataforge.core.retired_assets`). The
manifest-scoped prune misses it when the files were untracked or edited, so it
survives and trips other guards. ``cataforge upgrade apply`` removes these
directories; this WARN surfaces any that remain with the one-step fix, and is
wired into doctor with ``gating=False`` so a leftover is a nudge, not a gate.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import click

from cataforge.core.retired_assets import retired_skill_dirs

if TYPE_CHECKING:
    from cataforge.core.config import ConfigManager


def check_retired_skill_assets(cfg: ConfigManager) -> int:
    """Report retired skill source dirs still present. Always non-gating."""
    stale = retired_skill_dirs(cfg.paths.skills_dir)
    if not stale:
        click.echo("  (no retired skill leftovers)")
        return 0

    root = cfg.paths.root
    click.echo(f"  {len(stale)} retired skill leftover(s) found")
    for path in stale:
        try:
            display = path.relative_to(root).as_posix()
        except ValueError:
            display = str(path)
        click.echo(
            f"    WARN {display} — retired framework skill; run `cataforge upgrade apply` to remove"
        )
    return 0
