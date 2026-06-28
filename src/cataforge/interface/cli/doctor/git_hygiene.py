"""Git-hygiene doctor checks.

Advisory only: branch cleanup and downstream line-ending policy are never CI
failures here, so this module always returns 0.
"""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

import click

if TYPE_CHECKING:
    from cataforge.core.config import ConfigManager


def check_git_hygiene(cfg: ConfigManager) -> int:
    """Report stale branches and .gitattributes line-ending hygiene."""
    from cataforge.application.services.git_hygiene import GitWorkTree, inspect_gitattributes

    if shutil.which("git") is None:
        click.echo("  git not on PATH — skipped.")
        return 0

    git = GitWorkTree(cfg.paths.root)
    if not git.is_inside_work_tree():
        click.echo("  not a git work-tree — skipped.")
        return 0

    attr = inspect_gitattributes(cfg.paths.root)
    if attr.ok:
        click.echo("  .gitattributes: OK")
    elif not attr.exists:
        click.echo("  .gitattributes: WARN missing; run `cataforge setup gitattributes`.")
    else:
        missing: list[str] = []
        if not attr.has_text_auto:
            missing.append("text=auto")
        if not attr.has_eol_rule:
            missing.append("eol=")
        click.echo(
            "  .gitattributes: WARN missing "
            + ", ".join(missing)
            + "; preserve custom file and add line-ending rules manually."
        )

    gone = git.gone_branches()
    if not gone:
        click.echo("  branches: OK — no stale local branches.")
        return 0

    click.echo(f"  branches: {len(gone)} local branch(es) with a gone upstream: {', '.join(gone)}")
    click.echo("  remedy: `cataforge git prune` (squash-merged branches git's -d would miss).")
    return 0
