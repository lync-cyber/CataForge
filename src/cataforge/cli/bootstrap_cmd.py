"""cataforge bootstrap — one-shot setup → upgrade → deploy → doctor.

Thin orchestrator on top of the existing subcommands. Each step's
skip/run decision is derived from on-disk product state (scaffold
version, manifest hashes, ``.deploy-state``) — never from a separate
"bootstrap-ran" flag — so the output always reflects reality even if
the user manually deletes ``.claude/`` or rolls back the scaffold.

Design notes:

* No new business logic lives here. Side effects delegate to
  :func:`cataforge.core.scaffold.copy_scaffold_to`,
  :class:`cataforge.deploy.deployer.Deployer`, and ``ctx.invoke`` for
  ``doctor``. Bootstrap is an orchestrator, not a reconciler.
* ``--dry-run`` prints every step's decision (skip/run + why) without
  writing. Safe for CI and for humans who want a preview.
* The command fails fast: a failed step halts the pipeline. We do not
  attempt to auto-repair intermediate state.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

import click

from cataforge.cli.main import cli
from cataforge.platform.conformance import ALL_PLATFORMS


@cli.command("bootstrap")
@click.option(
    "--platform",
    type=click.Choice(ALL_PLATFORMS),
    default=None,
    help="Target AI IDE platform. Required on fresh install; "
         "on an existing project defaults to framework.json's runtime.platform.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Print the plan without executing. Shows skip/run decision per step.",
)
@click.option(
    "--yes", "-y",
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
    from cataforge.cli.helpers import get_config_manager

    cfg = get_config_manager()
    plan = _build_plan(cfg, requested_platform=platform)

    _print_plan(plan, dry_run=dry_run)

    if dry_run:
        return

    # Abort cleanly on any hard error surfaced during plan building.
    if plan.error is not None:
        raise click.ClickException(plan.error)

    if not yes and plan.any_writes() and not _confirm_plan(plan):
        click.echo("Aborted.")
        raise click.exceptions.Exit(1)

    _execute_plan(ctx, cfg, plan, skip_doctor=skip_doctor)


# ---- plan model ----

class _StepPlan:
    """One pipeline step's skip/run decision and the reason behind it.

    Kept dataclass-free to stay aligned with the plain-dict style used
    elsewhere in the CLI (cf. the ``ctx.obj`` pattern in main.py).
    """
    __slots__ = ("name", "action", "reason")

    def __init__(self, name: str, action: str, reason: str) -> None:
        self.name = name
        # action ∈ {"skip", "run", "error"} — "error" is terminal (reported
        # up-front before any writes).
        self.action = action
        self.reason = reason


class _Plan:
    __slots__ = ("steps", "target_platform", "error")

    def __init__(self) -> None:
        self.steps: list[_StepPlan] = []
        self.target_platform: str | None = None
        self.error: str | None = None

    def add(self, name: str, action: str, reason: str) -> None:
        self.steps.append(_StepPlan(name, action, reason))

    def any_writes(self) -> bool:
        return any(s.action == "run" for s in self.steps if s.name != "doctor")


def _build_plan(cfg, *, requested_platform: str | None) -> _Plan:
    """Inspect on-disk state and decide what each step must do."""
    from cataforge.core.scaffold import classify_scaffold_files

    plan = _Plan()

    try:
        installed = _pkg_version("cataforge")
    except PackageNotFoundError:
        installed = None

    scaffold_dir = cfg.paths.cataforge_dir
    scaffold_exists = scaffold_dir.is_dir() and cfg.paths.framework_json.is_file()

    # Step 1: setup (scaffold).
    if not scaffold_exists:
        if requested_platform is None:
            plan.error = (
                "Fresh install detected (no .cataforge/). "
                "Rerun with `--platform <id>`, "
                f"e.g. --platform {ALL_PLATFORMS[0]}."
            )
            plan.add("setup", "error", plan.error)
            plan.target_platform = None
            # Still enumerate downstream steps as "blocked" so the user
            # sees the full picture.
            plan.add("upgrade", "skip", "blocked on setup")
            plan.add("deploy", "skip", "blocked on setup")
            plan.add("doctor", "skip", "blocked on setup")
            return plan
        plan.add(
            "setup", "run",
            f"no .cataforge/ at {scaffold_dir} — fresh scaffold",
        )
        plan.target_platform = requested_platform
        plan.add("upgrade", "skip", "fresh scaffold already current")
        plan.add("deploy", "run", "fresh install — initial deploy required")
        if requested_platform is not None:
            _append_doctor(plan)
        return plan

    plan.add(
        "setup", "skip",
        f"scaffold present (version {cfg.version})",
    )

    # Decide the target platform for downstream steps — explicit flag wins,
    # else the recorded runtime.platform.
    current_platform = cfg.runtime_platform
    plan.target_platform = requested_platform or current_platform
    if (
        requested_platform is not None
        and current_platform
        and requested_platform != current_platform
    ):
        plan.error = (
            f"--platform={requested_platform!r} conflicts with "
            f"framework.json runtime.platform={current_platform!r}. "
            "Run `cataforge setup --platform <id> --show-diff` explicitly "
            "to change the target platform — bootstrap will not rewrite it."
        )
        plan.add("upgrade", "error", plan.error)
        plan.add("deploy", "error", plan.error)
        plan.add("doctor", "skip", "blocked on platform mismatch")
        return plan

    # Step 2: upgrade (scaffold refresh).
    #
    # We trigger upgrade on either:
    #   (a) manifest drift — a scaffold file disagrees with the bundled copy;
    #   (b) installed package semver > recorded scaffold version — the user
    #       just ran `pip install -U cataforge` and framework.json (a preserved
    #       file) still advertises the old version.
    #
    # NOT triggering when ``installed < scaffold`` is intentional: editable
    # dev installs often have stale package metadata below the source tree's
    # __version__, and that case is harmless.
    classified = classify_scaffold_files(scaffold_dir)
    drifted = [s for _, s in classified if s in ("update", "user-modified", "drift", "new")]
    installed_newer = installed is not None and _semver_newer(installed, cfg.version)

    if drifted or installed_newer:
        tallies: dict[str, int] = {}
        for _, status in classified:
            tallies[status] = tallies.get(status, 0) + 1
        parts = [f"{count} {status}" for status, count in sorted(tallies.items())
                 if status in ("update", "user-modified", "drift", "new")]
        summary = ", ".join(parts) if parts else "version bump only"
        if installed_newer:
            summary = f"installed={installed} > scaffold={cfg.version}; {summary}"
        plan.add("upgrade", "run", f"scaffold refresh required ({summary})")
    else:
        plan.add("upgrade", "skip", "scaffold manifest matches bundled package")

    # Step 3: deploy.
    deploy_state_file = cfg.paths.deploy_state
    upgrade_running = plan.steps[-1].action == "run"  # upgrade step just above
    if not deploy_state_file.is_file():
        plan.add("deploy", "run", "never deployed (.deploy-state missing)")
    else:
        import json as _json
        try:
            state = _json.loads(deploy_state_file.read_text(encoding="utf-8"))
        except (OSError, _json.JSONDecodeError):
            state = {}
        deployed_platform = state.get("platform")
        if deployed_platform != plan.target_platform:
            plan.add(
                "deploy", "run",
                f"platform changed: deployed={deployed_platform} "
                f"→ target={plan.target_platform}",
            )
        elif upgrade_running:
            plan.add(
                "deploy", "run",
                "scaffold refreshed — IDE artefacts must be re-rendered",
            )
        else:
            plan.add("deploy", "skip", f"{deployed_platform} already deployed")

    _append_doctor(plan)
    return plan


def _append_doctor(plan: _Plan) -> None:
    plan.add("doctor", "run", "verification gate")


def _semver_newer(a: str, b: str) -> bool:
    """True iff *a* is a semver strictly newer than *b*.

    Non-numeric versions fall back to plain string inequality — we'd rather
    be conservative (trigger upgrade) than silently skip a real release
    just because someone typed "0.2.0rc1".

    Special case: when *b* is a placeholder like ``0.0.0-template`` (used
    in source-repo framework.json that hasn't been stamped with a real
    package version yet), do NOT treat any installed version as "newer".
    Otherwise dogfood developers always see a phantom upgrade plan because
    their installed package (e.g. 0.1.12) compares > 0.0.0. The placeholder
    semantically means "this scaffold has not been materialised by setup
    yet; defer the comparison until it has".
    """
    import re

    if b.startswith("0.0.0-"):
        return False

    tup_re = re.compile(r"^(\d+)\.(\d+)\.(\d+)")
    ma = tup_re.match(a)
    mb = tup_re.match(b)
    if ma is None or mb is None:
        return a != b
    return tuple(int(x) for x in ma.groups()) > tuple(int(x) for x in mb.groups())


# ---- presentation ----

_ACTION_STYLE = {
    "run": ("•", "green"),
    "skip": ("○", "cyan"),
    "error": ("✗", "red"),
}


def _print_plan(plan: _Plan, *, dry_run: bool) -> None:
    header = "Plan (dry-run):" if dry_run else "Plan:"
    click.echo(header)
    for step in plan.steps:
        mark, color = _ACTION_STYLE.get(step.action, ("?", "white"))
        click.echo(
            f"  {click.style(mark, fg=color)} {step.name:<8} "
            f"{step.action:<5} — {step.reason}"
        )
    if plan.target_platform and not plan.error:
        click.echo(f"\n  target platform: {plan.target_platform}")
    if plan.error:
        click.secho(f"\n  blocking: {plan.error}", fg="red", err=True)


def _confirm_plan(plan: _Plan) -> bool:
    return click.confirm(
        f"Run {sum(1 for s in plan.steps if s.action == 'run')} step(s)?",
        default=True,
    )


# ---- execution ----

def _execute_plan(
    ctx: click.Context,
    cfg,
    plan: _Plan,
    *,
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

    bus = EventBus()

    step_by_name = {s.name: s for s in plan.steps}

    click.echo("")

    setup_step = step_by_name.get("setup")
    if setup_step is not None and setup_step.action == "run":
        click.echo(f"[setup] delegating to `cataforge setup --platform {plan.target_platform}`")
        # Delegate to setup_command so any new side effect added there
        # (e.g. --emit-env-block, additional checks) is automatically
        # picked up by bootstrap. We pass --no-deploy explicitly: bootstrap
        # owns the deploy step and we don't want setup to chain it.
        from cataforge.cli.setup_cmd import setup_command

        ctx.invoke(
            setup_command,
            platform=plan.target_platform,
            with_penpot=False,
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
        click.echo(f"[upgrade] refreshing .cataforge/ at {cfg.paths.cataforge_dir}")
        written, _, backup = copy_scaffold_to(
            cfg.paths.cataforge_dir, force=True,
        )
        cfg.reload()
        if backup is not None:
            click.echo(f"  backup: {backup.relative_to(cfg.paths.cataforge_dir.parent)}")
        click.echo(f"  wrote {len(written)} file(s)")

    deploy_step = step_by_name.get("deploy")
    if deploy_step is not None and deploy_step.action == "run":
        target = plan.target_platform or cfg.runtime_platform
        click.echo(f"[deploy] rendering artefacts for {target}")
        from cataforge.deploy.deployer import Deployer

        deployer = Deployer(cfg, bus)
        actions = deployer.deploy(target)
        for action in actions:
            click.echo(f"  {action}")
        bus.emit(FRAMEWORK_SETUP, {"platform": target, "bootstrap": True})

    # First-time bootstrap previously left docs/.doc-index.json absent
    # forever, so doctor's orphan check silently skipped and `cataforge
    # docs load` was invisible to the user. Auto-generate the first
    # index when docs/ exists with markdown content; non-blocking on
    # failure so a malformed doc doesn't strand bootstrap mid-flow.
    docs_dir = cfg.paths.root / "docs"
    if docs_dir.is_dir() and any(docs_dir.rglob("*.md")):
        click.echo("\n[docs-index] generating docs/.doc-index.json")
        from cataforge.docs.indexer import main as indexer_main

        try:
            rc = indexer_main(["--project-root", str(cfg.paths.root)])
            if rc != 0:
                click.secho(
                    f"  WARN docs index returned {rc} — see warnings above; "
                    "fix front matter then rerun `cataforge docs index`.",
                    fg="yellow",
                    err=True,
                )
        except Exception as e:  # noqa: BLE001
            click.secho(
                f"  WARN docs index crashed: {e} — bootstrap continuing.",
                fg="yellow",
                err=True,
            )

    doctor_step = step_by_name.get("doctor")
    if skip_doctor:
        click.echo("\n[doctor] skipped (--skip-doctor)")
        return
    if doctor_step is not None and doctor_step.action == "run":
        click.echo("\n[doctor] running diagnostics")
        from cataforge.cli.doctor_cmd import doctor_command

        ctx.invoke(doctor_command)
