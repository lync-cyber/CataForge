"""cataforge upgrade — framework upgrade management."""

from __future__ import annotations

import click

from cataforge.cli.main import cli
from cataforge.cli.stubs import exit_not_implemented


@cli.group("upgrade")
def upgrade_group() -> None:
    """Manage framework upgrades."""


@upgrade_group.command("check")
def upgrade_check() -> None:
    """Check if a newer version is available."""
    from cataforge.core.config import ConfigManager

    cfg = ConfigManager()
    source = cfg.upgrade_source
    click.echo(f"Current version: {cfg.version}")
    click.echo(f"Upgrade source: {source.get('repo', 'not configured')}")
    exit_not_implemented(
        "远程版本检查",
        milestone="v0.2",
        workaround="pip install --upgrade cataforge  # 或 uv tool upgrade cataforge",
    )


@upgrade_group.command("apply")
@click.option("--dry-run", is_flag=True, help="Show what would change without applying.")
def upgrade_apply(dry_run: bool) -> None:
    """Apply available upgrade."""
    exit_not_implemented(
        "升级应用",
        f"(--dry-run={dry_run})",
        milestone="v0.2",
        workaround=(
            "pip install --upgrade cataforge && cataforge setup --force-scaffold"
        ),
    )


@upgrade_group.command("verify")
def upgrade_verify() -> None:
    """Verify current installation integrity."""
    from cataforge.core.config import ConfigManager

    cfg = ConfigManager()
    fw = cfg.load()
    checks = fw.get("migration_checks", [])
    click.echo(f"Found {len(checks)} migration checks.")
    exit_not_implemented(
        "迁移检查执行",
        milestone="v0.2",
        workaround="cataforge doctor  # 基础健康检查已可用",
    )
