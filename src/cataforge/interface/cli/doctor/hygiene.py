"""Instruction-file hygiene check (size + state-section + Learnings Registry).

Platform-aware: each scoped platform's profile declares its instruction
file (CLAUDE.md for claude-code, AGENTS.md for cursor/codex/opencode), so
the check measures the file the platform actually reads and the
remediation names the right deploy target.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

import click

if TYPE_CHECKING:
    from cataforge.core.config import ConfigManager


def _instruction_file_name(cfg: ConfigManager, platform_id: str) -> str:
    from cataforge.adapter.platform.registry import get_adapter

    try:
        adapter = get_adapter(platform_id, cfg.paths.platforms_dir)
        targets = adapter.instruction_targets
        if targets:
            return str(targets[0].get("path") or "CLAUDE.md")
    except Exception:  # profile unreadable — fall back to the shared default
        pass
    return "CLAUDE.md" if platform_id == "claude-code" else "AGENTS.md"


def check_claude_md_hygiene(cfg: ConfigManager, platforms: list[str] | None = None) -> int:
    """Surface instruction-file size + Learnings Registry overflow.

    Returns 1 only when at least one configured limit is breached so CI
    treating doctor as a gate notices, but a missing instruction file
    (e.g. a fresh checkout pre-deploy) is reported informationally.
    """
    from cataforge.core.claude_md_hygiene import measure_claude_md

    scope = platforms or [cfg.default_platform]
    seen: set[str] = set()
    failed = 0
    for platform_id in scope:
        name = _instruction_file_name(cfg, platform_id)
        if name in seen:
            continue
        seen.add(name)
        failed += _check_one_instruction_file(cfg, name, platform_id, measure_claude_md)
    return failed


def _check_one_instruction_file(
    cfg: ConfigManager,
    name: str,
    platform_id: str,
    measure: Callable[[Path], Any],
) -> int:
    path = cfg.paths.root / name
    measurement = measure(path)
    if not measurement.exists:
        click.echo(f"  no {name} at {path} (run `cataforge deploy --platform {platform_id}`).")
        return 0

    limits = cfg.claude_md_limits
    failed = 0

    click.echo(
        f"  {name}: size {measurement.total_bytes} bytes "
        f"(limit {limits['max_bytes']}); "
        f"§项目状态 lines: {measurement.state_section_lines} "
        f"(limit {limits['max_state_section_lines']}); "
        f"Learnings Registry: {measurement.learnings_entries} "
        f"(limit {limits['learnings_registry_max_entries']})"
    )
    if measurement.total_bytes > limits["max_bytes"]:
        click.secho(
            f"  FAIL: {name} exceeds claude_md_limits.max_bytes — split user "
            f"extensions out of {name} or run `cataforge claude-md compact`.",
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


def check_project_state_projection(cfg: ConfigManager, platforms: list[str] | None = None) -> int:
    """WARN when instruction-file projections of §项目状态 have drifted.

    The default platform's instruction file is the single source of truth;
    other platforms' files are seeded from it at deploy time and can drift
    if edited independently. Never gates — drift is a reconcile nudge, not
    a failure (run `cataforge deploy` after aligning the primary).
    """
    from cataforge.runtime.deploy.manifest import deployed_platforms

    scope = platforms or deployed_platforms(cfg.paths.root) or [cfg.default_platform]
    primary_name = _instruction_file_name(cfg, cfg.default_platform)
    primary = cfg.paths.root / primary_name
    if not primary.is_file():
        click.echo(f"  (primary instruction file {primary_name} absent — skipped)")
        return 0

    primary_state = _state_section(primary.read_text())
    drifted = 0
    seen = {primary_name}
    for platform_id in scope:
        name = _instruction_file_name(cfg, platform_id)
        if name in seen:
            continue
        seen.add(name)
        path = cfg.paths.root / name
        if not path.is_file():
            continue
        if _state_section(path.read_text()) != primary_state:
            click.echo(
                f"  WARN {name}: §项目状态 differs from {primary_name} "
                f"(the SSOT) — reconcile manually, then redeploy."
            )
            drifted += 1
    if drifted == 0:
        click.echo(f"  §项目状态 projections in sync with {primary_name}")
    return 0


def _state_section(text: str) -> str:
    """The §项目状态 section body (normalised), or '' when absent."""
    import re

    match = re.search(r"(?ms)^## 项目状态.*?$(.*?)(?=^## |\Z)", text)
    return match.group(1).strip() if match else ""
