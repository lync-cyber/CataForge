"""Private helpers behind the ``cataforge setup`` main flow."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import click

if TYPE_CHECKING:
    from pathlib import Path

    from cataforge.core.config import ConfigManager
    from cataforge.core.events import EventBus


def _locked_deploy(cfg: ConfigManager, bus: EventBus, target: str) -> list[str]:
    """Run one platform deploy under the project deploy lock."""
    from cataforge.core.errors import ConfigError
    from cataforge.runtime.deploy.deployer import Deployer
    from cataforge.utils.locks import LockHeldError

    try:
        with Deployer.deploy_lock(cfg):
            return Deployer(cfg, bus).deploy(target)
    except LockHeldError as e:
        raise ConfigError(
            f"{e}\nIf you need to work in parallel, use a separate worktree:\n"
            "  git worktree add ../<branch-dir> <branch>"
        ) from e


def _scaffold(dest: Path, *, force: bool) -> None:
    """Copy the bundled .cataforge/ skeleton into *dest*."""
    from cataforge.core.scaffold import copy_scaffold_to, format_protected_warning

    action = "Refreshing" if dest.is_dir() else "Scaffolding"
    click.echo(f"{action} .cataforge/ at {dest}")
    result = copy_scaffold_to(dest, force=force)
    if result.backup is not None:
        click.echo(f"  backup: {result.backup.relative_to(dest.parent)}")
    click.echo(
        f"  wrote {len(result.written)} file(s)"
        + (f", kept {len(result.skipped)} existing" if result.skipped else "")
    )
    for line in format_protected_warning(result.protected, dest):
        click.secho(f"  {line}", fg="yellow", err=True)


def _ensure_gitattributes(root: Path) -> None:
    """Create a default .gitattributes when missing; never overwrite."""
    from cataforge.application.services.git_hygiene import ensure_gitattributes

    status = ensure_gitattributes(root)
    if status.wrote_file:
        click.echo("  wrote .gitattributes (line-ending defaults)")
    elif status.ok:
        click.echo("  .gitattributes: OK")
    else:
        click.secho(
            "  .gitattributes: WARN — add `text=auto` and at least one `eol=` rule "
            "or run `cataforge setup gitattributes` after manual cleanup.",
            fg="yellow",
        )


def _apply_languages(cfg: ConfigManager, languages: tuple[str, ...]) -> None:
    """Write declared ``project.languages``, backfilling from detection when unset.

    SKILL-side consumers read ``project.languages`` verbatim and skip their
    lang-rule loading when it is empty, so an unpinned project must be
    backfilled here — detection output that is only echoed never reaches them.
    """
    from cataforge.core.languages import detect_languages, normalize

    if languages:
        normalized = normalize(list(languages))
        cfg.set_languages(normalized)
        click.echo(f"Languages set to: {', '.join(normalized)}")
        return
    if cfg.languages:
        return
    detected = detect_languages(cfg.paths.root)
    if detected:
        cfg.set_languages(detected)
        click.echo(
            f"  detected languages pinned to project.languages: {', '.join(detected)} "
            "(override with `setup --language <id>`)"
        )
    else:
        click.echo(
            "  no project languages declared or detected (declare with `setup --language <id>`)"
        )


def _apply_penpot(cfg: ConfigManager, with_penpot: bool) -> None:
    """Enable the Penpot design integration: set ``design_tool`` + drop the spec.

    Writing ``.cataforge/mcp/penpot.yaml`` is what makes a later ``cataforge
    deploy`` inject the Penpot MCP server; ``design_tool`` records the choice
    durably so upgrades and tooling can see it.
    """
    if not with_penpot:
        return
    from cataforge.adapter.integrations.penpot.mcp_spec import write_penpot_mcp_spec

    cfg.set_design_tool("penpot")
    spec = write_penpot_mcp_spec(cfg.paths.root)
    click.echo(f"Penpot 设计集成已启用: design_tool=penpot, {spec}")
    click.echo(
        "  Tip: 运行 `cataforge deploy` 让 CLAUDE.md / AGENTS.md 的「设计工具」"
        "字段从 framework.json 重新渲染。"
    )


def _report_dry_run(
    cfg: ConfigManager,
    *,
    scaffold_missing: bool,
    scaffold_dir: Path,
    force_scaffold: bool,
    platform: str | None,
    languages: tuple[str, ...],
    context_mode: str | None,
    with_penpot: bool,
    deploy_after: bool,
) -> None:
    """Print what a real `setup` run would change, writing nothing."""
    click.echo("(dry-run — no files will be written)")
    if scaffold_missing:
        click.echo(f"  would scaffold .cataforge/ at {scaffold_dir}")
    elif force_scaffold:
        click.echo(f"  would refresh .cataforge/ at {scaffold_dir}")
    else:
        click.echo("  .cataforge/ already present (no scaffold changes)")

    if platform:
        diff = cfg.describe_platform_change(platform) if not scaffold_missing else None
        if scaffold_missing:
            click.echo(
                f"  would set framework.json: deployment.default_platform = {platform} "
                "(file created by scaffold)"
            )
        elif diff is None:
            click.echo(
                f"  framework.json: deployment.default_platform already = {platform} (no change)"
            )
        else:
            click.echo(
                f"  would patch framework.json: {diff['field']}: "
                f"{diff['before']!r} → {diff['after']!r}"
            )
            click.echo("  (no other framework.json fields will be touched)")
    else:
        click.echo("  no --platform specified; framework.json would be untouched")

    if languages:
        from cataforge.core.languages import normalize

        click.echo(f"  would set framework.json: project.languages = {normalize(list(languages))}")

    if context_mode:
        click.echo(f"  would set framework.json: context.mode = {context_mode}")

    if with_penpot:
        click.echo(
            "  would set framework.json: project.design_tool = penpot "
            "and write .cataforge/mcp/penpot.yaml"
        )

    click.echo("  would ensure .gitattributes line-ending hygiene (write only if missing)")

    if deploy_after:
        click.echo("  would chain `cataforge deploy` (run `cataforge deploy --dry-run` to preview)")
    click.echo("Dry-run complete. No changes made.")


def _apply_context_mode(cfg: ConfigManager, mode: str | None, *, scaffold_missing: bool) -> None:
    """Resolve and persist ``context.mode``.

    An explicit ``--context-mode`` always wins. On a fresh interactive
    install with no flag, prompt the user. Otherwise leave the scaffold
    default (graph) untouched — orthogonal to the execution-mode choice.
    """
    resolved = mode
    if resolved is None and scaffold_missing and sys.stdin.isatty():
        resolved = _prompt_context_mode()
    if resolved is None:
        return
    current = (cfg.load_raw().get("context") or {}).get("mode")
    if resolved == current:
        click.echo(f"Context mode: {resolved} (no change)")
        return
    cfg.set_context_mode(resolved)
    click.echo(f"Context mode set to: {resolved}")


def _prompt_context_mode() -> str:
    from cataforge.interface.cli._support.ui import ChoiceOption, ui

    choice = ui.prompt_choice(
        "上下文事实源模式",
        [
            ChoiceOption(
                "1",
                "graph（推荐）",
                description="图为源，cataforge context finalize 导出 markdown 供人工审查",
            ),
            ChoiceOption(
                "2",
                "markdown",
                description="markdown 为源，无图后端",
            ),
        ],
        default="1",
    )
    return {"1": "graph", "2": "markdown"}[choice]


def _run_checks(cfg: ConfigManager) -> None:
    """Quick prerequisite checks."""
    import shutil
    import sys

    click.echo(f"Python: {sys.version}")
    click.echo(f"framework.json: {'OK' if cfg.paths.framework_json.is_file() else 'MISSING'}")
    click.echo(f"hooks.yaml: {'OK' if cfg.paths.hooks_spec.is_file() else 'MISSING'}")

    for tool in ("ruff", "npx", "docker"):
        found = shutil.which(tool) is not None
        click.echo(f"{tool}: {'found' if found else 'not found'}")
