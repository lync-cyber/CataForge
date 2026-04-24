"""cataforge upgrade — framework upgrade management.

CataForge's upgrade model is **package-manager driven**: the Python package
is upgraded via ``pip install --upgrade cataforge`` or ``uv tool upgrade
cataforge``, after which ``cataforge setup --force-scaffold`` refreshes the
in-project ``.cataforge/`` scaffold while preserving user-owned state
(``runtime.platform``, ``upgrade.state``, ``PROJECT-STATE.md``).

There is no in-repo self-upgrade mechanism — that would duplicate and diverge
from the package manager's version resolution. ``cataforge upgrade apply``
simply refreshes the scaffold against the currently-installed package.
"""

from __future__ import annotations

import re
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from pathlib import Path

import click

from cataforge.cli.main import cli


@cli.group("upgrade")
def upgrade_group() -> None:
    """Manage framework upgrades.

    The Python package is upgraded via pip/uv; ``apply`` then refreshes
    the in-project scaffold. ``verify`` is an alias for ``doctor``.
    """


@upgrade_group.command("check")
def upgrade_check() -> None:
    """Compare the in-project scaffold version against the installed package."""
    from cataforge.cli.helpers import get_config_manager

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

    if scaffold_version == installed:
        click.echo("\nScaffold is up to date with the installed package.")
        return

    click.echo(
        "\nScaffold differs from installed package. Refresh with:\n"
        "  cataforge upgrade apply\n"
        "\nTo upgrade the package itself first:\n"
        "  pip install --upgrade cataforge   # or: uv tool upgrade cataforge"
    )

    breaking = _find_breaking_entries(scaffold_version, installed)
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
        "\nTip: inside Claude Code / Cursor, the `/self-update` skill automates "
        "the whole flow (check → confirm → apply → verify)."
    )


@upgrade_group.command("apply")
@click.option("--dry-run", is_flag=True, help="Show what would change without applying.")
def upgrade_apply(dry_run: bool) -> None:
    """Refresh the in-project scaffold against the installed package.

    Equivalent to ``cataforge setup --force-scaffold`` — the package
    itself must be upgraded separately via pip/uv.
    """
    from cataforge.cli.helpers import get_config_manager
    from cataforge.core.scaffold import classify_scaffold_files, copy_scaffold_to

    if dry_run:
        cfg = get_config_manager()
        dest = cfg.paths.cataforge_dir
        classified = classify_scaffold_files(dest)
        tallies: dict[str, int] = {}
        for _, status in classified:
            tallies[status] = tallies.get(status, 0) + 1

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
                f"  WARNING: {user_modified} file(s) marked user-modified/drift "
                "will be overwritten by `upgrade apply`. "
                "Back up or commit them before proceeding.",
                fg="yellow",
                err=True,
            )
        click.echo(
            "\nUser-owned state preserved: framework.json(runtime.platform, "
            "upgrade.state), PROJECT-STATE.md"
        )
        return

    # Direct scaffold refresh — avoids the fragile ctx.invoke(setup_command, ...)
    # pattern which was silently sensitive to changes in setup's parameter list.
    cfg = get_config_manager()
    dest = cfg.paths.cataforge_dir
    click.echo(f"Refreshing .cataforge/ at {dest}")
    written, skipped, backup = copy_scaffold_to(dest, force=True)
    if backup is not None:
        click.echo(f"  backup: {backup.relative_to(dest.parent)}")
        click.echo("  (roll back with `cataforge upgrade rollback`)")
    click.echo(
        f"  wrote {len(written)} file(s)"
        + (f", kept {len(skipped)} existing" if skipped else "")
    )
    cfg.reload()
    click.echo(f"CataForge v{cfg.version} — scaffold up to date.")

    # Platform-rendered artifacts (.claude/settings.json, .cursor/hooks.json,
    # ...) are produced by `cataforge deploy`, not by scaffold refresh. If a
    # deploy has already happened at least once, remind the user to re-run it
    # so the refreshed scaffold actually lands in the IDE-facing directory.
    if cfg.paths.deploy_state.is_file():
        click.echo(
            "\nTip: scaffold refreshed — run `cataforge deploy` to propagate "
            "changes to platform deliverables (e.g. .claude/settings.json)."
        )


