"""cataforge config — validate / inspect / edit / migrate framework.json."""

from __future__ import annotations

import json
from typing import Any

import click

from cataforge.interface.cli.main import cli

# Paths users may edit through `config set`. Everything else is either
# framework-owned (edit via upgrade) or has a dedicated command (setup).
SET_WHITELIST = frozenset(
    {
        "deployment.default_platform",
        "deployment.targets",
        "context.mode",
        "project.design_tool",
    }
)

_PLATFORM_VALUED = {"deployment.default_platform"}
_PLATFORM_LIST_VALUED = {"deployment.targets"}


@cli.group("config")
def config_group() -> None:
    """Inspect and edit .cataforge/framework.json safely."""


@config_group.command("validate")
@click.pass_context
def config_validate(ctx: click.Context) -> None:
    """Validate framework.json: schema shape, schema_version, platform ids."""
    from pydantic import ValidationError

    from cataforge.adapter.platform.conformance import ALL_PLATFORMS
    from cataforge.core.config_migrate import (
        CONFIG_SCHEMA_VERSION,
        needs_migration,
        reject_newer_schema,
    )
    from cataforge.core.errors import ConfigError
    from cataforge.core.schema.framework import FrameworkFile
    from cataforge.interface.cli._support.helpers import get_config_manager

    cfg = get_config_manager()
    raw = cfg.load_raw()
    if not raw:
        click.echo(f"FAIL: {cfg.paths.framework_json} missing or empty", err=True)
        ctx.exit(1)

    failures = 0
    try:
        reject_newer_schema(raw)
    except ConfigError as e:
        click.echo(f"FAIL: {e}", err=True)
        ctx.exit(1)

    try:
        FrameworkFile.model_validate(raw)
        click.echo("OK: schema shape valid")
    except ValidationError as e:
        click.echo(f"FAIL: schema validation: {e}", err=True)
        failures += 1

    targets = (raw.get("deployment") or {}).get("targets") or []
    legacy = (raw.get("runtime") or {}).get("platform")
    candidates = [str(t) for t in targets]
    if legacy:
        candidates.append(str(legacy))
    default = (raw.get("deployment") or {}).get("default_platform")
    if default:
        candidates.append(str(default))
    unknown_platforms = sorted(set(candidates) - set(ALL_PLATFORMS))
    if unknown_platforms:
        click.echo(f"FAIL: unknown platform id(s): {', '.join(unknown_platforms)}", err=True)
        failures += 1

    if default and targets and str(default) not in [str(t) for t in targets]:
        click.echo(
            f"FAIL: deployment.default_platform {default!r} not in deployment.targets {targets}"
        )
        failures += 1

    if needs_migration(raw):
        click.echo(
            f"WARN: schema v{raw.get('schema_version', 1)} layout detected — "
            "run `cataforge config migrate` to move to "
            f"schema v{CONFIG_SCHEMA_VERSION}."
        )

    if failures:
        ctx.exit(1)
    click.echo("Config valid.")


@config_group.command("get")
@click.argument("path")
@click.pass_context
def config_get(ctx: click.Context, path: str) -> None:
    """Print the resolved value at a dotted PATH."""
    from cataforge.interface.cli._support.helpers import get_config_manager

    value, _ = get_config_manager().explain(path)
    if value is None:
        click.echo(f"(unset) {path}")
        ctx.exit(1)
    click.echo(json.dumps(value, ensure_ascii=False))


@config_group.command("explain")
@click.argument("path")
def config_explain(path: str) -> None:
    """Print the resolved value at PATH and which layer supplied it."""
    from cataforge.interface.cli._support.helpers import get_config_manager

    value, source = get_config_manager().explain(path)
    click.echo(f"{path} = {json.dumps(value, ensure_ascii=False)}")
    click.echo(f"source: {source}")


@config_group.command("set")
@click.argument("path")
@click.argument("value")
@click.option("--dry-run", is_flag=True, help="Show the change without writing.")
@click.pass_context
def config_set(ctx: click.Context, path: str, value: str, dry_run: bool) -> None:
    """Set a whitelisted PATH to VALUE (lists as comma-separated)."""
    from cataforge.adapter.platform.conformance import ALL_PLATFORMS
    from cataforge.interface.cli._support.helpers import get_config_manager

    if path not in SET_WHITELIST:
        click.echo(
            f"FAIL: {path!r} is not editable via `config set` "
            f"(allowed: {', '.join(sorted(SET_WHITELIST))})"
        )
        ctx.exit(1)

    parsed: Any = value
    if path in _PLATFORM_LIST_VALUED:
        parsed = [item.strip() for item in value.split(",") if item.strip()]
        unknown = sorted(set(parsed) - set(ALL_PLATFORMS))
        if unknown:
            click.echo(f"FAIL: unknown platform id(s): {', '.join(unknown)}", err=True)
            ctx.exit(1)
    elif path in _PLATFORM_VALUED and value not in ALL_PLATFORMS:
        click.echo(
            f"FAIL: unknown platform id {value!r} (choices: {', '.join(ALL_PLATFORMS)})", err=True
        )
        ctx.exit(1)

    cfg = get_config_manager()
    current, _ = cfg.explain(path)
    if current == parsed:
        click.echo(f"{path} already = {json.dumps(parsed, ensure_ascii=False)} (no change)")
        return
    if dry_run:
        click.echo(
            f"would set {path}: {json.dumps(current, ensure_ascii=False)} "
            f"-> {json.dumps(parsed, ensure_ascii=False)}"
        )
        return

    with cfg._config_lock():
        raw = cfg.load_raw()
        node = raw
        parts = path.split(".")
        for part in parts[:-1]:
            nxt = node.get(part)
            if not isinstance(nxt, dict):
                nxt = {}
                node[part] = nxt
            node = nxt
        node[parts[-1]] = parsed
        cfg._write_raw(raw)
        cfg.reload()
    click.echo(f"{path} = {json.dumps(parsed, ensure_ascii=False)}")


@config_group.command("migrate")
@click.option("--dry-run", is_flag=True, help="Report the migration without writing.")
@click.pass_context
def config_migrate(ctx: click.Context, dry_run: bool) -> None:
    """Migrate framework.json to the current schema (idempotent, backed up)."""
    from cataforge.core.config_migrate import migrate_framework_json
    from cataforge.core.errors import ConfigError
    from cataforge.interface.cli._support.helpers import get_config_manager

    cfg = get_config_manager()
    try:
        result = migrate_framework_json(cfg.paths.root, dry_run=dry_run)
    except ConfigError as e:
        click.echo(f"FAIL: {e}", err=True)
        ctx.exit(1)
        return

    if not result.migrated:
        click.echo("Already at current schema — nothing to do.")
        return
    prefix = "would apply" if dry_run else "applied"
    for action in result.actions:
        click.echo(f"  {prefix}: {action}")
    if result.backup is not None:
        click.echo(f"  backup: {result.backup}")
    click.echo("Migration complete." if not dry_run else "Dry run — no files written.")
