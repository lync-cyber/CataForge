"""cataforge upgrade — framework upgrade management.

CataForge's upgrade model is **package-manager driven**: the Python package
is upgraded via ``pip install --upgrade cataforge`` or ``uv tool upgrade
cataforge``, after which ``cataforge setup --force-scaffold`` refreshes the
in-project ``.cataforge/`` scaffold while preserving user-owned state
(``runtime.platform``, ``upgrade.state``).

There is no in-repo self-upgrade mechanism — that would duplicate and diverge
from the package manager's version resolution. ``cataforge upgrade apply``
simply refreshes the scaffold against the currently-installed package.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from pathlib import Path

import click

from cataforge.application.services.upgrade import (
    find_breaking_entries,
    lift_design_tool_intent,
)
from cataforge.interface.cli.main import cli


@cli.group("upgrade")
def upgrade_group() -> None:
    """Manage framework upgrades.

    The Python package is upgraded via pip/uv; ``apply`` then refreshes
    the in-project scaffold. ``verify`` is an alias for ``doctor``.
    """


@upgrade_group.command("check")
def upgrade_check() -> None:
    """Compare the in-project scaffold version against the installed package."""
    from cataforge.interface.cli.helpers import get_config_manager

    cfg = get_config_manager()
    scaffold_version = cfg.version
    try:
        installed = _pkg_version("cataforge")
    except PackageNotFoundError:
        installed = "unknown"

    click.echo(f"Installed package : {installed}")
    click.echo(f"Scaffold version  : {scaffold_version}")

    if installed == "unknown":
        click.echo(
            "\nCould not detect installed package version. "
            "Run `pip show cataforge` or `uv tool list` to verify."
        )
        return

    from cataforge.interface.cli.guidance import print_next_steps

    if scaffold_version == installed:
        click.echo("\nScaffold is up to date with the installed package.")
        print_next_steps("upgrade-up-to-date")
        return

    click.echo(
        "\nScaffold differs from installed package. Refresh with:\n"
        "  cataforge upgrade apply\n"
        "\nTo upgrade the package itself first:\n"
        "  pip install --upgrade cataforge   # or: uv tool upgrade cataforge"
    )
    print_next_steps("upgrade-checked-stale")

    breaking = find_breaking_entries(scaffold_version, installed)
    if breaking:
        click.secho(
            "\nBREAKING CHANGES between installed package and scaffold:",
            fg="yellow",
            err=True,
        )
        for version_label, summary in breaking:
            click.secho(f"  [{version_label}] {summary}", fg="yellow", err=True)
        click.secho(
            "  Review CHANGELOG.md before running `upgrade apply`.",
            fg="yellow",
            err=True,
        )

    click.echo(
        "\nTip: inside Claude Code / Cursor, the `/framework-update` skill automates "
        "the whole flow (check → confirm → apply → verify)."
    )


@upgrade_group.command("apply")
@click.option("--dry-run", is_flag=True, help="Show what would change without applying.")
def upgrade_apply(dry_run: bool) -> None:
    """Refresh the in-project scaffold against the installed package.

    Equivalent to ``cataforge setup --force-scaffold`` — the package
    itself must be upgraded separately via pip/uv.
    """
    from cataforge.core.scaffold import (
        SIDECAR_SUFFIX,
        classify_scaffold_files,
        copy_scaffold_to,
        format_protected_warning,
    )
    from cataforge.interface.cli.helpers import get_config_manager

    if dry_run:
        from cataforge.core.tallies import classify_tallies

        cfg = get_config_manager()
        dest = cfg.paths.cataforge_dir
        classified = classify_scaffold_files(dest)
        tallies = classify_tallies(classified)

        click.echo(f"Would refresh scaffold at {dest}")
        click.echo(f"  Total files: {len(classified)}")
        parts = [f"{count} {status}" for status, count in sorted(tallies.items())]
        if parts:
            click.echo("  Summary: " + ", ".join(parts))
        click.echo("")
        for rel, status in sorted(classified):
            tag = _status_tag(status)
            click.echo(f"  {tag} {rel}")
        user_modified = tallies.get("user-modified", 0) + tallies.get("drift", 0)
        if user_modified:
            click.echo("")
            click.secho(
                f"  NOTE: {user_modified} file(s) marked user-modified/drift "
                "will be kept; `upgrade apply` writes the framework version "
                f"alongside as *{SIDECAR_SUFFIX} for you to review and merge.",
                fg="yellow",
                err=True,
            )
        click.echo("\nUser-owned state preserved: framework.json(runtime.platform, upgrade.state)")
        return

    # Direct scaffold refresh — avoids the fragile ctx.invoke(setup_command, ...)
    # pattern which was silently sensitive to changes in setup's parameter list.
    cfg = get_config_manager()
    dest = cfg.paths.cataforge_dir
    click.echo(f"Refreshing .cataforge/ at {dest}")
    result = copy_scaffold_to(dest, force=True)
    if result.backup is not None:
        click.echo(f"  backup: {result.backup.relative_to(dest.parent)}")
        click.echo("  (roll back with `cataforge upgrade rollback`)")
    click.echo(
        f"  wrote {len(result.written)} file(s)"
        + (f", kept {len(result.skipped)} existing" if result.skipped else "")
        + (f", pruned {len(result.removed)} obsolete" if result.removed else "")
    )
    for line in format_protected_warning(result.protected, dest):
        click.secho(f"  {line}", fg="yellow", err=True)
    cfg.reload()
    click.echo(f"CataForge v{cfg.version} — scaffold up to date.")

    # A scaffold refresh may have config-flipped a legacy hybrid (or mode-less)
    # project to context.mode=graph. The Markdown survives but the graph store is
    # empty, so seed it from docs/ (ingest → finalize) to avoid a first-read
    # NEVER_EXPORTED drift. Idempotent: a no-op once the graph is populated.
    from cataforge.application.context.seed import seed_graph_from_docs

    seed = seed_graph_from_docs(str(cfg.paths.root))
    if seed.action == "seeded":
        click.echo(f"\n[graph-seed] {seed.detail}")
    elif seed.action == "blocked":
        click.secho(f"\n[graph-seed] {seed.detail}", fg="yellow", err=True)

    # framework.json#project.design_tool is the single source of truth for the
    # design integration; the instruction file's 设计工具 field is now rendered
    # from it and force-overwritten on every deploy. Lift a penpot choice that
    # previously lived only in CLAUDE.md / AGENTS.md so that force-overwrite
    # doesn't silently disable it.
    lifted = lift_design_tool_intent(cfg)
    if lifted:
        click.echo(
            f"\n[design-tool] recorded project.design_tool = {lifted} from the "
            "instruction file (now the single source of truth; run `cataforge deploy` "
            "to re-render)."
        )

    # Refresh docs/.doc-index.json when the project has opted into it.
    # Without this an upgraded scaffold would still load an index built
    # against the previous version's docs, and orphans introduced
    # between releases would only surface at next manual `docs index`
    # invocation.
    from cataforge.domain.docs.indexer import INDEX_FILENAME

    docs_dir = cfg.paths.root / "docs"
    if (docs_dir / INDEX_FILENAME).is_file():
        click.echo(f"\n[docs-index] refreshing docs/{INDEX_FILENAME}")
        from cataforge.domain.docs.indexer import main as indexer_main

        rc = indexer_main(["--project-root", str(cfg.paths.root)])
        if rc != 0:
            click.secho(
                f"  WARN docs index returned {rc} — fix front matter and "
                "rerun `cataforge docs index`.",
                fg="yellow",
                err=True,
            )

    # Platform-rendered artifacts (.claude/settings.json, .cursor/hooks.json,
    # ...) are produced by `cataforge deploy`, not by scaffold refresh. If a
    # deploy has already happened at least once, remind the user to re-run it
    # so the refreshed scaffold actually lands in the IDE-facing directory.
    from cataforge.interface.cli.guidance import print_next_steps

    if cfg.paths.deploy_state.is_file():
        click.echo(
            "\nTip: scaffold refreshed — run `cataforge deploy` to propagate "
            "changes to platform deliverables (e.g. .claude/settings.json)."
        )
        print_next_steps("upgrade-applied")
    else:
        print_next_steps("upgrade-applied")


@upgrade_group.command("verify")
@click.pass_context
def upgrade_verify(ctx: click.Context) -> None:
    """Run migration checks (alias for ``cataforge doctor``)."""
    # Importing the command here keeps module import time low and makes
    # the aliasing explicit. ctx.invoke preserves any parent flags the
    # user passed (e.g. --verbose/--quiet/--project-dir).
    from cataforge.interface.cli.doctor_cmd import doctor_command

    ctx.invoke(doctor_command)


@upgrade_group.command("rollback")
@click.option(
    "--list",
    "list_only",
    is_flag=True,
    help="List available snapshots and exit.",
)
@click.option(
    "--from",
    "from_backup",
    default=None,
    metavar="TS_OR_PATH",
    help="Restore this snapshot (timestamp name or absolute path). Default: the newest snapshot.",
)
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    help="Skip the interactive confirmation prompt.",
)
def upgrade_rollback(
    list_only: bool,
    from_backup: str | None,
    yes: bool,
) -> None:
    """Restore ``.cataforge/`` from a previous ``upgrade apply`` snapshot.

    Every ``upgrade apply`` that found an existing ``.cataforge/`` stashed
    its prior state under ``.cataforge/.backups/<ts>/`` before overwriting.
    ``rollback`` reverses that: current state is first re-stashed into a
    fresh ``.backups/pre-rollback-<ts>/`` (so rollback is itself
    reversible), then the chosen snapshot is restored.
    """
    from cataforge.core.scaffold import list_backups, restore_backup
    from cataforge.interface.cli.helpers import get_config_manager

    cfg = get_config_manager()
    dest = cfg.paths.cataforge_dir
    backups = list_backups(dest)

    if list_only or not backups:
        click.echo(f"Snapshots under {dest}/.backups/:")
        if not backups:
            click.echo("  (none — run `cataforge upgrade apply` first)")
            if not list_only:
                raise click.exceptions.Exit(1)
            return
        for i, b in enumerate(backups):
            marker = " (newest)" if i == 0 else ""
            click.echo(f"  {b.name}{marker}")
        return

    target = _resolve_backup(backups, from_backup)

    if not yes and not click.confirm(
        f"Roll back .cataforge/ to {target.name}?",
        default=False,
    ):
        click.echo("Aborted.")
        raise click.exceptions.Exit(1)

    stash = restore_backup(dest, target)
    click.echo(f"Restored .cataforge/ from {target.name}")
    click.echo(f"  previous state stashed at {stash.relative_to(dest.parent)}")
    cfg.reload()
    click.echo(f"CataForge v{cfg.version} — rollback complete.")


def _resolve_backup(backups: list[Path], selector: str | None) -> Path:
    """Map a ``--from`` value to a concrete backup path."""
    if selector is None:
        return backups[0]

    selector_path = Path(selector)
    if selector_path.is_absolute() and selector_path.is_dir():
        return selector_path

    by_name = {b.name: b for b in backups}
    if selector in by_name:
        return by_name[selector]

    raise click.UsageError(
        f"No snapshot matches {selector!r}. "
        "Run `cataforge upgrade rollback --list` to see available names."
    )


_STATUS_TAGS = {
    "new": "[new]          ",
    "unchanged": "[unchanged]    ",
    "update": "[update]       ",
    "preserved": "[preserved]    ",
    "user-modified": "[user-modified]",
    "drift": "[drift]        ",
}


def _status_tag(status: str) -> str:
    return _STATUS_TAGS.get(status, f"[{status}]")
