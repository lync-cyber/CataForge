"""cataforge doctor — environment diagnostics entry.

The actual check implementations live in :mod:`cataforge.interface.cli.doctor`.
This module wires them into the ``doctor`` Click command and exits non-zero
when any migration_check / structural check fails, so CI can treat it as a
gate.
"""

from __future__ import annotations

import shutil
import sys
from typing import TYPE_CHECKING

import click

from cataforge.interface.cli.main import cli

if TYPE_CHECKING:
    from cataforge.core.config import ConfigManager

from .doctor._helpers import check_dir, check_file, check_import
from .doctor.capability_health import report_capability_health
from .doctor.context_authority import check_context_mode_validity
from .doctor.deploy_integrity import (
    check_deploy_drift,
    check_deploy_integrity,
    check_deploy_source_orphans,
)
from .doctor.event_log import check_event_log_bypass_writes, check_event_log_schema
from .doctor.git_hygiene import check_git_hygiene
from .doctor.hook_health import check_hook_script_importability, report_hook_errors
from .doctor.hygiene import check_claude_md_hygiene, check_project_state_projection
from .doctor.kg_ingestion import (
    check_kg_ingestion_completeness,
    check_kg_shacl_conformance,
    check_kg_snapshot_freshness,
    check_kg_snapshot_gitignore,
    check_kg_xref_target_integrity,
)
from .doctor.migration import check_runtime_api_version, run_migration_checks
from .doctor.protocol_refs import (
    _DEPRECATED_REFS,
    check_deprecated_references,
    check_markdown_link_resolution,
    check_protocol_script_references,
)
from .doctor.provenance import report_deployment_provenance
from .doctor.retired_assets import check_retired_skill_assets
from .doctor.shell_preference import check_shell_preference
from .doctor.skill_health import (
    check_agent_skill_reachability,
    check_builtin_skill_reachability,
    check_docs_validate,
)

__all__ = ["doctor_command", "_DEPRECATED_REFS"]

