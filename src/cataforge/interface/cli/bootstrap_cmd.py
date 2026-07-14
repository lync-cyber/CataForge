"""cataforge bootstrap — one-shot setup → upgrade → deploy → doctor.

Thin orchestrator on top of the existing subcommands. Each step's
skip/run decision is derived from on-disk product state (scaffold
version, manifest hashes, ``.deploy-state``) — never from a separate
"bootstrap-ran" flag — so the output always reflects reality even if
the user manually deletes ``.claude/`` or rolls back the scaffold.

Design notes:

* No new business logic lives here. Side effects delegate to
  :func:`cataforge.core.scaffold.copy_scaffold_to`,
  :class:`cataforge.runtime.deploy.deployer.Deployer`, and ``ctx.invoke`` for
  ``doctor``. Bootstrap is an orchestrator, not a reconciler.
* ``--dry-run`` prints every step's decision (skip/run + why) without
  writing. Safe for CI and for humans who want a preview.
* The command fails fast: a failed step halts the pipeline. We do not
  attempt to auto-repair intermediate state.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import click

from cataforge.adapter.platform.conformance import ALL_PLATFORMS
from cataforge.application.services.bootstrap import Plan, build_plan
from cataforge.interface.cli.main import cli

if TYPE_CHECKING:
    from cataforge.core.config import ConfigManager
    from cataforge.core.events import EventBus


@cli.command("bootstrap")
@click.option(
    "--platform",
    type=click.Choice(ALL_PLATFORMS),
    default=None,
    help="Target AI IDE platform. Required on fresh install; "
    "on an existing project defaults to framework.json's deployment.default_platform.",
)
@click.option(
    "--context-mode",
    type=click.Choice(["markdown", "graph"]),
    default=None,
    help=(
        "Context source-of-truth mode forwarded to `setup`. graph (graph "
        "source, export markdown for review, default) or markdown (no graph "
        "backend). Prompted on a fresh install when omitted."
    ),
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Print the plan without executing. Shows skip/run decision per step.",
)
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    help="Skip interactive confirmation before writing.",
)
@click.option(
    "--skip-doctor",
    is_flag=True,
    help="Skip the final `doctor` gate (not recommended — doctor is the "
    "whole point of the final step).",
)
@click.pass_context
def bootstrap_command(
    ctx: click.Context,
    platform: str | None,
    context_mode: str | None,
    dry_run: bool,
    yes: bool,
    skip_doctor: bool,
) -> None:
    """Install, upgrade, deploy, and verify — in one idempotent command.

    \b
    WHAT IT DOES:
      1. setup     Copy the bundled .cataforge/ scaffold if missing.
      2. upgrade   Refresh scaffold if the bundled version is newer
                   than the on-disk version, or if manifest drift exists.
      3. deploy    Render IDE-visible artefacts (.claude/, CLAUDE.md, …)
                   if never deployed, target platform changed, or the
                   scaffold was just refreshed.
      4. doctor    Run the verification gate (always, unless --skip-doctor).

    \b
    SKIP RULES:
      Each step checks its own product state and is skipped when already
      current. There is no cached "bootstrap ran" flag — re-running a
      fully-bootstrapped project just runs doctor.

    \b
    EXAMPLES:
      cataforge bootstrap --platform claude-code
          Fresh install, single command.

    \b
      cataforge bootstrap
          Already-installed project — refreshes whatever is stale.

    \b
      cataforge bootstrap --dry-run
          Print the plan without writing anything.
    """
    from cataforge.interface.cli.helpers import get_config_manager

    cfg = get_config_manager()
    plan = build_plan(cfg, requested_platform=platform, requested_mode=context_mode)

    _print_plan(plan, dry_run=dry_run)

    if dry_run:
        return

    # Abort cleanly on any hard error surfaced during plan building.
    if plan.error is not None:
        raise click.ClickException(plan.error)

    if not yes and plan.any_writes() and not _confirm_plan(plan):
        from cataforge.interface.cli.ui import ui

        ui.warn("Aborted.")
        raise click.exceptions.Exit(1)

    _execute_plan(ctx, cfg, plan, context_mode=context_mode, skip_doctor=skip_doctor)


# ---- presentation ----

_ACTION_STYLE = {
    "run": ("•", "green"),
    "skip": ("○", "cyan"),
    "error": ("✗", "red"),
}


def _print_plan(plan: Plan, *, dry_run: bool) -> None:
    header = "Plan (dry-run):" if dry_run else "Plan:"
    click.echo(header)
    for step in plan.steps:
        mark, color = _ACTION_STYLE.get(step.action, ("?", "white"))
        click.echo(
            f"  {click.style(mark, fg=color)} {step.name:<8} {step.action:<5} — {step.reason}"
        )
    if plan.target_platform and not plan.error:
        click.echo(f"\n  target platform: {plan.target_platform}")
    if plan.error:
        click.secho(f"\n  blocking: {plan.error}", fg="red", err=True)


def _confirm_plan(plan: Plan) -> bool:
    from cataforge.interface.cli.ui import ui

    n_run = sum(1 for s in plan.steps if s.action == "run")
    return ui.prompt_confirm(f"Run {n_run} step(s)?", default=True)


# ---- execution ----


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


def _migrate_config(cfg: ConfigManager, ui: Any) -> None:
    from cataforge.core.config_migrate import migrate_framework_json

    migration = migrate_framework_json(cfg.paths.root)
    if migration.migrated:
        for action in migration.actions:
            ui.info(f"[config migrate] {action}")


def _execute_plan(
    ctx: click.Context,
    cfg: ConfigManager,
    plan: Plan,
    *,
    context_mode: str | None,
    skip_doctor: bool,
) -> None:
    """Run each planned step in order. Halt on first failure.

    Setup and upgrade are not reimplemented here — they delegate to
    ``setup_command`` (fresh scaffold + platform write) and
    ``copy_scaffold_to(force=True)`` (in-place refresh) respectively.
    Bootstrap's job is orchestration: deciding which steps run and
    halting on failure, not duplicating the side effects.
    """
    from cataforge.core.events import FRAMEWORK_SETUP, EventBus
    from cataforge.core.scaffold import copy_scaffold_to
    from cataforge.interface.cli.ui import ui

    bus = EventBus()

    step_by_name = {s.name: s for s in plan.steps}

    ui.print("")

    setup_step = step_by_name.get("setup")
    if setup_step is not None and setup_step.action == "run":
        ui.print("")
        ui.info(f"[setup] delegating to `cataforge setup --platform {plan.target_platform}`")
        # Delegate to setup_command so any new side effect added there
        # (e.g. --emit-env-block, additional checks) is automatically
        # picked up by bootstrap. deploy_after=False: bootstrap owns the
        # deploy step and we don't want setup to chain it.
        from cataforge.interface.cli.setup_cmd import setup_command

        ctx.invoke(
            setup_command,
            platform=plan.target_platform,
            with_penpot=False,
            context_mode=context_mode,
            check_only=False,
            force_scaffold=False,
            deploy_after=False,
            dry_run=False,
            show_diff=False,
        )
        cfg.reload()

    upgrade_step = step_by_name.get("upgrade")
    if upgrade_step is not None and upgrade_step.action == "run":
        # Upgrade is a refresh-in-place — copy_scaffold_to(force=True) is
        # the only direct call here because there is no `cataforge upgrade
        # apply` no-prompt subcommand to invoke (apply has its own
        # interactive flow with backups + diff). When such a non-interactive
        # path is added, this branch can collapse to ctx.invoke.
        ui.print("")
        ui.info(f"[upgrade] refreshing .cataforge/ at {cfg.paths.cataforge_dir}")
        result = copy_scaffold_to(
            cfg.paths.cataforge_dir,
            force=True,
        )
        _migrate_config(cfg, ui)
        cfg.reload()
        if result.backup is not None:
            ui.ok(f"backup: {result.backup.relative_to(cfg.paths.cataforge_dir.parent)}")
        ui.ok(f"wrote {len(result.written)} file(s)")
        from cataforge.core.scaffold import format_protected_warning

        for line in format_protected_warning(result.protected, cfg.paths.cataforge_dir):
            ui.warn(line)

        # Heal a penpot design-tool choice into framework.json (the SSOT) before
        # the deploy step below force-overwrites the instruction file from it.
        _lift_design_tool(cfg)

    _ensure_gitattributes(cfg)

    deploy_step = step_by_name.get("deploy")
    if deploy_step is not None and deploy_step.action == "run":
        target = plan.target_platform or cfg.default_platform
        ui.print("")
        ui.info(f"[deploy] rendering artefacts for {target}")
        for action in _locked_deploy(cfg, bus, target):
            ui.print(f"  {action}")
        bus.emit(FRAMEWORK_SETUP, {"platform": target, "bootstrap": True})

    # First-time bootstrap previously left docs/.doc-index.json absent
    # forever, so doctor's orphan check silently skipped and `cataforge
    # docs load` was invisible to the user. Auto-generate the first
    # index when docs/ exists with markdown content; non-blocking on
    # failure so a malformed doc doesn't strand bootstrap mid-flow.
    docs_dir = cfg.paths.root / "docs"
    if docs_dir.is_dir() and any(docs_dir.rglob("*.md")):
        ui.print("")
        ui.info("[docs-index] generating docs/.doc-index.json")
        from cataforge.domain.docs.indexer import main as indexer_main

        try:
            rc = indexer_main(["--project-root", str(cfg.paths.root)])
            if rc != 0:
                ui.warn(
                    f"docs index returned {rc} — see warnings above; "
                    "fix front matter then rerun `cataforge docs index`."
                )
        except Exception as e:  # noqa: BLE001
            ui.warn(f"docs index crashed: {e} — bootstrap continuing.")

    # Graph-backed projects (graph mode) need an initialized store before
    # the first `context write` / `reconcile`; without it those commands crash
    # on a missing store. Create it idempotently (only when absent) so
    # re-bootstrap is a no-op; non-blocking on failure like docs-index above.
    _maybe_init_kg_store(cfg)

    # Set the GitHub merge policy once (delete-branch-on-merge + squash-only) so
    # PR head branches are auto-deleted server-side. Idempotent + best-effort:
    # no-op without gh/auth/GitHub remote, never blocks bootstrap.
    _maybe_ensure_merge_policy(cfg)

    doctor_step = step_by_name.get("doctor")
    if skip_doctor:
        ui.print("")
        ui.info("[doctor] skipped (--skip-doctor)")
        return
    if doctor_step is not None and doctor_step.action == "run":
        ui.print("")
        ui.info("[doctor] running diagnostics")
        from cataforge.interface.cli.doctor_cmd import doctor_command

        ctx.invoke(doctor_command)


def _ensure_gitattributes(cfg: ConfigManager) -> None:
    """Ensure line-ending policy exists during bootstrap without overwriting custom files."""
    from cataforge.application.services.git_hygiene import ensure_gitattributes
    from cataforge.interface.cli.ui import ui

    status = ensure_gitattributes(cfg.paths.root)
    if status.wrote_file:
        ui.ok("wrote .gitattributes")
    elif not status.ok:
        ui.warn(".gitattributes lacks line-ending rules; run `cataforge setup gitattributes`.")


def _lift_design_tool(cfg: ConfigManager) -> None:
    """Heal a penpot design-tool choice into framework.json before deploy.

    deploy force-overwrites the instruction file's 设计工具 field from
    framework.json#project.design_tool (the SSOT); lift a choice that lived only
    in CLAUDE.md / AGENTS.md so the bootstrap path runs the same heal as
    `upgrade apply`. Idempotent — a no-op once design_tool is non-default.
    """
    from cataforge.application.services.upgrade import lift_design_tool_intent
    from cataforge.interface.cli.ui import ui

    lifted = lift_design_tool_intent(cfg)
    if lifted:
        ui.ok(
            f"[design-tool] recorded project.design_tool = {lifted} from the "
            "instruction file (now the single source of truth)"
        )


def _maybe_ensure_merge_policy(cfg: ConfigManager) -> None:
    """Apply the GitHub merge policy once during bootstrap (best-effort).

    No-op unless ``gh`` is installed + authenticated and origin is a GitHub
    remote. Idempotent (only PATCHes a drifted setting). Any failure warns and
    continues — bootstrap must not hinge on a network/permission hiccup.
    """
    import shutil

    from cataforge.interface.cli.ui import ui

    if shutil.which("gh") is None:
        return
    try:
        from cataforge.application.services.git_hygiene import GitHubRepo, GitWorkTree
        from cataforge.utils.run_subprocess import run as run_proc

        if run_proc(["gh", "auth", "status"]).returncode != 0:
            return
        git = GitWorkTree(cfg.paths.root)
        if not git.is_inside_work_tree():
            return
        gh = GitHubRepo.from_remote(git)
        if gh is None:
            return
        change = gh.ensure_merge_policy(cfg.git_remote_policy)
    except Exception as e:  # noqa: BLE001
        ui.warn(f"merge-policy setup skipped: {e} — bootstrap continuing.")
        return

    if change.changed:
        ui.print("")
        ui.ok(f"[merge-policy] set on {change.slug}: {', '.join(change.fields)}")


def _maybe_init_kg_store(cfg: ConfigManager) -> None:
    """Hydrate the KG store on a graph-backed project that lacks one.

    No-op under ``markdown`` (the graph is not a backend) and when a populated
    store already exists (idempotent re-bootstrap). The physical store is
    gitignored, so a fresh clone rebuilds it here: ``graph`` from the latest
    NQuads snapshot. Failure warns and continues —
    bootstrap must not be stranded by a hydration hiccup.
    """
    from cataforge.domain.kg._dispatch import invalidate_cache
    from cataforge.interface.cli.ui import ui

    invalidate_cache()  # setup may have rewritten context.mode this run
    try:
        from cataforge.application.context.write import ensure_store

        result = ensure_store(str(cfg.paths.root))
    except Exception as e:  # noqa: BLE001
        ui.warn(f"kg store hydration failed: {e} — bootstrap continuing.")
        return

    if result.action == "noop":
        return
    ui.print("")
    ui.ok(f"[kg-store] {result.action}: {result.detail}")
