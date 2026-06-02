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

import click

from cataforge.adapter.platform.conformance import ALL_PLATFORMS
from cataforge.application.services.bootstrap import Plan, build_plan
from cataforge.interface.cli.main import cli


@cli.command("bootstrap")
@click.option(
    "--platform",
    type=click.Choice(ALL_PLATFORMS),
    default=None,
    help="Target AI IDE platform. Required on fresh install; "
    "on an existing project defaults to framework.json's runtime.platform.",
)
@click.option(
    "--context-strategy",
    type=click.Choice(["kg-first", "doc-only"]),
    default=None,
    help=(
        "Document-driving backend forwarded to `setup`. kg-first (graph is "
        "source, export markdown for review) or doc-only (markdown is source, "
        "bypass the graph). Prompted on a fresh install when omitted."
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
    context_strategy: str | None,
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
    plan = build_plan(cfg, requested_platform=platform)

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

    _execute_plan(ctx, cfg, plan, context_strategy=context_strategy, skip_doctor=skip_doctor)


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


def _execute_plan(
    ctx: click.Context,
    cfg,
    plan: Plan,
    *,
    context_strategy: str | None,
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
        # picked up by bootstrap. We pass --no-deploy explicitly: bootstrap
        # owns the deploy step and we don't want setup to chain it.
        from cataforge.interface.cli.setup_cmd import setup_command

        ctx.invoke(
            setup_command,
            platform=plan.target_platform,
            with_penpot=False,
            context_strategy=context_strategy,
            check_only=False,
            force_scaffold=False,
            # deploy_after=False so setup doesn't chain a deploy — bootstrap
            # owns the deploy step. no_deploy=False to avoid setup's
            # deprecation warning (the flag is a deprecated no-op).
            deploy_after=False,
            no_deploy=False,
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
        cfg.reload()
        if result.backup is not None:
            ui.ok(f"backup: {result.backup.relative_to(cfg.paths.cataforge_dir.parent)}")
        ui.ok(f"wrote {len(result.written)} file(s)")
        from cataforge.core.scaffold import format_protected_warning

        for line in format_protected_warning(result.protected, cfg.paths.cataforge_dir):
            ui.warn(line)

    deploy_step = step_by_name.get("deploy")
    if deploy_step is not None and deploy_step.action == "run":
        target = plan.target_platform or cfg.runtime_platform
        ui.print("")
        ui.info(f"[deploy] rendering artefacts for {target}")
        from cataforge.runtime.deploy.deployer import Deployer

        deployer = Deployer(cfg, bus)
        actions = deployer.deploy(target)
        for action in actions:
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
