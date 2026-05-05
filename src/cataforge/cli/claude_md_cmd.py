"""``cataforge claude-md`` — CLAUDE.md hygiene commands.

Two subcommands:

* ``check``  — print size + Learnings Registry entry count, exit 1 if
  any threshold from ``framework.json#claude_md_limits`` is breached.
* ``compact``— trim Learnings Registry to ``learnings_registry_max_entries``
  and archive the surplus to ``.cataforge/learnings/registry-archive.md``.

The matching diagnostic ALSO runs as part of ``cataforge doctor``; this
group exists because the user-facing fix is a separate action and benefits
from its own ``--dry-run`` ergonomics.
"""

from __future__ import annotations

import click

from cataforge.cli.errors import NotInitializedError
from cataforge.cli.helpers import get_config_manager
from cataforge.cli.main import cli
from cataforge.core.claude_md_hygiene import (
    compact_learnings_registry,
    measure_claude_md,
)


@cli.group("claude-md")
def claude_md_group() -> None:
    """CLAUDE.md hygiene: size diagnostics + Learnings Registry compaction."""


@claude_md_group.command("check")
def check_command() -> None:
    """Report CLAUDE.md size + Learnings Registry entry count.

    Exits 1 when any limit from `framework.json#claude_md_limits` is breached
    (so CI can use this as a gate); 0 otherwise.
    """
    cfg = get_config_manager()
    limits = cfg.claude_md_limits

    claude_md = cfg.paths.root / "CLAUDE.md"
    measurement = measure_claude_md(claude_md)
    if not measurement.exists:
        click.echo(f"No CLAUDE.md at {claude_md} (run `cataforge deploy`).")
        return

    failed = 0
    click.echo(f"CLAUDE.md: {measurement.path}")
    click.echo(
        f"  size:               {measurement.total_bytes:>6} bytes "
        f"(limit: {limits['max_bytes']})"
    )
    if measurement.total_bytes > limits["max_bytes"]:
        click.secho(
            "    FAIL: exceeds max_bytes — split user-extensions out or run "
            "`cataforge claude-md compact`.",
            fg="red",
        )
        failed += 1

    click.echo(
        f"  §项目状态 lines:    {measurement.state_section_lines:>6} "
        f"(limit: {limits['max_state_section_lines']})"
    )
    if measurement.state_section_lines > limits["max_state_section_lines"]:
        click.secho(
            "    FAIL: state section is too long — orchestrator may be writing "
            "history that belongs in EVENT-LOG.",
            fg="red",
        )
        failed += 1

    click.echo(
        f"  Learnings Registry: {measurement.learnings_entries:>6} entries "
        f"(limit: {limits['learnings_registry_max_entries']})"
    )
    if (
        measurement.learnings_entries
        > limits["learnings_registry_max_entries"]
    ):
        click.secho(
            "    FAIL: registry exceeds max — run "
            "`cataforge claude-md compact` to archive older entries.",
            fg="red",
        )
        failed += 1

    if failed:
        raise SystemExit(1)
    click.secho("  OK: within limits.", fg="green")


@claude_md_group.command("compact")
@click.option(
    "--max-entries", "max_entries", type=int, default=None,
    help="Override learnings_registry_max_entries from framework.json.",
)
@click.option(
    "--dry-run", "dry_run", is_flag=True, default=False,
    help="Print the compaction plan without modifying files.",
)
def compact_command(max_entries: int | None, dry_run: bool) -> None:
    """Trim CLAUDE.md Learnings Registry; archive the surplus."""
    cfg = get_config_manager()
    limits = cfg.claude_md_limits
    bound = max_entries if max_entries is not None else limits["learnings_registry_max_entries"]

    claude_md = cfg.paths.root / "CLAUDE.md"
    if not claude_md.is_file():
        raise NotInitializedError(cfg.paths.root)
    archive = cfg.paths.root / ".cataforge" / "learnings" / "registry-archive.md"

    measurement = measure_claude_md(claude_md)
    if measurement.learnings_entries <= bound:
        click.echo(
            f"  no compaction needed ({measurement.learnings_entries} ≤ {bound})."
        )
        return

    surplus = measurement.learnings_entries - bound
    click.echo(
        f"  would archive {surplus} oldest entries, keep {bound} newest "
        f"(out of {measurement.learnings_entries} total)."
    )
    if dry_run:
        click.echo("  (dry-run; pass without --dry-run to apply)")
        return

    result = compact_learnings_registry(
        claude_md, archive_path=archive, max_entries=bound
    )
    click.secho(
        f"  archived {result.archived_entries} → {result.archive_path}; "
        f"kept {result.kept_entries} in CLAUDE.md.",
        fg="green",
    )