# Declarative tail of the doctor run: each entry is (header, check, gating).
# ``check(cfg)`` runs after its header is printed; when ``gating`` is True its
# return value (a failure count) is added to the exit-code tally. Informational
# reporters (provenance, hook log) return nothing and never gate. Adding a
# diagnostic is a one-line append here rather than another echo+accumulate pair.
_DOCTOR_SECTIONS = [
    # runtime_api_version contract — drift between scaffold-shipped value and
    # on-disk value means framework.json was authored against a different
    # runtime API revision than the package can serve.
    ("runtime_api_version contract:", check_runtime_api_version, True),
    # Framework migration checks — defined in framework.json, verified here so
    # scaffold/repo drift surfaces automatically instead of only at upgrade time.
    ("Framework migration checks:", run_migration_checks, True),
    # Protocol script references — markdown/YAML in .cataforge/ invoke
    # ``python .cataforge/scripts/...``; a missing script fails silently at
    # runtime, so a static scan catches the rot at diagnostic time.
    ("Protocol script references:", check_protocol_script_references, True),
    ("Deprecated protocol references:", check_deprecated_references, True),
    # Markdown link resolution — a SKILL/AGENT link to repo-root docs/ resolves
    # downstream to a path deploy never copied (only .cataforge/** ships), so the
    # agent follows a dead link. Gate keeps the deployable-asset boundary closed.
    ("Markdown link resolution:", check_markdown_link_resolution, True),
    # Retired skill leftovers — informational WARN: a removed framework skill's
    # source dir survived an upgrade (untracked/edited, so manifest prune missed
    # it). Non-gating; `upgrade apply` removes it. Reframes the deprecated-refs
    # scan, which skips these dirs so they surface here, not as a stale FAIL.
    ("Retired skill assets:", check_retired_skill_assets, False),
    ("Docs validation:", check_docs_validate, True),
    # context.mode validity — an invalid mode or the retired strategy/authoring
    # pair is a config error; gate it here so the author migrates framework.json.
    ("Context mode config:", check_context_mode_validity, True),
    # KG ingestion completeness — hard ERROR gate ensuring the KG is the single
    # source of truth for active doc_types (ERROR when an FS entity_id is
    # missing from the graph; skipped when no store exists).
    ("KG ingestion completeness:", check_kg_ingestion_completeness, True),
    # KG xref target integrity — hard gate mirroring `kg validate`'s
    # cf:*-target-exists shapes: a renamed/deleted entity leaves dangling edges
    # the entity_id-keyed reconcile diff misses, so reconcile=0 could hide
    # broken references. Gating so doctor-clean implies edge-target integrity.
    ("KG xref target integrity:", check_kg_xref_target_integrity, True),
    # KG SHACL conformance — full generated-shapes pass (closed shapes,
    # required slots, enum membership) that per-write validation doesn't run.
    # Gating when the shacl extra is installed; degrades to a printed skip
    # note (never silently) when it isn't.
    ("KG SHACL conformance:", check_kg_shacl_conformance, True),
    # KG snapshot freshness — graph-mode WARN: the gitignored store rebuilds
    # from the latest NQuads snapshot on clone, so a snapshot lagging the live
    # store risks losing uncommitted graph state. Non-gating; nudges finalize.
    ("KG snapshot freshness:", check_kg_snapshot_freshness, False),
    # KG snapshot gitignore — graph-mode WARN: a project-root .gitignore that
    # excludes the snapshots dir drops the graph's only durable artifact on
    # clone. Non-gating; points at the conflicting root rule.
    ("KG snapshot gitignore:", check_kg_snapshot_gitignore, False),
    ("Hook script importability:", check_hook_script_importability, True),
    ("Built-in skill reachability:", check_builtin_skill_reachability, True),
    # Agent skill dependencies — every skills: declaration in a source
    # AGENT.md must resolve to .cataforge/skills/<id>/SKILL.md; on platforms
    # without a skills surface the deployed agent body points there directly.
    ("Agent skill dependencies:", check_agent_skill_reachability, True),
    ("EVENT-LOG schema sample:", check_event_log_schema, True),
    ("EVENT-LOG bypass guard:", check_event_log_bypass_writes, True),
    ("Instruction file hygiene:", check_claude_md_hygiene, True),
    # Project-state projection — WARN when a secondary instruction file's
    # §项目状态 drifted from the default platform's (the SSOT).
    ("Project state projection:", check_project_state_projection, False),
    # Shell preference — Windows-only WARN: deployed settings prefer Git Bash
    # (CLAUDE_CODE_USE_POWERSHELL_TOOL=0) but no Git Bash is resolvable, so the
    # Bash tool would be unusable. Non-gating; points at install / env remedy.
    ("Shell preference:", check_shell_preference, False),
    # Git hygiene — informational: local branches whose upstream is gone
    # (squash-merged). Non-gating (branch cleanup is never a CI failure);
    # points the user at `cataforge git prune`.
    ("Git hygiene:", check_git_hygiene, False),
    # Deployment provenance — informational: shows which platform dirs the last
    # deploy would have written so users see what is CataForge-managed.
    ("Deployment provenance:", report_deployment_provenance, False),
    ("Capability enforcement:", report_capability_health, False),
    # Deploy integrity — the hard gate: turns dangling links / missing owned
    # dirs into FAILs so post-deploy regressions can't slip past doctor.
    ("Deploy integrity:", check_deploy_integrity, True),
    # Deploy source orphans — informational: a deployed skill whose source
    # under .cataforge/skills/ was removed lingers until the next deploy
    # prunes it. WARN-only (non-gating) so the self-healing artefact doesn't
    # fail doctor.
    ("Deploy source orphans:", check_deploy_source_orphans, False),
    # Deploy drift — informational WARN: .cataforge/ source or the installed
    # cataforge version moved since the last deploy, so IDE artefacts are
    # stale. Non-gating (a nudge, not a failure); points the user at deploy.
    ("Deploy drift:", check_deploy_drift, False),
    # Recent hook execution failures — informational; surfaces silent
    # observer-hook crashes logged by hook_main().
    ("Hook execution log:", report_hook_errors, False),
]


# Sections whose behaviour depends on the platform scope — they accept a
# ``platforms`` kwarg. Everything else is platform-neutral.
_PLATFORM_SCOPED_CHECKS = {
    run_migration_checks,
    check_claude_md_hygiene,
    check_project_state_projection,
    check_shell_preference,
    report_deployment_provenance,
    report_capability_health,
    check_deploy_integrity,
    check_deploy_drift,
}


def _resolve_platform_scope(cfg: ConfigManager, platform: str | None) -> list[str]:
    """Doctor's platform scope: explicit id > all (targets ∪ deployed) >
    default (deployed platforms, else the declared default)."""
    from cataforge.runtime.deploy.manifest import deployed_platforms

    if platform and platform != "all":
        return [platform]
    deployed = deployed_platforms(cfg.paths.root)
    if platform == "all":
        merged = list(cfg.deployment_targets)
        for p in deployed:
            if p not in merged:
                merged.append(p)
        return merged
    return deployed or [cfg.default_platform]


