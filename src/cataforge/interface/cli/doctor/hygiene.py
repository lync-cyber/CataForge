"""CLAUDE.md hygiene check (size + state-section + Learnings Registry limits)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import click

if TYPE_CHECKING:
    from cataforge.core.config import ConfigManager


def check_claude_md_hygiene(cfg: ConfigManager) -> int:
    """Surface CLAUDE.md size + Learnings Registry overflow as a doctor warning.

    Returns 1 only when at least one configured limit is breached so CI
    treating doctor as a gate notices, but a missing CLAUDE.md (e.g. a
    fresh checkout pre-deploy) is reported informationally, not as a fail.
    """
    from cataforge.core.claude_md_hygiene import measure_claude_md

    claude_md = cfg.paths.root / "CLAUDE.md"
    measurement = measure_claude_md(claude_md)
    if not measurement.exists:
        click.echo(f"  no CLAUDE.md at {claude_md} (run `cataforge deploy`).")
        return 0

    limits = cfg.claude_md_limits
    failed = 0

    click.echo(
        f"  size: {measurement.total_bytes} bytes "
        f"(limit {limits['max_bytes']}); "
        f"§项目状态 lines: {measurement.state_section_lines} "
        f"(limit {limits['max_state_section_lines']}); "
        f"Learnings Registry: {measurement.learnings_entries} "
        f"(limit {limits['learnings_registry_max_entries']})"
    )
    if measurement.total_bytes > limits["max_bytes"]:
        click.secho(
            "  FAIL: CLAUDE.md exceeds claude_md_limits.max_bytes — split user "
            "extensions out of CLAUDE.md or run `cataforge claude-md compact`.",
            fg="red",
        )
        failed += 1
    if measurement.state_section_lines > limits["max_state_section_lines"]:
        click.secho(
            "  FAIL: §项目状态 too long — orchestrator may be writing history "
            "that belongs in EVENT-LOG.",
            fg="red",
        )
        failed += 1
    if measurement.learnings_entries > limits["learnings_registry_max_entries"]:
        click.secho(
            "  FAIL: Learnings Registry over limit — run "
            "`cataforge claude-md compact` to archive the oldest entries.",
            fg="red",
        )
        failed += 1
    bullet_limit = limits["max_state_bullet_chars"]
    if measurement.max_state_bullet_chars > bullet_limit:
        click.secho(
            f"  FAIL: a §项目状态 bullet is {measurement.max_state_bullet_chars} chars "
            f"(limit {bullet_limit}) — a single run-on line accumulating closed-PR / "
            f"debug / backlog history; keep a live delta, move history to docs/ or EVENT-LOG.",
            fg="red",
        )
        failed += 1
    if failed == 0:
        click.echo("  OK")
    return failed
