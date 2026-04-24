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
    from cataforge.cli.helpers import get_config_manager

    click.echo("CataForge Doctor")
    click.echo("=" * 40)

    cfg = get_config_manager()

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

    # Protocol script references — markdown/YAML files inside .cataforge/
    # routinely invoke ``python .cataforge/scripts/...`` commands. If one of
    # those scripts is missing, every call site silently fails at runtime
    # (each orchestrator [EVENT] line, every TDD phase transition, the
    # agent_dispatch hook, ...), with no signal until someone reads the
    # hook error log. Scanning statically catches the rot at diagnostic time.
    click.echo("\nProtocol script references:")
    failed_count += _check_protocol_script_references(cfg)

    # Deployment provenance — shows which platform-specific directories would
    # have been written by the last successful deploy. Lets users see at a
    # glance which ``.claude/`` / ``.cursor/`` / etc. are CataForge-managed
    # vs user/IDE-native, which was confusing in the Cursor verification.
    click.echo("\nDeployment provenance:")
    _report_deployment_provenance(cfg)

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


def _report_deployment_provenance(cfg) -> None:
    """Show which platform directories were created by the last deploy.

    Reads ``.cataforge/.deploy-state`` (written at the end of each
    ``cataforge deploy``) plus the target platform's profile to compute
    the directory namespace that CataForge owns, then reports which of
    those paths actually exist on disk vs which are user/IDE native.
    """
    import json as _json

    deploy_state_path = cfg.paths.cataforge_dir / ".deploy-state"
    if not deploy_state_path.is_file():
        click.echo("  (no deploy has been run yet — run `cataforge deploy`)")
        return

    try:
        state = _json.loads(deploy_state_path.read_text(encoding="utf-8"))
    except (OSError, _json.JSONDecodeError) as e:
        click.echo(f"  (could not parse {deploy_state_path}: {e})")
        return

    platform_id = state.get("platform")
    if not platform_id:
        click.echo(f"  (malformed deploy state: {state})")
        return

    click.echo(f"  Last deploy target: {platform_id}")

    # Map platform → directories CataForge *may* own under that platform.
    # We err on the side of listing a stable, well-known subset rather than
    # introspecting every adapter (which would require instantiation).
    owned: dict[str, list[str]] = {
        "claude-code": [".claude/agents", ".claude/rules", ".claude/skills",
                        ".claude/commands", ".claude/settings.json"],
        "cursor": [".cursor/agents", ".cursor/rules", ".cursor/hooks.json",
                   ".cursor/mcp.json", ".cursor/commands"],
        "codex": [".codex/agents", ".codex/hooks.json", ".codex/config.toml"],
        "opencode": [".opencode/agents", ".opencode/plugins", "opencode.json"],
    }

    root = cfg.paths.root
    entries = owned.get(platform_id, [])
    if not entries:
        click.echo(f"  (no provenance map declared for platform {platform_id!r})")
        return

    for rel in entries:
        p = root / rel
        marker = "present" if (p.exists() or p.is_symlink()) else "absent"
        click.echo(f"  [{marker}] {rel}  (CataForge-managed)")

    # Also flag Cursor mirror state: is .claude/rules present even though the
    # mirror is off?  That usually means a stale artifact from an older deploy.
    if platform_id == "cursor":
        mirror = root / ".claude" / "rules"
        if mirror.exists() or mirror.is_symlink():
            profile_path = cfg.paths.platform_profile("cursor")
            mirror_enabled = _read_cursor_mirror_flag(profile_path)
            if not mirror_enabled:
                click.echo(
                    "  NOTE: .claude/rules exists but rules.cross_platform_mirror "
                    "is false — likely a stale artifact from a pre-M5 deploy. "
                    "Safe to delete."
                )


def _read_cursor_mirror_flag(profile_path: Path) -> bool:
    """Best-effort read of ``rules.cross_platform_mirror`` from a YAML profile."""
    if not profile_path.is_file():
        return False
    try:
        import yaml as _yaml

        data = _yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return False
    if not isinstance(data, dict):
        return False
    rules = data.get("rules") or {}
    if not isinstance(rules, dict):
        return False
    return bool(rules.get("cross_platform_mirror", False))


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


def _check_protocol_script_references(cfg) -> int:
    """Scan ``.cataforge/`` protocol docs + hooks spec for ``python .cataforge/scripts/...``
    invocations and report any that point at a file that does not exist.

    Returns the number of distinct missing scripts (counts toward the
    ``cataforge doctor`` exit code gate).
    """
    import re

    # Match ``python <path>`` where <path> starts with ``.cataforge/scripts/``
    # and ends at the first whitespace or quote. Greedy enough to cover both
    # ``python .cataforge/scripts/framework/event_logger.py --event X``
    # (space-terminated) and ``python .cataforge/scripts/framework/setup.py``
    # at end of line. We deliberately do not resolve shell quoting — if a
    # protocol ever wraps the path in quotes we can revisit.
    pattern = re.compile(
        r"python\s+(\.cataforge/scripts/[^\s`\"'<>|&;]+\.py)"
    )

    root = cfg.paths.root
    scan_roots = (
        cfg.paths.agents_dir,
        cfg.paths.skills_dir,
        cfg.paths.rules_dir,
        cfg.paths.hooks_dir,
        cfg.paths.commands_dir,
    )

    suffixes = {".md", ".yaml", ".yml"}
    # script relpath → sorted list of "file:line" callers (for the error message)
    refs: dict[str, list[str]] = {}
    for base in scan_roots:
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in suffixes:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            for lineno, line in enumerate(text.splitlines(), start=1):
                for match in pattern.finditer(line):
                    rel = match.group(1)
                    try:
                        display = path.relative_to(root).as_posix()
                    except ValueError:
                        display = str(path)
                    refs.setdefault(rel, []).append(f"{display}:{lineno}")

    if not refs:
        click.echo("  (no protocol script references found)")
        return 0

    missing: list[tuple[str, list[str]]] = []
    for rel in sorted(refs):
        if not (root / rel).is_file():
            missing.append((rel, sorted(set(refs[rel]))))

    present_count = len(refs) - len(missing)
    parts = [f"{present_count}/{len(refs)} scripts present"]
    if missing:
        parts.append(f"{len(missing)} missing")
    click.echo("  " + ", ".join(parts))

    for rel, callers in missing:
        click.echo(f"  FAIL {rel} (referenced by):")
        # Cap the shown callers so a widely-used missing script doesn't
        # drown the output; the count conveys the scope.
        shown = callers[:5]
        for caller in shown:
            click.echo(f"    - {caller}")
        extra = len(callers) - len(shown)
        if extra > 0:
            click.echo(f"    - ... and {extra} more call site(s)")

    return len(missing)


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
