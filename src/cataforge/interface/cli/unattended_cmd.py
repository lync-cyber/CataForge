"""cataforge unattended — headless building-loop driver.

Cross-platform outer shell for one frozen sprint's building. Loop logic lives
in :mod:`cataforge.runtime.unattended`; this is the Click surface + constant
resolution from ``framework.json#/constants``.
"""

from __future__ import annotations

import os
from pathlib import Path

import click

from cataforge.core.config import ConfigManager
from cataforge.core.paths import find_project_root
from cataforge.interface.cli.helpers import resolve_project_dir
from cataforge.interface.cli.main import cli
from cataforge.runtime.unattended import (
    EXIT_CIRCUIT,
    EXIT_COMPLETE,
    EXIT_MAX_ITERATIONS,
    EXIT_PREFLIGHT,
    run_building_loop,
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
@click.argument("sprint")
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
    sprint: str,
    max_iterations: int | None,
    project_root: Path | None,
) -> None:
    """Drive SPRINT's building until sprint_complete / circuit_open / cap.

    Exit codes: 0 complete · 3 circuit-open · 4 hit cap · 5 pre-flight refusal
    (5, not 2, so it's distinct from Click's own usage error).
    Never merges / deploys; runs only on a feature branch inside a sandbox.
    """
    root = project_root or resolve_project_dir() or find_project_root()
    cfg = ConfigManager(root)

    def _c(name: str, default: int) -> int:
        return int(cfg.get_constant(name, default))

    code = run_building_loop(
        root,
        sprint,
        max_iterations=max_iterations or _c("UNATTENDED_LOOP_MAX_ITERATIONS", 30),
        stagnation_threshold=_c("UNATTENDED_STAGNATION_THRESHOLD", 3),
        card_revision_ceiling=_c("UNATTENDED_CARD_REVISION_CEILING", 3),
        same_error_ceiling=_c("UNATTENDED_SAME_ERROR_CEILING", 5),
        iter_timeout_sec=float(_c("UNATTENDED_LOOP_ITER_TIMEOUT_SEC", 1800)),
        ratelimit_wait_sec=float(os.environ.get("UNATTENDED_RATELIMIT_WAIT_SEC", "300")),
    )
    click.echo(_OUTCOME_MESSAGE[code].format(sprint=sprint), err=code != EXIT_COMPLETE)
    ctx.exit(code)
