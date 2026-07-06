"""cataforge setup — project initialization."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

import click

from cataforge.adapter.platform.conformance import ALL_PLATFORMS
from cataforge.interface.cli.errors import CataforgeGroup
from cataforge.interface.cli.main import cli
from cataforge.utils.atomic_write import atomic_write_text

if TYPE_CHECKING:
    from cataforge.core.config import ConfigManager


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
          edits to framework.json runtime.platform are preserved; other
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
            context_mode=context_mode,
            with_penpot=with_penpot,
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

    _ensure_gitattributes(cfg.paths.root)

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
    _apply_context_mode(cfg, context_mode, scaffold_missing=scaffold_missing)
    _apply_penpot(cfg, with_penpot)

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
    from cataforge.interface.cli.ui import ChoiceOption, ui

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


def _setup_root() -> Path:
    """Project root for stack-scoped subcommands: explicit override, else walk up."""
    from cataforge.core.paths import find_project_root_or_none
    from cataforge.interface.cli.helpers import resolve_project_dir

    override = resolve_project_dir()
    if override is not None:
        return override
    return find_project_root_or_none(Path.cwd()) or Path.cwd()


@setup_command.command("env-block")
def setup_env_block() -> None:
    """Print the §执行环境 Markdown block for the detected stack.

    Exit 2 when no known toolchain is detected so the caller can fall back to
    asking the user.
    """
    from cataforge.core.stack import detect_primary_stack, render_env_block

    stack = detect_primary_stack(_setup_root())
    if stack is None:
        click.echo("- 无自动检测到的标准包管理器（请根据实际技术栈手动填写）")
        raise SystemExit(2)
    click.echo(render_env_block(stack), nl=False)


@setup_command.command("permissions")
def setup_permissions() -> None:
    """Narrow the Bash allowlist in the platform settings file to the detected stack.

    Exit 2 when no stack is detected, 1 when no platform settings file exists.
    """
    import json

    from cataforge.core.stack import detect_primary_stack

    root = _setup_root()
    stack = detect_primary_stack(root)
    if stack is None:
        click.echo("no stack detected — leaving permissions unchanged", err=True)
        raise SystemExit(2)

    # Generic utility prefixes are needed regardless of stack for Bootstrap.
    allow_prefixes = [*stack.bash_allow, "git ", "ls ", "cat ", "echo "]

    settings = root / ".claude" / "settings.json"
    if settings.is_file():
        data = json.loads(settings.read_text())
        perms = data.setdefault("permissions", {})
        perms["allow"] = [f"Bash({p}*)" for p in allow_prefixes]
        atomic_write_text(settings, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        click.echo(f"updated {settings} — {len(allow_prefixes)} allow prefixes")
        return

    cursor_settings = root / ".cursor" / "hooks.json"
    if cursor_settings.is_file():
        click.echo(
            f"Cursor permissions narrowing not implemented yet — detected stack: {stack.language}",
            err=True,
        )
        return

    click.echo("no platform settings file found — nothing to update", err=True)
    raise SystemExit(1)


@setup_command.command("gitattributes")
def setup_gitattributes() -> None:
    """Ensure project-root .gitattributes line-ending defaults."""
    from cataforge.application.services.git_hygiene import ensure_gitattributes

    root = _setup_root()
    status = ensure_gitattributes(root)
    if status.wrote_file:
        click.echo("wrote .gitattributes")
        return
    if status.ok:
        click.echo("ok: .gitattributes already normalizes line endings")
        return
    click.echo(
        ".gitattributes exists but lacks `text=auto` or `eol=`; "
        "preserving user-owned file. Add line-ending rules manually.",
        err=True,
    )
    raise SystemExit(1)
