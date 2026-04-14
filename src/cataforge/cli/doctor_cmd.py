"""cataforge doctor — environment diagnostics."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import click

from cataforge.cli.main import cli


@cli.command("doctor")
def doctor_command() -> None:
    """Run environment diagnostics and report issues."""
    from cataforge.core.config import ConfigManager

    click.echo("CataForge Doctor")
    click.echo("=" * 40)

    cfg = ConfigManager()

    # Python
    click.echo(f"\nPython: {sys.version}")
    click.echo(f"  Executable: {sys.executable}")

    # Framework
    click.echo(f"\nProject root: {cfg.paths.root}")
    _check_file("framework.json", cfg.paths.framework_json)
    _check_file("PROJECT-STATE.md", cfg.paths.project_state_md)
    _check_dir(".cataforge/agents", cfg.paths.agents_dir)
    _check_dir(".cataforge/skills", cfg.paths.skills_dir)
    _check_dir(".cataforge/rules", cfg.paths.rules_dir)
    _check_dir(".cataforge/hooks", cfg.paths.hooks_dir)
    _check_file("hooks.yaml", cfg.paths.hooks_spec)
    _check_dir(".cataforge/platforms", cfg.paths.platforms_dir)

    # Config
    click.echo(f"\nFramework version: {cfg.version}")
    click.echo(f"Runtime platform: {cfg.runtime_platform}")

    # Dependencies
    click.echo("\nDependencies:")
    _check_import("yaml", "PyYAML")
    _check_import("click", "click")

    # External tools
    click.echo("\nExternal tools:")
    for tool in ("ruff", "npx", "docker", "git"):
        path = shutil.which(tool)
        status = f"found ({path})" if path else "not found"
        click.echo(f"  {tool}: {status}")

    # Platform profiles
    click.echo("\nPlatform profiles:")
    for pid in ("claude-code", "cursor", "codex", "opencode"):
        path = cfg.paths.platform_profile(pid)
        status = "OK" if path.is_file() else "MISSING"
        click.echo(f"  {pid}: {status}")

    click.echo("\nDiagnostics complete.")


def _check_file(label: str, path: Path) -> None:
    status = "OK" if path.is_file() else "MISSING"
    click.echo(f"  {label}: {status}")


def _check_dir(label: str, path: Path) -> None:
    status = "OK" if path.is_dir() else "MISSING"
    click.echo(f"  {label}: {status}")


def _check_import(module: str, display: str) -> None:
    try:
        __import__(module)
        click.echo(f"  {display}: OK")
    except ImportError:
        click.echo(f"  {display}: MISSING")
