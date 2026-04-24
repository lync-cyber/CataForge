"""Shared messaging for CLI subcommands that are not implemented yet.

Stub commands raise :class:`NotImplementedFeature` (exit code 70,
BSD sysexits ``EX_SOFTWARE``) so that:

* CI scripts can reliably distinguish "feature not shipped yet" from
  Click's own usage errors (exit 2) and from generic failures (exit 1).
* The message prefix matches every other error the CLI emits
  (``Error: …`` on stderr).
"""

from __future__ import annotations

from cataforge.cli.errors import EXIT_NOT_IMPLEMENTED, NotImplementedFeature

# Preserved as a public constant so tests and external tooling can import
# it without hard-coding the literal. Value is the exit code Click uses
# when :class:`NotImplementedFeature` propagates.
STUB_EXIT_CODE = EXIT_NOT_IMPLEMENTED

_ISSUES_URL = "https://github.com/lync-cyber/CataForge/issues"


def exit_not_implemented(
    feature: str,
    detail: str = "",
    *,
    milestone: str | None = None,
    workaround: str | None = None,
) -> None:
    """Raise :class:`NotImplementedFeature` with a consistent layout.

    Args:
        feature: Human-readable feature name (Chinese by convention).
        detail: Optional context (e.g. the argument the user passed).
        milestone: Target roadmap version (e.g. ``"v0.2"``).
        workaround: A one-line workaround / alternative path the user
            can take today.

    The call never returns — the raised exception triggers Click's
    stderr rendering and process exit (code 70).
    """
    lines = [f"{feature} 尚未实现。"]
    if detail:
        lines.append(f"  {detail}")
    if milestone:
        lines.append(f"  计划在 {milestone} 提供。")
    if workaround:
        lines.append(f"  当前可用方案：{workaround}")
    lines.append(f"  需求反馈：{_ISSUES_URL}")
    raise NotImplementedFeature("\n".join(lines))


__all__ = ["STUB_EXIT_CODE", "exit_not_implemented"]
