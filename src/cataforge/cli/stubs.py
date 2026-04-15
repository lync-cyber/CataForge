"""Shared messaging for CLI subcommands that are not implemented yet."""

from __future__ import annotations

import click

STUB_EXIT_CODE = 2

_ISSUES_URL = "https://github.com/lync-cyber/CataForge/issues"


def exit_not_implemented(
    feature: str,
    detail: str = "",
    *,
    milestone: str | None = None,
    workaround: str | None = None,
) -> None:
    """Print a consistent, actionable stub message and exit with code 2.

    Args:
        feature: Human-readable feature name (Chinese).
        detail: Optional context (e.g. the argument the user passed).
        milestone: Target roadmap version (e.g. ``"v0.2"``).
        workaround: A one-line workaround / alternative path the user can take today.
    """
    lines = [f"✖ {feature} 尚未实现。"]
    if detail:
        lines.append(f"  {detail}")
    if milestone:
        lines.append(f"  计划在 {milestone} 提供。")
    if workaround:
        lines.append(f"  当前可用方案：{workaround}")
    lines.append(f"  需求反馈：{_ISSUES_URL}")
    click.secho("\n".join(lines), fg="yellow", err=True)
    raise SystemExit(STUB_EXIT_CODE)
