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
    GitHubRepo,
    GitWorkTree,
    PolicyChange,
    SyncOutcome,
    find_prunable_branches,
    prune_branches,
    sync_default_branch,
)
from cataforge.core.errors import CataforgeError, ExternalToolError
from cataforge.interface.cli._support.helpers import get_config_manager, resolve_root
from cataforge.interface.cli.main import cli

F = TypeVar("F", bound=Callable[..., object])


def _prune_flags(func: F) -> F:
    """Apply the flags shared by ``git sync`` (when pruning) and ``git prune``."""
    func = click.option(
        "--dry-run",
        "dry_run",
        is_flag=True,
        default=False,
        help="Print the intended deletions without executing them.",
    )(func)
    func = click.option(
        "--yes",
        "auto_yes",
        is_flag=True,
        default=False,
        help="Skip the deletion confirmation prompt.",
    )(func)
    func = click.option(
        "--no-confirm-gh",
        "no_confirm_gh",
        is_flag=True,
        default=False,
        help="Trust the [gone] upstream signal without asking gh for a merged PR.",
    )(func)
    func = click.option(
        "--branch",
        "branch",
        default=None,
        help="Default branch (auto-detected from origin/HEAD when omitted).",
    )(func)
    return func


def _sync_options(func: F) -> F:
    """Apply the shared flag set to both ``git sync`` and the ``sync-main`` alias."""
    func = _prune_flags(func)
    func = click.option(
        "--prune-merged",
        "prune_merged_alias",
        is_flag=True,
        default=False,
        hidden=True,
        help="Deprecated alias for --prune-gone.",
    )(func)
    func = click.option(
        "--prune-gone",
        "prune_gone",
        is_flag=True,
        default=False,
        help="After sync, delete local branches whose upstream is gone (squash-merged).",
    )(func)
    return func


@cli.group("git")
def git_group() -> None:
    """Sync / prune local branches against origin (post-PR hygiene)."""


@git_group.command("sync")
@_sync_options
def git_sync(
    branch: str | None,
    prune_gone: bool,
    prune_merged_alias: bool,
    no_confirm_gh: bool,
    auto_yes: bool,
    dry_run: bool,
) -> None:
    """Fast-forward the local default branch from origin; optionally prune gone branches.

    Refuses anything destructive when the working tree is dirty, the branch
    has diverged, or HEAD is detached — each refusal prints a one-line remedy.
    """
    _run_sync(
        branch=branch,
        prune=prune_gone or prune_merged_alias,
        confirm_via_gh=not no_confirm_gh,
        auto_yes=auto_yes,
        dry_run=dry_run,
    )


@cli.command("sync-main", hidden=True)
@_sync_options
def sync_main_alias(
    branch: str | None,
    prune_gone: bool,
    prune_merged_alias: bool,
    no_confirm_gh: bool,
    auto_yes: bool,
    dry_run: bool,
) -> None:
    """Alias for `cataforge git sync`."""
    _run_sync(
        branch=branch,
        prune=prune_gone or prune_merged_alias,
        confirm_via_gh=not no_confirm_gh,
        auto_yes=auto_yes,
        dry_run=dry_run,
    )


@git_group.command("prune")
@_prune_flags
def git_prune(branch: str | None, no_confirm_gh: bool, auto_yes: bool, dry_run: bool) -> None:
    """Delete local branches whose upstream is gone (squash-merged + head deleted).

    Fetches with --prune first so the [gone] signal is current, then — unless
    --no-confirm-gh — confirms a merged PR via gh before deleting each branch.
    """
    git = _open_worktree(dry_run=dry_run)
    target = branch or git.detect_default_branch()
    _render_prune(git, target, confirm_via_gh=not no_confirm_gh, auto_yes=auto_yes, dry_run=dry_run)
    _emit_planned(git, dry_run=dry_run)


