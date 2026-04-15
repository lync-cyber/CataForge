"""cataforge doctor — environment diagnostics."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import click

from cataforge.cli.main import cli


@cli.command("doctor")
@click.pass_context
def doctor_command(ctx: click.Context) -> None:
    """Run environment diagnostics and report issues.

    Exits with a non-zero status when any migration_check fails, so CI can
    treat doctor as a gate.
    """
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

    # Framework migration checks — defined in framework.json, verified here so
    # scaffold/repo drift surfaces automatically instead of only at upgrade time.
    click.echo("\nFramework migration checks:")
    failed_count = _run_migration_checks(cfg)

    click.echo("\nDiagnostics complete.")

    if failed_count:
        ctx.exit(1)


def _run_migration_checks(cfg) -> int:
    """Run migration checks; return the number of failures."""
    checks = cfg.load().get("migration_checks") or []
    if not checks:
        click.echo("  (none defined)")
        return 0

    passed = 0
    failed: list[tuple[str, str]] = []
    for check in checks:
        cid = str(check.get("id", "?"))
        ok, reason = _evaluate_check(check, cfg.paths.root)
        if ok:
            passed += 1
        else:
            failed.append((cid, reason))

    click.echo(f"  {passed}/{len(checks)} passed")
    for cid, reason in failed:
        click.echo(f"  FAIL {cid}: {reason}")
    return len(failed)


def _evaluate_check(check: dict, root: Path) -> tuple[bool, str]:
    """Evaluate a single migration_check entry.  Returns (ok, reason)."""
    ctype = str(check.get("type", ""))
    rel = str(check.get("path", ""))
    target = root / rel
    patterns = list(check.get("patterns") or [])

    if ctype == "file_must_exist":
        return (target.is_file(), "" if target.is_file() else f"{rel} does not exist")

    if ctype == "file_must_contain":
        if not target.is_file():
            return False, f"{rel} does not exist"
        try:
            text = target.read_text(encoding="utf-8")
        except OSError as e:
            return False, f"cannot read {rel}: {e}"
        missing = [p for p in patterns if p not in text]
        if missing:
            return False, f"{rel} missing patterns: {missing}"
        return True, ""

    if ctype == "file_must_not_contain":
        if not target.is_file():
            # A non-existent file trivially satisfies "must not contain".
            return True, ""
        try:
            text = target.read_text(encoding="utf-8")
        except OSError as e:
            return False, f"cannot read {rel}: {e}"
        present = [p for p in patterns if p in text]
        if present:
            return False, f"{rel} contains forbidden patterns: {present}"
        return True, ""

    if ctype == "dir_must_contain_files":
        if not target.is_dir():
            return False, f"{rel} is not a directory"
        missing = [p for p in patterns if not (target / p).is_file()]
        if missing:
            return False, f"{rel} missing files: {missing}"
        return True, ""

    return False, f"unknown check type: {ctype}"


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
