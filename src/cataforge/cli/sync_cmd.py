"""``cataforge sync-main`` — bring the local default branch up to date with origin.

Solves a frequent dogfood pain: after a feature-branch PR squash-merges to
``main``, the local ``main`` keeps drifting until the user remembers to
``git fetch && git switch main && git pull``. Forgetting it leads to
"`git checkout -b feature/...` from stale main" and a noisy rebase later.

Default behaviour (no destructive action without explicit opt-in):

1. Verify ``git`` is on PATH and the cwd is inside a git work-tree.
2. ``git fetch origin <main> --prune`` (default branch auto-detected; falls
   back to ``main`` then ``master``).
3. Switch to that branch (rejecting if the working tree has uncommitted
   changes — never overwrite local edits).
4. Fast-forward to ``origin/<main>`` only — refuses to do a merge commit if
   local has diverged. Diverged branches surface a clear message instead.
5. Optionally delete fully-merged local feature branches with
   ``--prune-merged`` (interactive confirmation unless ``--yes``).

This command is intentionally narrow: no rebase, no force-push, no stash.
Anything outside the happy path bails out with an actionable message.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import click

from cataforge.cli.errors import CataforgeError, ExternalToolError
from cataforge.cli.helpers import resolve_root
from cataforge.cli.main import cli


def _git(args: list[str], *, cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run a git subprocess, returning the CompletedProcess."""
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=check,
        encoding="utf-8",
    )


def _detect_default_branch(repo: Path) -> str:
    """Resolve the configured default branch.

    Order of attempts:

    1. ``git symbolic-ref refs/remotes/origin/HEAD`` — what ``origin`` advertises.
    2. ``git config init.defaultBranch`` — local fallback.
    3. ``main`` if ``refs/heads/main`` exists, else ``master``.
    """
    try:
        result = _git(
            ["symbolic-ref", "--short", "refs/remotes/origin/HEAD"],
            cwd=repo,
            check=True,
        )
        ref = (result.stdout or "").strip()
        if ref.startswith("origin/"):
            return ref[len("origin/"):]
    except subprocess.CalledProcessError:
        pass

    try:
        result = _git(
            ["config", "--get", "init.defaultBranch"],
            cwd=repo,
            check=True,
        )
        configured = (result.stdout or "").strip()
        if configured:
            return configured
    except subprocess.CalledProcessError:
        pass

    for candidate in ("main", "master"):
        try:
            _git(
                ["show-ref", "--verify", f"refs/heads/{candidate}"],
                cwd=repo,
                check=True,
            )
            return candidate
        except subprocess.CalledProcessError:
            continue

    raise CataforgeError(
        "Could not detect a default branch. Pass --branch explicitly or set "
        "`git remote set-head origin --auto` so origin/HEAD points somewhere."
    )


def _is_working_tree_clean(repo: Path) -> bool:
    """True iff `git status --porcelain` is empty (no staged / unstaged / untracked)."""
    result = _git(["status", "--porcelain"], cwd=repo, check=True)
    return not (result.stdout or "").strip()


def _current_branch(repo: Path) -> str:
    result = _git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=repo, check=True)
    return (result.stdout or "").strip()


def _local_branches(repo: Path) -> list[str]:
    result = _git(
        ["for-each-ref", "--format=%(refname:short)", "refs/heads/"],
        cwd=repo,
        check=True,
    )
    return [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]


def _merged_into(repo: Path, branch: str) -> set[str]:
    """Return local branches that have been fully merged into ``branch``."""
    result = _git(["branch", "--merged", branch], cwd=repo, check=True)
    out: set[str] = set()
    for line in (result.stdout or "").splitlines():
        name = line.strip().lstrip("*").strip()
        if name and not name.startswith("("):
            out.add(name)
    return out