@upgrade_group.command("verify")
@click.pass_context
def upgrade_verify(ctx: click.Context) -> None:
    """Run migration checks (alias for ``cataforge doctor``)."""
    # Importing the command here keeps module import time low and makes
    # the aliasing explicit. ctx.invoke preserves any parent flags the
    # user passed (e.g. --verbose/--quiet/--project-dir).
    from cataforge.cli.doctor_cmd import doctor_command

    ctx.invoke(doctor_command)


@upgrade_group.command("rollback")
@click.option(
    "--list", "list_only",
    is_flag=True,
    help="List available snapshots and exit.",
)
@click.option(
    "--from", "from_backup",
    default=None,
    metavar="TS_OR_PATH",
    help="Restore this snapshot (timestamp name or absolute path). "
         "Default: the newest snapshot.",
)
@click.option(
    "--yes", "-y",
    is_flag=True,
    help="Skip the interactive confirmation prompt.",
)
def upgrade_rollback(
    list_only: bool, from_backup: str | None, yes: bool,
) -> None:
    """Restore ``.cataforge/`` from a previous ``upgrade apply`` snapshot.

    Every ``upgrade apply`` that found an existing ``.cataforge/`` stashed
    its prior state under ``.cataforge/.backups/<ts>/`` before overwriting.
    ``rollback`` reverses that: current state is first re-stashed into a
    fresh ``.backups/pre-rollback-<ts>/`` (so rollback is itself
    reversible), then the chosen snapshot is restored.
    """
    from cataforge.cli.helpers import get_config_manager
    from cataforge.core.scaffold import list_backups, restore_backup

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


_CHANGELOG_HEADER_RE = re.compile(r"^## \[(?P<version>[^\]]+)\]")
_BREAKING_HEADER_RE = re.compile(r"^#{2,4}\s*(?:BREAKING|breaking)(?:\s|$)")


def _find_breaking_entries(
    scaffold_version: str, installed_version: str,
) -> list[tuple[str, str]]:
    """Scan CHANGELOG.md for BREAKING sections in the upgrade range.

    Returns ``(version, first_bullet)`` tuples for every section whose
    version sits between the scaffold's current state and the installed
    package, when that section contains a ``### BREAKING`` subheader.

    Silent on missing CHANGELOG or a malformed range — the check is a
    courtesy warning, not a correctness gate.
    """
    changelog = _find_changelog()
    if changelog is None:
        return []

    sections = _iter_changelog_sections(changelog.read_text(encoding="utf-8"))
    out: list[tuple[str, str]] = []
    for version, body in sections:
        if not _is_in_upgrade_range(version, scaffold_version, installed_version):
            continue
        summary = _extract_breaking_summary(body)
        if summary is not None:
            out.append((version, summary))
    return out


def _find_changelog() -> Path | None:
    """Walk up from cwd for a CHANGELOG.md (project root is where it lives)."""
    here = Path.cwd().resolve()
    for parent in (here, *here.parents):
        candidate = parent / "CHANGELOG.md"
        if candidate.is_file():
            return candidate
    return None


def _iter_changelog_sections(text: str) -> list[tuple[str, str]]:
    """Return ``(version, body)`` for every ``## [x.y.z]`` section."""
    sections: list[tuple[str, str]] = []
    current_version: str | None = None
    current_body: list[str] = []
    for line in text.splitlines():
        header = _CHANGELOG_HEADER_RE.match(line)
        if header is not None:
            if current_version is not None:
                sections.append((current_version, "\n".join(current_body)))
            current_version = header.group("version")
            current_body = []
        elif current_version is not None:
            current_body.append(line)
    if current_version is not None:
        sections.append((current_version, "\n".join(current_body)))
    return sections


def _parse_semver(version: str) -> tuple[int, int, int] | None:
    """Best-effort semver tuple; returns None for non-numeric versions."""
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)", version)
    if m is None:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def _is_in_upgrade_range(version: str, lower: str, upper: str) -> bool:
    """True iff *lower < version <= upper* on semver ordering."""
    vv = _parse_semver(version)
    lo = _parse_semver(lower)
    hi = _parse_semver(upper)
    if vv is None or lo is None or hi is None:
        return False
    return lo < vv <= hi


def _extract_breaking_summary(body: str) -> str | None:
    """Return the first non-blank line under a BREAKING subheader, or None."""
    lines = body.splitlines()
    for i, line in enumerate(lines):
        if _BREAKING_HEADER_RE.match(line):
            for follow in lines[i + 1:]:
                stripped = follow.strip().lstrip("-*").strip()
                if stripped:
                    return stripped
            return "(BREAKING section present; see CHANGELOG.md)"
    return None


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
