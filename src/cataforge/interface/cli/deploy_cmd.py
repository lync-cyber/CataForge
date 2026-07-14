"""cataforge deploy — deploy framework to target platform(s)."""

from __future__ import annotations

from pathlib import Path

import click

from cataforge.adapter.platform.conformance import ALL_PLATFORMS
from cataforge.core.errors import ConfigError, NotInitializedError
from cataforge.interface.cli.main import cli

PLATFORM_CHOICES = ALL_PLATFORMS + ["all"]


def _require_scaffold(root: Path, targets: list[str], platforms_dir: Path) -> None:
    """Fail with a friendly hint when the project is not yet initialised.

    Two failure modes:
      1. No ``.cataforge/`` at all — user never ran ``cataforge setup``.
      2. ``.cataforge/`` exists but a requested platform's ``profile.yaml``
         is missing — partial/corrupt scaffold.
    """
    if not (root / ".cataforge").is_dir():
        hint_platform = targets[0] if targets and targets[0] != "all" else "claude-code"
        raise NotInitializedError(root, hint_platform=hint_platform)

    missing = [
        p for p in targets if p != "all" and not (platforms_dir / p / "profile.yaml").is_file()
    ]
    if missing:
        raise ConfigError(
            "Missing platform profile(s): " + ", ".join(missing) + "\n"
            f"  Expected at: {platforms_dir}/<platform>/profile.yaml\n"
            "  Re-run setup to restore the scaffold:\n"
            f"    cataforge setup --platform {missing[0]} --force-scaffold"
        )


@cli.command("deploy")
@click.option(
    "--platform",
    type=click.Choice(PLATFORM_CHOICES),
    default=None,
    help="Target platform (default: from framework.json).",
)
@click.option(
    "--dry-run",
    "dry_run",
    is_flag=True,
    help="Preview actions without writing files.",
)
@click.option("--conformance", is_flag=True, help="Run platform conformance checks only.")
@click.option(
    "--include-maintainer-only",
    "include_maintainer_only",
    is_flag=True,
    default=False,
    help=(
        "Also deploy skills marked `maintainer-only: true` in their SKILL.md "
        "frontmatter. Off by default — those skills operate on upstream "
        "(.cataforge maintainer) workflows like GitHub-issue triage and "
        "would just bloat prompt context for downstream users. Turn on "
        "when working inside the CataForge repo itself."
    ),
)
@click.option(
    "--copy",
    "force_copy",
    is_flag=True,
    default=False,
    help=(
        "Materialise skills/rules as independent COPIES instead of "
        "symlinks/junctions. Slightly more disk, but the IDE-visible "
        "tree is fully isolated from `.cataforge/` — so deleting or "
        "editing files inside `.claude/skills/<name>/` can never destroy "
        "the source. Recommended on Windows without Developer Mode "
        "(junction fallback) if you value safety over instant updates."
    ),
)
@click.option(
    "--rebuild",
    "rebuild",
    is_flag=True,
    default=False,
    help=(
        "Before deploying, remove every path the previous deploy claimed "
        "ownership of (per `.cataforge/.deploy-manifest.json`). Use this "
        "to reset a corrupt or partially-deployed state. User-authored "
        "files outside the manifest are never touched."
    ),
)
def deploy_command(
    platform: str | None,
    dry_run: bool,
    conformance: bool,
    include_maintainer_only: bool,
    force_copy: bool,
    rebuild: bool,
) -> None:
    """Deploy CataForge agents, hooks, and rules to the target platform.

    Reads the target platform from ``.cataforge/framework.json`` (written by
    ``cataforge setup``) and translates the bundled scaffold into the files
    that IDE actually looks at — e.g. ``CLAUDE.md``, ``.claude/agents/`` for
    Claude Code; ``.cursor/rules/`` for Cursor; ``AGENTS.md`` for Codex.

    \b
    EXAMPLES:
      cataforge deploy
          Deploy to the platform recorded in framework.json.

    \b
      cataforge deploy --platform cursor
          Override the target (useful when one repo is edited from
          multiple IDEs).

    \b
      cataforge deploy --dry-run
          Preview the actions without writing any files.

    \b
      cataforge deploy --platform all
          Emit artefacts for every supported IDE at once.

    \b
      cataforge deploy --conformance
          Validate every platform profile against its schema and exit.
    """
    from cataforge.core.events import EventBus
    from cataforge.interface.cli.helpers import get_config_manager

    cfg = get_config_manager()
    bus = EventBus()

    if conformance:
        from cataforge.adapter.platform.conformance import check_all_conformance

        issues = check_all_conformance()
        for issue in issues:
            click.echo(issue)
        if not issues:
            click.echo("All platforms conformant.")
        return

    targets: list[str] = []
    if platform == "all":
        targets = list(ALL_PLATFORMS)
    elif platform:
        targets = [platform]
    else:
        # No flag: deploy every declared target (single-platform projects
        # declare exactly one, so the legacy behaviour is unchanged).
        targets = list(cfg.deployment_targets)

    _require_scaffold(cfg.paths.root, targets, cfg.paths.platforms_dir)

    from cataforge.core.config_migrate import reject_newer_schema
    from cataforge.core.errors import ConfigError
    from cataforge.runtime.deploy.deployer import Deployer
    from cataforge.utils.locks import LockHeldError

    # Config errors fail the whole run before any platform deploys —
    # never a partial multi-platform deployment on a bad config.
    reject_newer_schema(cfg.load_raw())

    deployer = Deployer(cfg, bus)

    from cataforge.interface.cli.guidance import print_next_steps
    from cataforge.interface.cli.ui import ui

    def _run_all() -> None:
        for target in targets:
            ui.header(f"Deploying: {target}")

            if dry_run:
                ui.info("dry-run — no files will be written")
                actions = deployer.deploy(
                    target,
                    dry_run=True,
                    include_maintainer_only=include_maintainer_only,
                    force_copy=force_copy,
                    rebuild=rebuild,
                )
                for action in actions:
                    ui.print(f"  {action}")
                continue

            actions = deployer.deploy(
                target,
                include_maintainer_only=include_maintainer_only,
                force_copy=force_copy,
                rebuild=rebuild,
            )
            for action in actions:
                ui.print(f"  {action}")

    if dry_run:
        _run_all()
        ui.ok("Deploy complete.")
        return

    try:
        with Deployer.deploy_lock(cfg):
            _run_all()
    except LockHeldError as e:
        raise ConfigError(
            f"{e}\n"
            "If you need to work in parallel, use a separate worktree:\n"
            "  git worktree add ../<branch-dir> <branch>\n"
            "A stale lock from a crashed run expires automatically."
        ) from e

    ui.ok("Deploy complete.")
    print_next_steps("deploy-done")
