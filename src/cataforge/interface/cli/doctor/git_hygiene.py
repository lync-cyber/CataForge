"""Git-hygiene doctor check — report stale (squash-merged) local branches.

Advisory only: branch hygiene is never a CI failure, so this always returns 0.
It reuses :meth:`GitWorkTree.gone_branches` and does no network I/O — the count
reflects what the last fetch already knows; the remedy refreshes and prunes.
"""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

import click

if TYPE_CHECKING:
    from cataforge.core.config import ConfigManager


def check_git_hygiene(cfg: ConfigManager) -> int:
    """Report local branches whose upstream is gone; always returns 0."""
    from cataforge.application.services.git_hygiene import GitWorkTree

    if shutil.which("git") is None:
        click.echo("  git not on PATH — skipped.")
        return 0

    git = GitWorkTree(cfg.paths.root)
    if not git.is_inside_work_tree():
        click.echo("  not a git work-tree — skipped.")
        return 0

    gone = git.gone_branches()
    if not gone:
        click.echo("  OK — no stale local branches.")
        return 0

    click.echo(f"  {len(gone)} local branch(es) with a gone upstream: {', '.join(gone)}")
    click.echo("  remedy: `cataforge git prune` (squash-merged branches git's -d would miss).")
    return 0
