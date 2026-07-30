"""Hook script importability + runtime degradation reporting + error log tail."""

from __future__ import annotations

from datetime import UTC
from typing import TYPE_CHECKING, Any

import click

if TYPE_CHECKING:
    from cataforge.core.config import ConfigManager


def check_hook_script_importability(cfg: ConfigManager) -> int:
    """Verify each hooks.yaml script resolves to an importable module.

    Uses ``find_spec`` (no execution). ``custom:`` scripts are excluded —
    those are covered by the protocol-script-reference scan.
    """
    import importlib.util

    try:
        from cataforge.runtime.hook.bridge import load_hooks_spec
    except ImportError as e:
        click.echo(f"  FAIL cannot import cataforge.runtime.hook.bridge: {e}")
        return 1

    spec_path = cfg.paths.hooks_spec
    if not spec_path.is_file():
        click.echo(f"  (no hooks.yaml at {spec_path} — skipping)")
        return 0

    try:
        spec = load_hooks_spec(spec_path)
    except Exception as e:
        click.echo(f"  FAIL cannot parse {spec_path}: {e}")
        return 1

    declared: list[str] = []
    for event_hooks in (spec.get("hooks") or {}).values():
        for entry in event_hooks or []:
            script = str(entry.get("script", "")).replace(".py", "")
            if not script or script.startswith("custom:"):
                continue
            declared.append(script)

    if not declared:
        click.echo("  (no built-in hook scripts declared)")
        return 0

    missing: list[str] = []
    for name in declared:
        module = f"cataforge.runtime.hook.scripts.{name}"
        try:
            found = importlib.util.find_spec(module) is not None
        except (ImportError, ValueError):
            found = False
        if not found:
            missing.append(name)

    present = len(declared) - len(missing)
    click.echo(f"  {present}/{len(declared)} declared scripts importable")
    for name in missing:
        click.echo(
            f"  FAIL cataforge.runtime.hook.scripts.{name} — IDE invocations will "
            "ImportError before @hook_main can log them. "
            "Reinstall with `pip install -e .` (or the wheel) to resolve."
        )

    _report_runtime_degradation(cfg, declared)
    return len(missing)


def _report_runtime_degradation(cfg: ConfigManager, declared: list[str]) -> None:
    """List each declared script's hook policy mode on the current platform."""
    try:
        from cataforge.adapter.platform.registry import get_adapter

        adapter = get_adapter(cfg.default_platform)
    except Exception as e:
        click.echo(f"  (cannot load adapter for {cfg.default_platform!r}: {e})")
        return

    statuses: dict[str, str] = {}
    for name in declared:
        statuses[name] = adapter.get_hook_policy(name).mode

    unsupported = sorted(n for n, s in statuses.items() if s == "unsupported")
    other_degraded = sorted(n for n, s in statuses.items() if s in ("hybrid", "degraded"))
    native_count = sum(1 for s in statuses.values() if s == "native")

    summary = f"  Hook policies on {cfg.default_platform}: {native_count} native"
    if unsupported:
        summary += f", {len(unsupported)} unsupported"
    if other_degraded:
        summary += f", {len(other_degraded)} hybrid/degraded"
    click.echo(summary)
    for name in unsupported:
        click.echo(f"    UNSUPPORTED {name} — no native hook or fallback will be generated")
    for name in other_degraded:
        click.echo(f"    {statuses[name].upper()} {name}")


def report_hook_errors(cfg: ConfigManager) -> None:
    """Surface recent entries from ``.cataforge/.hook-errors.jsonl``.

    Doctor doesn't fail on these — a crashed observer hook is degraded
    functionality, not a broken project — but it surfaces the log so the
    user knows it exists.
    """
    import json as _json
    from datetime import datetime, timedelta

    log_path = cfg.paths.hook_error_log
    if not log_path.is_file():
        click.echo("  (no hook errors recorded)")
        return

    cutoff = datetime.now(UTC) - timedelta(hours=24)
    recent: list[dict[str, Any]] = []
    try:
        with open(log_path) as f:
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
