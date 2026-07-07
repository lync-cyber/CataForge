"""cataforge unattended — headless building-loop driver.

Cross-platform outer shell for one frozen sprint's building. Loop logic lives
in :mod:`cataforge.runtime.unattended`; this is the Click surface + constant
resolution from ``framework.json#/constants``.
"""

from __future__ import annotations

from pathlib import Path

import click

from cataforge.adapter.platform.registry import read_execution_mode
from cataforge.application.unattended_preflight import (
    preflight_frozen_upstream,
    preflight_prototype_brief,
)
from cataforge.core.config import ConfigManager
from cataforge.core.paths import find_project_root
from cataforge.interface.cli.helpers import resolve_project_dir
from cataforge.interface.cli.main import cli
from cataforge.runtime.unattended import (
    EXIT_CIRCUIT,
    EXIT_COMPLETE,
    EXIT_MAX_ITERATIONS,
    EXIT_PREFLIGHT,
    prototype_target,
    run_building_loop,
    sprint_target,
)

_OUTCOME_MESSAGE = {
    EXIT_COMPLETE: "✅ {sprint} 完成，feature 分支待 PR，人工晨检后合并。",
    EXIT_PREFLIGHT: "拒绝：禁止在 main 上跑无人循环。",
    EXIT_CIRCUIT: "⛔ 熔断，停止，等待人工。",
    EXIT_MAX_ITERATIONS: "⏹ 达迭代上限，{sprint} 未完成，停止，等待人工。",
}


@cli.group("unattended")
def unattended_group() -> None:
    """Headless building-loop for a frozen sprint (feature branch only)."""


@unattended_group.command("build")
@click.argument("sprint", required=False)
@click.option(
    "--max-iterations",
    type=int,
    default=None,
    help="Override UNATTENDED_LOOP_MAX_ITERATIONS for this run.",
)
@click.option(
    "--project-root",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    default=None,
    help="Override project root (default: walk up for .cataforge/).",
)
@click.pass_context
def unattended_build(
    ctx: click.Context,
    sprint: str | None,
    max_iterations: int | None,
    project_root: Path | None,
) -> None:
    """Drive a build target until sprint_complete / circuit_open / cap.

    Auto-detects the execution mode: agile-prototype builds the brief's task
    cards (SPRINT is unused), every other mode builds SPRINT's dev-plan cards.

    Exit codes: 0 complete · 3 circuit-open · 4 hit cap · 5 pre-flight refusal
    (5, not 2, so it's distinct from Click's own usage error).
    Never merges / deploys; runs only on a feature branch inside a sandbox.
    """
    root = project_root or resolve_project_dir() or find_project_root()

    # Auto-detect target from the declared execution mode (single source of
    # truth in the instruction file) — no flag to mismatch against reality.
    if read_execution_mode(root) == "agile-prototype":
        if sprint:
            click.echo(
                f"提示：agile-prototype 模式忽略 SPRINT 参数（{sprint}），"
                "building 目标为 brief#tasks",
                err=True,
            )
        target = prototype_target()
        refusal = preflight_prototype_brief(root)
    else:
        if not sprint:
            raise click.UsageError("非 agile-prototype 模式需指定 SPRINT 参数（如 sprint-2）")
        target = sprint_target(sprint)
        refusal = preflight_frozen_upstream(root, sprint)

    # Frozen-upstream gate: refuse before spending an overnight budget when the
    # plan isn't present / ready. run_building_loop still does its own fail-closed
    # branch check as the load-bearing guard.
    if refusal is not None:
        click.echo(f"拒绝：{refusal}", err=True)
        ctx.exit(EXIT_PREFLIGHT)

    cfg = ConfigManager(root)

    def _c(name: str, default: int) -> int:
        return int(cfg.get_constant(name, default))

    code = run_building_loop(
        root,
        target,
        max_iterations=max_iterations or _c("UNATTENDED_LOOP_MAX_ITERATIONS", 30),
        stagnation_threshold=_c("UNATTENDED_STAGNATION_THRESHOLD", 3),
        card_revision_ceiling=_c("UNATTENDED_CARD_REVISION_CEILING", 3),
        iter_timeout_sec=float(_c("UNATTENDED_LOOP_ITER_TIMEOUT_SEC", 1800)),
        ratelimit_wait_sec=float(_c("UNATTENDED_RATELIMIT_WAIT_SEC", 300)),
    )
    message = _OUTCOME_MESSAGE.get(code, f"未知退出码 {code}")
    click.echo(message.format(sprint=target.label), err=code != EXIT_COMPLETE)
    ctx.exit(code)
