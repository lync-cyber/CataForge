"""The ``setup`` group itself (invoke_without_command) — the main flow."""

from __future__ import annotations

from pathlib import Path

import click

from cataforge.adapter.platform.conformance import ALL_PLATFORMS
from cataforge.interface.cli._support.errors import CataforgeGroup
from cataforge.interface.cli.main import cli
from cataforge.interface.cli.setup import _flow


@cli.group("setup", cls=CataforgeGroup, invoke_without_command=True)
@click.option(
    "--platform",
    type=click.Choice(ALL_PLATFORMS),
    default=None,
    help="Target AI IDE platform.",
)
@click.option("--with-penpot", is_flag=True, help="Include Penpot design integration.")
@click.option(
    "--context-mode",
    type=click.Choice(["markdown", "graph"]),
    default=None,
    help=(
        "Context source-of-truth mode. graph (default): the graph is the source "
        "and `cataforge context finalize` exports Markdown for review. markdown: "
        "Markdown is the source, no graph backend. Prompted on a fresh install "
        "when omitted; defaults to graph non-interactively."
    ),
)
@click.option(
    "--language",
    "languages",
    multiple=True,
    metavar="LANG",
    help=(
        "Declare a project language (repeatable). Synonyms like 'typescript' "
        "normalise to canonical ids. Omit to detect from markers and pin the "
        "result when project.languages is unset."
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
    context_mode: str | None,
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
          edits to framework.json deployment.default_platform are preserved; other
          files under .cataforge/ are overwritten.
          For per-file preview use `cataforge upgrade apply --dry-run`.

    \b
      cataforge setup --check-prereqs
          Validate environment only — no writes.

    \b
      cataforge setup env-block
          Print the §执行环境 block for the detected stack (exit 2 = none).

    \b
      cataforge setup permissions
          Narrow the Bash allowlist to the detected stack.
    """
    if click.get_current_context().invoked_subcommand is not None:
        return  # env-block / permissions subcommand owns this invocation

    from cataforge.core.config import ConfigManager
    from cataforge.core.events import FRAMEWORK_SETUP, EventBus
    from cataforge.core.paths import find_project_root_or_none
    from cataforge.interface.cli._support.helpers import resolve_project_dir

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
        _flow._report_dry_run(
            cfg,
            scaffold_missing=scaffold_missing,
            scaffold_dir=scaffold_dir,
            force_scaffold=force_scaffold,
            platform=platform,
            languages=languages,
            context_mode=context_mode,
            with_penpot=with_penpot,
            deploy_after=deploy_after,
        )
        return

    if scaffold_missing or force_scaffold:
        _flow._scaffold(scaffold_dir, force=force_scaffold)
        # Re-read framework.json now that it exists on disk — without this
        # reload, the version banner below would show the pre-scaffold default
        # ("0.0.0") instead of the real bundled version.
        cfg.reload()

    click.echo(f"CataForge v{cfg.version} — setup")

    if check_only:
        _flow._run_checks(cfg)
        return

    _flow._ensure_gitattributes(cfg.paths.root)

    if platform:
        diff = cfg.describe_platform_change(platform)
        if show_diff:
            if diff is None:
                click.echo(
                    f"  framework.json: deployment.default_platform already = "
                    f"{platform} (no change)"
                )
            else:
                click.echo(
                    f"  framework.json diff: {diff['field']}: "
                    f"{diff['before']!r} → {diff['after']!r}"
                )
        if diff is not None:
            cfg.set_default_platform(platform)
        click.echo(f"Platform set to: {platform}")
        click.echo("  (framework.json modified only under deployment)")

    _flow._apply_languages(cfg, languages)
    _flow._apply_context_mode(cfg, context_mode, scaffold_missing=scaffold_missing)
    _flow._apply_penpot(cfg, with_penpot)

    from cataforge.interface.cli._support.guidance import print_next_steps
    from cataforge.interface.cli._support.ui import ui

    if not deploy_after:
        bus.emit(
            FRAMEWORK_SETUP,
            {"platform": platform, "with_penpot": with_penpot, "scaffold_only": True},
        )
        ui.ok("Setup complete. Run `cataforge deploy` to write IDE artifacts.")
        print_next_steps("setup-done")
        return

    target = platform or cfg.default_platform
    click.echo(f"Deploying for platform: {target}")

    for action in _flow._locked_deploy(cfg, bus, target):
        click.echo(f"  {action}")

    bus.emit(FRAMEWORK_SETUP, {"platform": target, "with_penpot": with_penpot})
    ui.ok("Setup complete.")
    print_next_steps("setup-deployed")
