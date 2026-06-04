"""Command + rules deployment step (+ overrides rules flow)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from cataforge.core.paths import ProjectPaths
from cataforge.runtime.deploy.steps.skills import copy_render_md_tree
from cataforge.runtime.deploy.template_render import render_runtime_content
from cataforge.utils.atomic_write import atomic_write_text

if TYPE_CHECKING:
    from cataforge.adapter.platform.adapter import PlatformAdapter
    from cataforge.runtime.deploy.manifest import DeployManifest


def deploy_commands(
    adapter: PlatformAdapter,
    source_dir: Path,
    project_root: Path,
    *,
    dry_run: bool = False,
    manifest: DeployManifest | None = None,
    prior_manifest: set[str] | None = None,
) -> list[str]:
    """Copy ``.cataforge/commands/*.md`` into the platform's slash-command dir.

    Flat copy of every ``*.md`` file. Prune scope is bounded by
    ``prior_manifest``: we only delete ``*.md`` entries that the previous
    deploy claimed ownership of, so hand-authored slash commands (e.g. the
    git-tracked dogfood wrapper ``framework-issue-resolve.md``) survive every
    redeploy.
    """
    target_rel = adapter.get_command_target_dir()
    if not target_rel or not source_dir.is_dir():
        return []
    target_dir = project_root / target_rel
    if not dry_run:
        target_dir.mkdir(parents=True, exist_ok=True)

    source_names = {md.name for md in source_dir.glob("*.md")}
    actions: list[str] = []

    # Prune stale commands the previous deploy wrote but that are no longer
    # in source. Without ``prior_manifest`` we fall back to the legacy
    # "anything orphaned in target" rule for direct callers that pre-date
    # the manifest plumbing.
    if target_dir.is_dir():
        for existing in target_dir.glob("*.md"):
            if existing.name in source_names:
                continue
            existing_rel = f"{target_rel}/{existing.name}"
            if prior_manifest is not None and existing_rel not in prior_manifest:
                continue
            if dry_run:
                actions.append(f"would prune orphan {target_rel}/{existing.name}")
            else:
                existing.unlink()
                actions.append(f"pruned orphan {target_rel}/{existing.name}")

    for md_file in sorted(source_dir.glob("*.md")):
        dst = target_dir / md_file.name
        cmd_rel = f"{target_rel}/{md_file.name}"
        if dry_run:
            actions.append(f"would deploy commands/{md_file.name} → {target_rel}/{md_file.name}")
            continue
        rendered = render_runtime_content(md_file.read_text(), adapter)
        atomic_write_text(dst, rendered)
        if manifest is not None:
            manifest.record(cmd_rel)
        actions.append(f"commands/{md_file.name} → {target_rel}")
    return actions


def deploy_rules(
    adapter: PlatformAdapter,
    source_dir: Path,
    project_root: Path,
    *,
    dry_run: bool = False,
    manifest: DeployManifest | None = None,
    prior_manifest: set[str] | None = None,
    force_copy: bool = False,
) -> list[str]:
    """Deploy rule files to the platform's rule directory.

    Copy + render so placeholders in ``COMMON-RULES.md`` /
    ``SUB-AGENT-PROTOCOLS.md`` reach the IDE already substituted.
    ``force_copy`` is accepted for API parity; deploy always copies (rendering
    forces independent copies — symlinks would point back at unrendered
    source).
    """
    del force_copy  # retained for API compat; always copy under render path
    del prior_manifest  # rules tree write is whole-dir; no per-file prune here

    scan_dirs = adapter.get_agent_scan_dirs()
    if not scan_dirs:
        return []
    platform_root = Path(scan_dirs[0]).parent
    target = project_root / platform_root / "rules"
    actions = copy_render_md_tree(adapter, source_dir, target, dry_run=dry_run)
    if manifest is not None and not dry_run:
        manifest.record(f"{platform_root.as_posix()}/rules")
    return actions


def deploy_additional_outputs(
    adapter: PlatformAdapter,
    rules_dir: Path,
    project_root: Path,
    *,
    dry_run: bool = False,
    manifest: DeployManifest | None = None,
    prior_manifest: set[str] | None = None,
) -> list[str]:
    """Deploy platform-specific additional outputs.

    Delegates to the adapter's ``deploy_additional_outputs_hook`` (default:
    no-op; Cursor generates MDC rules)."""
    return adapter.deploy_additional_outputs_hook(
        rules_dir,
        project_root,
        dry_run=dry_run,
        manifest=manifest,
        prior_manifest=prior_manifest,
    )


def deploy_overrides_rules(
    adapter: PlatformAdapter,
    project_root: Path,
    *,
    dry_run: bool = False,
    manifest: DeployManifest | None = None,
) -> list[str]:
    """Materialise platform override rules into native artefacts.

    Scans ``.cataforge/platforms/{platform_id}/overrides/rules/*.md`` (both
    hand-authored rules and auto-generated ones from hook bridge
    ``apply_degradation``) and writes each through the adapter's
    ``wrap_rule_for_platform`` hook.

    The hook controls output format and target path; the default produces a
    verbatim copy at ``<context_injection.rules_distribution.target>/<name>.md``.
    Returning ``None`` from the hook signals the platform opted not to emit a
    file (e.g. when the rule is registered through ``opencode.json#instructions``).
    """
    overrides_dir = ProjectPaths(project_root).platform_overrides(adapter.platform_id) / "rules"
    if not overrides_dir.is_dir():
        return []

    actions: list[str] = []
    for md_file in sorted(overrides_dir.glob("*.md")):
        content = md_file.read_text()
        wrapped = adapter.wrap_rule_for_platform(md_file.stem, content)
        if wrapped is None:
            actions.append(
                f"SKIP: overrides/rules/{md_file.name} — "
                f"{adapter.platform_id} platform opted not to materialise"
            )
            continue
        target_rel, body = wrapped
        target_path = project_root / target_rel
        if dry_run:
            actions.append(f"would deploy overrides/rules/{md_file.name} → {target_rel}")
            continue
        target_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(target_path, body)
        if manifest is not None:
            manifest.record(target_rel)
        actions.append(f"overrides/rules/{md_file.name} → {target_rel}")
    return actions
