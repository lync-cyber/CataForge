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

    # Recent hook execution failures — logged by hook_main() so silent
    # observer-hook crashes don't stay invisible.
    click.echo("\nHook execution log:")
    _report_hook_errors(cfg)

    click.echo("\nDiagnostics complete.")

    if failed_count:
        ctx.exit(1)


def _report_hook_errors(cfg) -> None:
    """Surface recent entries from ``.cataforge/.hook-errors.jsonl``.

    We don't fail the doctor run on these — a crashed observer hook is
    degraded functionality, not a broken project — but we do point the user
    at the log so they know it exists.
    """
    import json as _json
    from datetime import datetime, timedelta, timezone

    from cataforge.hook.base import HOOK_ERROR_LOG_REL

    log_path = cfg.paths.root / HOOK_ERROR_LOG_REL
    if not log_path.is_file():
        click.echo("  (no hook errors recorded)")
        return

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    recent: list[dict] = []
    try:
        with open(log_path, encoding="utf-8") as f:
            for raw in f:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    entry = _json.loads(raw)
                except _json.JSONDecodeError:
                    continue
                ts_raw = entry.get("ts")
                try:
                    ts = datetime.fromisoformat(ts_raw)
                except (TypeError, ValueError):
                    continue
                if ts >= cutoff:
                    recent.append(entry)
    except OSError as e:
        click.echo(f"  (could not read {log_path}: {e})")
        return

    if not recent:
        click.echo("  (no hook errors in the last 24h)")
        return

    tail = recent[-5:]
    click.echo(f"  {len(recent)} error(s) in the last 24h (showing last {len(tail)}):")
    for entry in tail:
        mod = entry.get("module", "?")
        fn = entry.get("func", "?")
        err_type = entry.get("error_type", "Error")
        err = entry.get("error", "")
        click.echo(f"  - [{entry.get('ts', '?')}] {mod}.{fn}: {err_type}: {err}")
    click.echo(f"  Full log: {log_path}  (set CATAFORGE_HOOK_DEBUG=1 for tracebacks)")


def _run_migration_checks(cfg) -> int:
    """Run migration checks; return the number of failures.

    Checks marked ``requires_deploy: true`` are SKIPPED (not failed) when the
    project has not yet been deployed — they target deploy-produced artifacts
    like ``.claude/settings.json`` that cannot exist until the first
    ``cataforge deploy`` run.  This lets ``doctor`` stay green for a
    fresh-install flow that hasn't deployed yet, while still catching drift
    once deploy has happened at least once.
    """
    checks = cfg.load().get("migration_checks") or []
    if not checks:
        click.echo("  (none defined)")
        return 0

    deployed = (cfg.paths.cataforge_dir / ".deploy-state").is_file()

    passed = 0
    skipped: list[tuple[str, str]] = []
    failed: list[tuple[str, str]] = []
    for check in checks:
        cid = str(check.get("id", "?"))
        if bool(check.get("requires_deploy", False)) and not deployed:
            skipped.append((cid, "requires deploy (run `cataforge deploy` first)"))
            continue
        ok, reason = _evaluate_check(check, cfg.paths.root)
        if ok:
            passed += 1
        else:
            failed.append((cid, reason))

    parts = [f"{passed}/{len(checks)} passed"]
    if skipped:
        parts.append(f"{len(skipped)} skipped")
    click.echo("  " + ", ".join(parts))
    for cid, reason in skipped:
        click.echo(f"  SKIP {cid}: {reason}")
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
