"""``cataforge git`` — local-branch hygiene against origin.

Thin parse→call→render layer over
:mod:`cataforge.application.services.git_hygiene`; all git mechanics live in
the service so the hook and bootstrap paths share one implementation.
``sync-main`` is kept as a hidden alias for ``git sync``.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from typing import TypeVar

import click

from cataforge.application.services.git_hygiene import (
    GitWorkTree,
    SyncOutcome,
    find_merged_branches,
    prune_branches,
    sync_default_branch,
)
from cataforge.core.errors import CataforgeError, ExternalToolError
from cataforge.interface.cli.helpers import resolve_root
from cataforge.interface.cli.main import cli

F = TypeVar("F", bound=Callable[..., object])


def _sync_options(func: F) -> F:
    """Apply the shared flag set to both ``git sync`` and the ``sync-main`` alias."""
    func = click.option(
        "--dry-run",
        "dry_run",
        is_flag=True,
        default=False,
        help="Print the intended git commands without executing mutations.",
    )(func)
    func = click.option(
        "--yes",
        "auto_yes",
        is_flag=True,
        default=False,
        help="Skip the confirmation prompt for --prune-merged.",
    )(func)
    func = click.option(
        "--prune-merged",
        "prune_merged",
        is_flag=True,
        default=False,
        help="Delete fully-merged local feature branches after sync.",
    )(func)
    func = click.option(
        "--branch",
        "branch",
        default=None,
        help="Default branch to sync (auto-detected from origin/HEAD when omitted).",
    )(func)
    return func


@cli.group("git")
def git_group() -> None:
    """Sync / prune local branches against origin (post-PR hygiene)."""


@git_group.command("sync")
@_sync_options
def git_sync(branch: str | None, prune_merged: bool, auto_yes: bool, dry_run: bool) -> None:
    """Fast-forward the local default branch from origin; optionally prune merged branches.

    Refuses anything destructive when the working tree is dirty, the branch
    has diverged, or HEAD is detached — each refusal prints a one-line remedy.
    """
    _run_sync(branch=branch, prune_merged=prune_merged, auto_yes=auto_yes, dry_run=dry_run)


@cli.command("sync-main", hidden=True)
@_sync_options
def sync_main_alias(branch: str | None, prune_merged: bool, auto_yes: bool, dry_run: bool) -> None:
    """Alias for `cataforge git sync`."""
    _run_sync(branch=branch, prune_merged=prune_merged, auto_yes=auto_yes, dry_run=dry_run)


def _run_sync(*, branch: str | None, prune_merged: bool, auto_yes: bool, dry_run: bool) -> None:
    if not shutil.which("git"):
        raise ExternalToolError("git not found on PATH.")

    root = resolve_root()
    git = GitWorkTree(root, dry_run=dry_run)
    if not git.is_inside_work_tree():
        raise CataforgeError(f"{root} is not inside a git work-tree — run from a clone.")

    outcome = sync_default_branch(git, branch=branch)
    click.echo(f"Default branch: {outcome.branch}")
    _render_sync(outcome)

    if prune_merged:
        _render_prune(git, outcome.branch, auto_yes=auto_yes, dry_run=dry_run)
    elif outcome.switched_from and outcome.switched_from != outcome.branch:
        _restore(git, outcome.switched_from)

    if dry_run and git.planned:
        click.echo("  DRY-RUN — no mutations applied; would run:")
        for argv in git.planned:
            click.echo(f"    {' '.join(argv)}")


def _render_sync(outcome: SyncOutcome) -> None:
    if outcome.switched_from:
        click.secho(f"  switched to {outcome.branch}", fg="green")
    if outcome.action == "up-to-date":
        click.echo(f"  `{outcome.branch}` already up to date.")
    elif outcome.action == "ahead-skip":
        click.secho(
            f"  local `{outcome.branch}` is {outcome.ahead} commit(s) ahead of origin — "
            "skipping fast-forward (push when ready).",
            fg="yellow",
        )
    elif outcome.action == "fast-forwarded":
        click.secho(f"  fast-forwarded {outcome.branch} by {outcome.behind} commit(s)", fg="green")


def _render_prune(git: GitWorkTree, target: str, *, auto_yes: bool, dry_run: bool) -> None:
    candidates = find_merged_branches(git, target)
    if not candidates:
        click.echo("  no merged feature branches to prune.")
        return
    click.echo("  Merged feature branches eligible for deletion:")
    for branch in candidates:
        click.echo(f"    - {branch}")
    if not auto_yes and not click.confirm("  Delete these branches?", default=False):
        click.echo("  skipped.")
        return
    deleted, failed = prune_branches(git, candidates)
    verb = "DRY-RUN: would delete" if dry_run else "deleted"
    for branch in deleted:
        click.secho(f"    {verb} {branch}", fg="green")
    for branch, err in failed:
        click.secho(f"    WARN: could not delete {branch}: {err}".rstrip(), fg="yellow", err=True)


def _restore(git: GitWorkTree, branch: str) -> None:
    try:
        git.switch(branch)
        click.echo(f"  back to {branch}")
    except ExternalToolError:
        click.secho(
            f"  WARN: could not switch back to `{branch}` (maybe it was deleted?). "
            "You're on the default branch.",
            fg="yellow",
        )