@git_group.command("ensure-policy")
@click.option(
    "--dry-run",
    "dry_run",
    is_flag=True,
    default=False,
    help="Print the intended merge settings without calling gh.",
)
def git_ensure_policy(dry_run: bool) -> None:
    """Make origin's GitHub merge settings match ``git.remote_policy`` (idempotent).

    Sets ``delete_branch_on_merge`` (and, when ``squash_only``, squash-only
    merges) so PR head branches are auto-deleted server-side. A re-run on an
    already-compliant repo issues no PATCH.
    """
    git = _open_worktree(dry_run=dry_run)
    gh = GitHubRepo.from_remote(git)
    if gh is None:
        raise CataforgeError("origin is not a GitHub remote — nothing to configure.")
    if not dry_run and shutil.which("gh") is None:
        raise ExternalToolError(
            "gh not found on PATH — install the GitHub CLI to set merge policy."
        )

    policy = get_config_manager().git_remote_policy
    change = gh.ensure_merge_policy(policy, dry_run=dry_run)
    _render_policy(change)


def _render_policy(change: PolicyChange) -> None:
    if not change.changed:
        click.secho(f"  {change.slug}: merge policy already compliant.", fg="green")
        return
    verb = "DRY-RUN: would set" if change.dry_run else "set"
    click.echo(f"  {verb} merge policy on {change.slug}:")
    for key, value in change.fields.items():
        click.echo(f"    {key}={value}")


def _open_worktree(*, dry_run: bool) -> GitWorkTree:
    if not shutil.which("git"):
        raise ExternalToolError("git not found on PATH.")
    root = resolve_root()
    git = GitWorkTree(root, dry_run=dry_run)
    if not git.is_inside_work_tree():
        raise CataforgeError(f"{root} is not inside a git work-tree — run from a clone.")
    return git


def _run_sync(
    *, branch: str | None, prune: bool, confirm_via_gh: bool, auto_yes: bool, dry_run: bool
) -> None:
    git = _open_worktree(dry_run=dry_run)

    outcome = sync_default_branch(git, branch=branch)
    click.echo(f"Default branch: {outcome.branch}")
    _render_sync(outcome)

    if prune:
        _render_prune(
            git, outcome.branch, confirm_via_gh=confirm_via_gh, auto_yes=auto_yes, dry_run=dry_run
        )
    elif outcome.switched_from and outcome.switched_from != outcome.branch:
        _restore(git, outcome.switched_from)

    _emit_planned(git, dry_run=dry_run)


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


def _render_prune(
    git: GitWorkTree, target: str, *, confirm_via_gh: bool, auto_yes: bool, dry_run: bool
) -> None:
    # Full fetch --prune so every stale remote-tracking ref is gone before
    # detection — a branch-scoped sync fetch only prunes its own refspec.
    git.fetch_prune()
    gh = GitHubRepo.from_remote(git)
    use_gh = confirm_via_gh and gh is not None
    if use_gh and shutil.which("gh") is None:
        click.secho(
            "  gh not on PATH — trusting the [gone] signal without PR verification.", fg="yellow"
        )
        use_gh = False

    verdicts = find_prunable_branches(git, gh, default_branch=target, confirm_via_gh=use_gh)
    deletable = [v.branch for v in verdicts if v.deletable]
    kept_gone = [v for v in verdicts if v.upstream_gone and not v.deletable]

    for v in kept_gone:
        click.secho(
            f"  kept `{v.branch}`: upstream gone but no merged PR found (use --no-confirm-gh "
            "to delete anyway).",
            fg="yellow",
        )

    if not deletable:
        click.echo("  no prunable branches.")
        return

    click.echo("  Branches whose upstream is gone (eligible for deletion):")
    for name in deletable:
        click.echo(f"    - {name}")
    if (
        not dry_run
        and not auto_yes
        and not click.confirm("  Delete these branches?", default=False)
    ):
        click.echo("  skipped.")
        return

    deleted, failed = prune_branches(git, deletable)
    verb = "DRY-RUN: would delete" if dry_run else "deleted"
    for name in deleted:
        click.secho(f"    {verb} {name}", fg="green")
    for name, err in failed:
        click.secho(f"    WARN: could not delete {name}: {err}".rstrip(), fg="yellow", err=True)


def _emit_planned(git: GitWorkTree, *, dry_run: bool) -> None:
    if dry_run and git.planned:
        click.echo("  DRY-RUN — no mutations applied; would run:")
        for argv in git.planned:
            click.echo(f"    {' '.join(argv)}")


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