@cli.command("doctor")
@click.option(
    "--platform",
    "platform",
    type=str,
    default=None,
    metavar="ID|all",
    help="Restrict platform-scoped checks to one platform, or 'all' for "
    "every declared target and deployed platform.",
)
@click.pass_context
def doctor_command(ctx: click.Context, platform: str | None) -> None:
    """Run environment diagnostics and report issues.

    Exits with a non-zero status when any migration_check fails, so CI can
    treat doctor as a gate.
    """
    from cataforge.interface.cli._support.helpers import get_config_manager
    from cataforge.interface.cli._support.ui import ui

    ui.header("CataForge Doctor", subtitle="Environment + scaffold integrity gate")

    cfg = get_config_manager()

    from cataforge.adapter.platform.conformance import ALL_PLATFORMS

    if platform and platform != "all" and platform not in ALL_PLATFORMS:
        click.echo(
            f"FAIL: unknown platform {platform!r} (choices: {', '.join(ALL_PLATFORMS)}, all)"
        )
        ctx.exit(1)
    platform_scope = _resolve_platform_scope(cfg, platform)

    # Python
    click.echo(f"\nPython: {sys.version}")
    click.echo(f"  Executable: {sys.executable}")

    # Framework — these are the source assets every CataForge project must
    # carry. Missing any of them is a setup failure, not a notice.
    click.echo(f"\nProject root: {cfg.paths.root}")
    failed_count = 0
    failed_count += check_file("framework.json", cfg.paths.framework_json, required=True)
    failed_count += check_dir(".cataforge/agents", cfg.paths.agents_dir, required=True)
    failed_count += check_dir(".cataforge/skills", cfg.paths.skills_dir, required=True)
    failed_count += check_dir(".cataforge/rules", cfg.paths.rules_dir, required=True)
    failed_count += check_dir(".cataforge/hooks", cfg.paths.hooks_dir, required=True)
    failed_count += check_file("hooks.yaml", cfg.paths.hooks_spec, required=True)
    failed_count += check_dir(".cataforge/platforms", cfg.paths.platforms_dir, required=True)

    # Config
    click.echo(f"\nFramework version: {cfg.version}")
    click.echo(f"Default platform: {cfg.default_platform}")
    click.echo(f"Platform scope: {', '.join(platform_scope)}")

    # Dependencies — these two are load-bearing for the CLI itself; if
    # either is missing the user can't run any cataforge command, so
    # gate doctor's exit code on them. ``check_import(..., required=True)``
    # mirrors the same pattern check_file / check_dir already use.
    click.echo("\nDependencies:")
    failed_count += check_import("yaml", "PyYAML", required=True)
    failed_count += check_import("click", "click", required=True)

    # External tools — diagnostic patterns for missing tools live in
    # cataforge.interface.cli._support.diagnostics so the same diagnosis/fix copy is shown by
    # other commands that probe these binaries (penpot doctor, hook tests).
    from cataforge.interface.cli._support.diagnostics import DOCTOR_PATTERNS
    from cataforge.interface.cli._support.ui import ui as _ui

    click.echo("\nExternal tools:")
    missing_tools_blob: list[str] = []
    for tool in ("ruff", "npx", "docker", "git"):
        path = shutil.which(tool)
        status = f"found ({path})" if path else "not found"
        click.echo(f"  {tool}: {status}")
        if path is None:
            missing_tools_blob.append(f"{tool}: not found")
    if missing_tools_blob:
        _ui.diagnose("\n".join(missing_tools_blob), DOCTOR_PATTERNS)

    # Platform profiles
    click.echo("\nPlatform profiles:")
    for pid in ("claude-code", "cursor", "codex", "opencode"):
        profile_path = cfg.paths.platform_profile(pid)
        status = "OK" if profile_path.is_file() else "MISSING"
        click.echo(f"  {pid}: {status}")

    for header, check, gating in _DOCTOR_SECTIONS:
        click.echo(f"\n{header}")
        if check in _PLATFORM_SCOPED_CHECKS:
            result = check(cfg, platforms=platform_scope)
        else:
            result = check(cfg)  # type: ignore[operator]
        if gating:
            failed_count += result or 0

    click.echo("\nDiagnostics complete.")
    _print_summary(failed_count)

    if failed_count:
        ctx.exit(1)


def _print_summary(failed_count: int) -> None:
    """Final one-line verdict so users do not have to scan every section.

    Kept intentionally minimal: a count of failures is the load-bearing
    datum. Section-level pass counts would require threading through more
    state than the value adds — sections already print their own running
    tallies (e.g. ``7/7 built-in skills``).
    """
    from cataforge.interface.cli._support.guidance import print_next_steps
    from cataforge.interface.cli._support.ui import NextStep, ui

    if failed_count == 0:
        ui.ok("Summary: all checks passed.")
        print_next_steps("doctor-pass")
        return
    ui.fail(f"Summary: {failed_count} failed — see FAIL lines above.")
    # Tailored next-steps when doctor fails — the right follow-up depends on
    # the symptom class. We give a triage list rather than a single command.
    ui.next_steps(
        [
            NextStep("cataforge deploy", "if FAIL was in `Deploy integrity`"),
            NextStep("cataforge upgrade apply", "if FAIL was in `Framework migration checks`"),
            NextStep("cataforge doctor", "rerun to confirm after fixing"),
        ]
    )
