"""Doctor reporter for deployed capability/enforcement state."""

from __future__ import annotations

from typing import TYPE_CHECKING

import click

from cataforge.runtime.deploy.capability_report import (
    load_capability_report,
    summarize_capability_report,
)
from cataforge.runtime.deploy.manifest import platform_capability_report_path

if TYPE_CHECKING:
    from cataforge.core.config import ConfigManager


def report_capability_health(cfg: ConfigManager, platforms: list[str] | None = None) -> None:
    for platform_id in platforms or [cfg.default_platform]:
        path = platform_capability_report_path(cfg.paths.root, platform_id)
        report = load_capability_report(path)
        if report is None:
            click.echo(f"  {platform_id}: no capability report (run `cataforge deploy`)")
            continue

        summary = summarize_capability_report(report)
        click.echo(
            f"  {platform_id}: tool_policy={summary['tool_policy']}, "
            f"conditional={summary['conditional']}, "
            f"unenforced_agents={summary['unenforced_agents']}"
        )
