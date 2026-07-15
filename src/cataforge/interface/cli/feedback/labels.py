"""cataforge feedback label management — ensure-labels."""

from __future__ import annotations

import shutil

import click

from cataforge.core.errors import CataforgeError, ExternalToolError
from cataforge.interface.cli._support.helpers import get_config_manager
from cataforge.interface.cli.feedback import feedback_group
from cataforge.utils.run_subprocess import run as run_proc


@feedback_group.command("ensure-labels")
@click.option(
    "--repo",
    "repo",
    default=None,
    help="Target repo (owner/name). Defaults to the upstream from "
    "`framework.json#upgrade.source.repo`.",
)
@click.option(
    "--dry-run",
    "dry_run",
    is_flag=True,
    default=False,
    help="Print what would be created without calling `gh label create`.",
)
def ensure_labels_command(repo: str | None, dry_run: bool) -> None:
    """Create the GitHub labels declared in `framework.json#feedback.gh.labels`
    on the upstream repo, idempotently.

    Use this once when bootstrapping a fork or when adding a new feedback
    label to `framework.json` — it skips labels that already exist.
    Requires `gh` on PATH and push access to the target repo.
    """
    if not shutil.which("gh"):
        raise ExternalToolError(
            "GitHub CLI `gh` not found on PATH. Install from https://cli.github.com/"
        )
    cfg = get_config_manager()
    if repo is None:
        upstream = cfg.upgrade_source
        owner_repo = upstream.get("repo")
        if not owner_repo:
            raise CataforgeError(
                "framework.json#upgrade.source.repo is not configured; "
                "pass --repo owner/name explicitly."
            )
        repo = str(owner_repo)

    # Collect every distinct label declared across feedback kinds.
    labels: set[str] = set()
    for kind in ("bug", "suggest", "correction-export"):
        for lbl in cfg.feedback_gh_labels(kind):
            labels.add(lbl)
    if not labels:
        click.echo("No labels declared in framework.json#feedback.gh.labels.")
        return

    # gh label list returns existing labels — used to skip duplicates so the
    # call is idempotent (gh label create exits 1 on duplicate).
    existing: set[str] = set()
    listing = run_proc(
        ["gh", "label", "list", "-R", repo, "--limit", "100", "--json", "name"],
    )
    if listing.returncode != 0:
        raise ExternalToolError(
            f"gh label list failed (exit {listing.returncode}):\n{listing.stderr or listing.stdout}"
        )
    import json as _json

    for entry in _json.loads(listing.stdout or "[]"):
        existing.add(entry.get("name", ""))

    to_create = sorted(labels - existing)
    already_there = sorted(labels & existing)

    if already_there:
        click.echo(f"Already present on {repo}: {', '.join(already_there)}")
    if not to_create:
        click.echo("Nothing to do — all configured labels exist.")
        return

    click.echo(f"Will create on {repo}: {', '.join(to_create)}")
    if dry_run:
        click.echo("(dry-run; pass without --dry-run to apply)")
        return

    for lbl in to_create:
        result = run_proc(["gh", "label", "create", lbl, "-R", repo])
        if result.returncode == 0:
            click.secho(f"  + {lbl}", fg="green")
        else:
            click.secho(
                f"  ! {lbl} — gh label create failed: {result.stderr or result.stdout}",
                fg="red",
                err=True,
            )
