"""cataforge setup — project initialization."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

import click

from cataforge.adapter.platform.conformance import ALL_PLATFORMS
from cataforge.interface.cli.main import cli

if TYPE_CHECKING:
    from cataforge.core.config import ConfigManager


@cli.command("setup")
@click.option(
    "--platform",
    type=click.Choice(ALL_PLATFORMS),
    default=None,
    help="Target AI IDE platform.",
)
@click.option("--with-penpot", is_flag=True, help="Include Penpot design integration.")
@click.option(
    "--context-strategy",
    type=click.Choice(["kg-first", "doc-only"]),
    default=None,
    help=(
        "Document-driving backend. kg-first: the graph is the source of truth, "
        "`cataforge kg export` renders markdown for human review. doc-only: "
        "markdown is the source and the graph is bypassed. Prompted on a fresh "
        "install when omitted; defaults to kg-first non-interactively."
    ),
)
@click.option(
    "--language",
    "languages",
    multiple=True,
    metavar="LANG",
    help=(
        "Declare a project language (repeatable). Synonyms like 'typescript' "
        "normalise to canonical ids. Omit to auto-detect from markers at read time."
    ),
)
@click.option(
    "--check-prereqs",
    "--check-only",
    "check_only",
    is_flag=True,
    help="Only check prerequisites, do not install. (Alias: --check-only.)",
)
@click.option(
    "--force-scaffold",
    is_flag=True,
    help="Re-copy the bundled .cataforge/ scaffold, overwriting existing files.",
)
@click.option(
    "--deploy",
    "deploy_after",
    is_flag=True,
    help="After scaffolding, also run `cataforge deploy` for the selected platform.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Report what setup would change without writing any files.",
)
@click.option(
    "--show-diff",
    is_flag=True,
    help="Print the framework.json fields that will change before writing.",
)
def setup_command(
    platform: str | None,
    with_penpot: bool,
    context_strategy: str | None,
    languages: tuple[str, ...],
    check_only: bool,
    force_scaffold: bool,
    deploy_after: bool,
    dry_run: bool,
    show_diff: bool,
) -> None:
    """Initialise .cataforge/ and record the target platform.

    Writes the scaffold but *not* IDE-visible artefacts — run
    ``cataforge deploy`` next, or pass ``--deploy`` here to chain both.

    \b
    TWO-STEP PIPELINE:
      cataforge setup  →  .cataforge/ + framework.json (scaffold)
      cataforge deploy →  CLAUDE.md / .claude/ / .cursor/ / … (IDE layer)

    \b
    COMMON FLOWS:
      cataforge setup --platform claude-code
          Fresh install — pick platform, scaffold, then run `deploy`.

    \b
      cataforge setup --platform claude-code --deploy
          Fresh install in one step (handy for CI / quick-start).

    \b
      cataforge setup --force-scaffold
          Re-copy the bundled scaffold over an existing project. User
          edits to framework.json runtime.platform are preserved; other
          files under .cataforge/ are overwritten.
          For per-file preview use `cataforge upgrade apply --dry-run`.

    \b
      cataforge setup --check-prereqs
          Validate environment only — no writes.
    """
    from cataforge.core.config import ConfigManager
    from cataforge.core.events import FRAMEWORK_SETUP, EventBus
    from cataforge.core.paths import find_project_root_or_none
    from cataforge.interface.cli.helpers import resolve_project_dir

    # Resolve the project root. `--project-dir` is the explicit opt-in to target
    # any directory (including a parent project). Without it, setup initialises
    # in cwd: it must NOT silently walk up and attach to an ancestor's
    # .cataforge/ — that would scaffold into the wrong project. Running setup
    # inside an existing root (cwd already has .cataforge/) stays unchanged.
    override = resolve_project_dir()
    if override is not None:
        root = override
    else:
        root = Path.cwd()
        ancestor = find_project_root_or_none(root)
        if ancestor is not None and ancestor != root.resolve():
            click.secho(
                f"Note: an ancestor project exists at {ancestor}. Initialising "
                f"in the current directory ({root}) instead of attaching to it. "
                f"Pass `--project-dir {ancestor}` to target the ancestor.",
                fg="yellow",
                err=True,
            )
    cfg = ConfigManager(project_root=root)
    bus = EventBus()

    click.echo(f"Project root: {cfg.paths.root}")

    scaffold_dir = cfg.paths.cataforge_dir
    scaffold_missing = not scaffold_dir.is_dir()

    if dry_run:
        _report_dry_run(
            cfg,
            scaffold_missing=scaffold_missing,
            scaffold_dir=scaffold_dir,
            force_scaffold=force_scaffold,
            platform=platform,
            languages=languages,
            context_strategy=context_strategy,
            deploy_after=deploy_after,
        )
        return

    if scaffold_missing or force_scaffold:
        _scaffold(scaffold_dir, force=force_scaffold)
        # Re-read framework.json now that it exists on disk — without this
        # reload, the version banner below would show the pre-scaffold default
        # ("0.0.0") instead of the real bundled version.
        cfg.reload()

    click.echo(f"CataForge v{cfg.version} — setup")

    if check_only:
        _run_checks(cfg)
        return

    if platform:
        diff = cfg.describe_platform_change(platform)
        if show_diff:
            if diff is None:
                click.echo(f"  framework.json: runtime.platform already = {platform} (no change)")
            else:
                click.echo(
                    f"  framework.json diff: {diff['field']}: "
                    f"{diff['before']!r} → {diff['after']!r}"
                )
        if diff is not None:
            cfg.set_runtime_platform(platform)
        click.echo(f"Platform set to: {platform}")
        click.echo("  (framework.json modified only at runtime.platform)")

    _apply_languages(cfg, languages)
    _apply_context_strategy(cfg, context_strategy, scaffold_missing=scaffold_missing)

    from cataforge.interface.cli.guidance import print_next_steps
    from cataforge.interface.cli.ui import ui

    if not deploy_after:
        bus.emit(
            FRAMEWORK_SETUP,
            {"platform": platform, "with_penpot": with_penpot, "scaffold_only": True},
        )
        ui.ok("Setup complete. Run `cataforge deploy` to write IDE artifacts.")
        print_next_steps("setup-done")
        return

    target = platform or cfg.runtime_platform
    click.echo(f"Deploying for platform: {target}")

    from cataforge.runtime.deploy.deployer import Deployer

    deployer = Deployer(cfg, bus)
    actions = deployer.deploy(target)
    for action in actions:
        click.echo(f"  {action}")

    bus.emit(FRAMEWORK_SETUP, {"platform": target, "with_penpot": with_penpot})
    ui.ok("Setup complete.")
    print_next_steps("setup-deployed")


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


def _apply_languages(cfg: ConfigManager, languages: tuple[str, ...]) -> None:
    """Write declared ``project.languages``, or hint at what auto-detect sees."""
    from cataforge.core.languages import active_languages, detect_languages, normalize

    if languages:
        normalized = normalize(list(languages))
        cfg.set_languages(normalized)
        click.echo(f"Languages set to: {', '.join(normalized)}")
        return
    # None declared — surface detection so the user knows what the SSOT resolves
    # to, and how to pin it.
    detected = detect_languages(cfg.paths.root)
    if detected:
        click.echo(
            f"  detected languages: {', '.join(detected)} "
            "(auto-detected at read time; pin with `setup --language <id>`)"
        )
    elif not active_languages(cfg):
        click.echo(
            "  no project languages declared or detected (declare with `setup --language <id>`)"
        )


def _report_dry_run(
    cfg: ConfigManager,
    *,
    scaffold_missing: bool,
    scaffold_dir: Path,
    force_scaffold: bool,
    platform: str | None,
    languages: tuple[str, ...],
    context_strategy: str | None,
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
                f"  would set framework.json: runtime.platform = {platform} "
                "(file created by scaffold)"
            )
        elif diff is None:
            click.echo(f"  framework.json: runtime.platform already = {platform} (no change)")
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

    if context_strategy:
        click.echo(f"  would set framework.json: context.strategy = {context_strategy}")

    if deploy_after:
        click.echo("  would chain `cataforge deploy` (run `cataforge deploy --dry-run` to preview)")
    click.echo("Dry-run complete. No changes made.")


def _apply_context_strategy(
    cfg: ConfigManager, strategy: str | None, *, scaffold_missing: bool
) -> None:
    """Resolve and persist ``context.strategy``.

    An explicit ``--context-strategy`` always wins. On a fresh interactive
    install with no flag, prompt the user. Otherwise leave the scaffold
    default (kg-first) untouched — orthogonal to the execution-mode choice.
    """
    resolved = strategy
    if resolved is None and scaffold_missing and sys.stdin.isatty():
        resolved = _prompt_context_strategy()
    if resolved is None:
        return
    current = (cfg.load_raw().get("context") or {}).get("strategy")
    if resolved == current:
        click.echo(f"Document-driving strategy: {resolved} (no change)")
        return
    cfg.set_context_strategy(resolved)
    click.echo(f"Document-driving strategy set to: {resolved}")


def _prompt_context_strategy() -> str:
    from cataforge.interface.cli.ui import ChoiceOption, ui

    choice = ui.prompt_choice(
        "文档驱动方式",
        [
            ChoiceOption(
                "1",
                "KG 驱动",
                description="图为源，cataforge kg export 导出 markdown 供人工审查",
            ),
            ChoiceOption(
                "2",
                "markdown + doc CLI 驱动",
                description="markdown 为源，默认旁路 KG",
            ),
        ],
        default="1",
    )
    return "kg-first" if choice == "1" else "doc-only"


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
