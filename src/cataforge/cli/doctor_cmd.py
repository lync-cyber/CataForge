"""cataforge doctor — environment diagnostics entry.

The actual check implementations live in :mod:`cataforge.cli.doctor`.
This module wires them into the ``doctor`` Click command and exits non-zero
when any migration_check / structural check fails, so CI can treat it as a
gate.
"""

from __future__ import annotations

import shutil
import sys

import click

from cataforge.cli.main import cli

from .doctor._helpers import check_dir, check_file, check_import
from .doctor.event_log import check_event_log_bypass_writes, check_event_log_schema
from .doctor.hook_health import check_hook_script_importability, report_hook_errors
from .doctor.hygiene import check_claude_md_hygiene
from .doctor.kg_health import check_kg_health
from .doctor.migration import check_runtime_api_version, run_migration_checks
from .doctor.protocol_refs import (
    _DEPRECATED_REFS,
    check_deprecated_references,
    check_protocol_script_references,
)
from .doctor.provenance import report_deployment_provenance
from .doctor.skill_health import check_builtin_skill_reachability, check_docs_validate

__all__ = ["doctor_command", "_DEPRECATED_REFS"]


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
    check_file("framework.json", cfg.paths.framework_json)
    check_file("PROJECT-STATE.md", cfg.paths.project_state_md)
    check_dir(".cataforge/agents", cfg.paths.agents_dir)
    check_dir(".cataforge/skills", cfg.paths.skills_dir)
    check_dir(".cataforge/rules", cfg.paths.rules_dir)
    check_dir(".cataforge/hooks", cfg.paths.hooks_dir)
    check_file("hooks.yaml", cfg.paths.hooks_spec)
    check_dir(".cataforge/platforms", cfg.paths.platforms_dir)

    # Config
    click.echo(f"\nFramework version: {cfg.version}")
    click.echo(f"Runtime platform: {cfg.runtime_platform}")

    # Dependencies
    click.echo("\nDependencies:")
    check_import("yaml", "PyYAML")
    check_import("click", "click")

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

    # runtime_api_version contract — drift between scaffold-shipped value
    # and on-disk value means the user's framework.json was authored
    # against a different runtime API revision than the package can serve.
    click.echo("\nruntime_api_version contract:")
    failed_count = check_runtime_api_version(cfg)

    # Framework migration checks — defined in framework.json, verified here so
    # scaffold/repo drift surfaces automatically instead of only at upgrade time.
    click.echo("\nFramework migration checks:")
    failed_count += run_migration_checks(cfg)

    # Protocol script references — markdown/YAML files inside .cataforge/
    # routinely invoke ``python .cataforge/scripts/...`` commands. If one of
    # those scripts is missing, every call site silently fails at runtime,
    # with no signal until someone reads the hook error log. Static scan
    # catches the rot at diagnostic time.
    click.echo("\nProtocol script references:")
    failed_count += check_protocol_script_references(cfg)

    click.echo("\nDeprecated protocol references:")
    failed_count += check_deprecated_references(cfg)

    click.echo("\nDocs validation:")
    failed_count += check_docs_validate(cfg)

    click.echo("\nHook script importability:")
    failed_count += check_hook_script_importability(cfg)

    click.echo("\nBuilt-in skill reachability:")
    failed_count += check_builtin_skill_reachability(cfg)

    click.echo("\nEVENT-LOG schema sample:")
    failed_count += check_event_log_schema(cfg)

    click.echo("\nEVENT-LOG bypass guard:")
    failed_count += check_event_log_bypass_writes(cfg)

    click.echo("\nCLAUDE.md hygiene:")
    failed_count += check_claude_md_hygiene(cfg)

    click.echo("\nKG health (conflicts / SHACL / render):")
    failed_count += check_kg_health(cfg)

    # Deployment provenance — shows which platform-specific directories would
    # have been written by the last successful deploy. Lets users see at a
    # glance which ``.claude/`` / ``.cursor/`` / etc. are CataForge-managed
    # vs user/IDE-native.
    click.echo("\nDeployment provenance:")
    report_deployment_provenance(cfg)

    # Recent hook execution failures — logged by hook_main() so silent
    # observer-hook crashes don't stay invisible.
    click.echo("\nHook execution log:")
    report_hook_errors(cfg)

    click.echo("\nDiagnostics complete.")

    if failed_count:
        ctx.exit(1)