@cli.command("sync-main")
@click.option(
    "--branch", "branch", default=None,
    help="Default branch to sync (auto-detected from origin/HEAD when omitted).",
)
@click.option(
    "--prune-merged", "prune_merged", is_flag=True, default=False,
    help="Delete fully-merged local feature branches after sync.",
)
@click.option(
    "--yes", "auto_yes", is_flag=True, default=False,
    help="Skip the confirmation prompt for --prune-merged.",
)
@click.option(
    "--dry-run", "dry_run", is_flag=True, default=False,
    help="Print the git commands and decisions without executing destructive ones.",
)
def sync_main_command(
    branch: str | None,
    prune_merged: bool,
    auto_yes: bool,
    dry_run: bool,
) -> None:
    """Fast-forward the local default branch from `origin` and (optionally)
    prune fully-merged feature branches.

    Refuses to do anything destructive when the working tree has uncommitted
    changes, when the branch has diverged from `origin`, or when running on
    a detached HEAD. Each refusal prints a one-line remedy.
    """
    if not shutil.which("git"):
        raise ExternalToolError("git not found on PATH.")

    repo = resolve_root()
    # Confirm we're inside a work-tree (resolve_root finds the project root,
    # which may be a parent without a .git/ when running in a checked-out
    # tarball — git rev-parse fails fast in that case).
    try:
        _git(["rev-parse", "--is-inside-work-tree"], cwd=repo, check=True)
    except subprocess.CalledProcessError as e:
        raise CataforgeError(
            f"{repo} is not inside a git work-tree:\n  {e.stderr or e.stdout}"
        ) from None

    target = branch or _detect_default_branch(repo)
    click.echo(f"Default branch: {target}")

    starting_branch = _current_branch(repo)
    if starting_branch == "HEAD":
        raise CataforgeError(
            "Detached HEAD — checkout a branch first, then re-run `cataforge sync-main`."
        )

    # Fetch + prune
    fetch_args = ["fetch", "origin", target, "--prune"]
    if dry_run:
        click.echo(f"  DRY-RUN: git {' '.join(fetch_args)}")
    else:
        try:
            _git(fetch_args, cwd=repo, check=True)
            click.secho(f"  fetched origin/{target}", fg="green")
        except subprocess.CalledProcessError as e:
            raise ExternalToolError(
                f"git fetch failed:\n  {e.stderr or e.stdout}"
            ) from None

    # Switch to target if needed
    if starting_branch != target:
        if not _is_working_tree_clean(repo):
            raise CataforgeError(
                f"Working tree on `{starting_branch}` has uncommitted changes — "
                f"commit or stash before running `cataforge sync-main`."
            )
        if dry_run:
            click.echo(f"  DRY-RUN: git switch {target}")
        else:
            try:
                _git(["switch", target], cwd=repo, check=True)
                click.secho(f"  switched to {target}", fg="green")
            except subprocess.CalledProcessError as e:
                raise ExternalToolError(
                    f"git switch {target} failed:\n  {e.stderr or e.stdout}"
                ) from None

    # Compare local target vs origin/target
    try:
        ahead_behind = _git(
            ["rev-list", "--left-right", "--count", f"{target}...origin/{target}"],
            cwd=repo,
            check=True,
        )
        ahead_str, behind_str = (ahead_behind.stdout or "0\t0").strip().split()
        ahead, behind = int(ahead_str), int(behind_str)
    except (subprocess.CalledProcessError, ValueError) as e:
        raise ExternalToolError(
            f"could not compare {target} vs origin/{target}: {e}"
        ) from None

    if ahead and behind:
        raise CataforgeError(
            f"`{target}` and `origin/{target}` have diverged "
            f"({ahead} ahead, {behind} behind). `cataforge sync-main` only does "
            "fast-forwards — resolve manually with `git pull --rebase` or "
            "`git reset --hard origin/{target}` (destructive)."
        )
    if ahead and not behind:
        click.secho(
            f"  local `{target}` is {ahead} commit(s) ahead of origin — "
            "skipping fast-forward (push when ready).",
            fg="yellow",
        )
    elif behind:
        ff_args = ["merge", "--ff-only", f"origin/{target}"]
        if dry_run:
            click.echo(f"  DRY-RUN: git {' '.join(ff_args)}")
        else:
            try:
                _git(ff_args, cwd=repo, check=True)
                click.secho(
                    f"  fast-forwarded {target} by {behind} commit(s)", fg="green"
                )
            except subprocess.CalledProcessError as e:
                raise ExternalToolError(
                    f"git merge --ff-only failed:\n  {e.stderr or e.stdout}"
                ) from None
    else:
        click.echo(f"  `{target}` already up to date.")

    if prune_merged:
        _prune_merged_branches(repo, target=target, auto_yes=auto_yes, dry_run=dry_run)

    # Restore the original branch when the user was on something else *and*
    # they didn't ask us to nuke it via --prune-merged.
    if starting_branch != target and not prune_merged:
        if dry_run:
            click.echo(f"  DRY-RUN: git switch {starting_branch}")
        else:
            try:
                _git(["switch", starting_branch], cwd=repo, check=True)
                click.echo(f"  back to {starting_branch}")
            except subprocess.CalledProcessError:
                # Non-fatal — user is on `target` now, which is fine.
                click.secho(
                    f"  WARN: could not switch back to `{starting_branch}` "
                    "(maybe it was deleted?). You're on the default branch.",
                    fg="yellow",
                )


def _prune_merged_branches(
    repo: Path, *, target: str, auto_yes: bool, dry_run: bool
) -> None:
    """Delete every local branch that's fully merged into ``target``."""
    locals_ = _local_branches(repo)
    merged = _merged_into(repo, target)
    candidates = sorted(
        b for b in locals_ if b in merged and b != target and b != "HEAD"
    )
    if not candidates:
        click.echo("  no merged feature branches to prune.")
        return
    click.echo("  Merged feature branches eligible for deletion:")
    for b in candidates:
        click.echo(f"    - {b}")
    if not auto_yes and not click.confirm(
        "  Delete these branches?", default=False
    ):
        click.echo("  skipped.")
        return
    for b in candidates:
        if dry_run:
            click.echo(f"    DRY-RUN: git branch -d {b}")
            continue
        try:
            _git(["branch", "-d", b], cwd=repo, check=True)
            click.secho(f"    deleted {b}", fg="green")
        except subprocess.CalledProcessError as e:
            click.secho(
                f"    WARN: could not delete {b}: {e.stderr or e.stdout}".rstrip(),
                fg="yellow",
                err=True,
            )
