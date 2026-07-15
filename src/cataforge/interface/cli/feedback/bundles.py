"""cataforge feedback bundle assemblers — bug, suggest, correction-export."""

from __future__ import annotations

from pathlib import Path

import click

from cataforge.application.feedback import (
    RETRO_TRIGGER_UPSTREAM_GAP_DEFAULT,
    UPSTREAM_GAP,
    assemble_bug,
    assemble_correction_export,
    assemble_suggestion,
    upstream_gap_count,
)
from cataforge.core.errors import CataforgeError
from cataforge.interface.cli._support.helpers import resolve_root
from cataforge.interface.cli.feedback import feedback_group
from cataforge.interface.cli.feedback._sinks import _emit, _resolve_summary, _sink_options


@feedback_group.command("bug")
@_sink_options
@click.option(
    "--since",
    "since",
    default=None,
    help="Only include EVENT-LOG / corrections at or after this date (YYYY-MM-DD).",
)
@click.option(
    "--event-limit",
    "event_limit",
    type=int,
    default=20,
    show_default=True,
    help="Max number of recent EVENT-LOG records to include (0 = all).",
)
@click.option(
    "--skip-framework-review",
    "skip_framework_review",
    is_flag=True,
    default=False,
    help="Don't run `framework-review` (faster; useful when the scaffold is broken).",
)
def bug_command(
    print_to_stdout: bool,
    out_path: Path | None,
    to_clipboard: bool,
    to_gh: bool,
    title: str | None,
    summary: str | None,
    notes: str,
    include_paths: bool,
    quiet: bool,
    since: str | None,
    event_limit: int,
    skip_framework_review: bool,
) -> None:
    """Render a bug-report bundle (env + doctor + events + upstream-gap)."""
    project_root = resolve_root()
    summary_text = _resolve_summary(summary)
    final_title = title or f"bug: {summary_text.splitlines()[0][:60]}"
    try:
        _payload, body = assemble_bug(
            project_root,
            title=final_title,
            summary=summary_text,
            user_notes=notes,
            since=since,
            event_limit=event_limit,
            include_paths=include_paths,
            skip_framework_review=skip_framework_review,
        )
    except Exception as e:
        raise CataforgeError(f"failed to assemble bug bundle: {e}") from e
    _emit(
        body,
        project_root=project_root,
        print_to_stdout=print_to_stdout,
        out_path=out_path,
        to_clipboard=to_clipboard,
        to_gh=to_gh,
        title=final_title,
        quiet=quiet,
        gh_kind="bug",
    )


@feedback_group.command("suggest")
@_sink_options
def suggest_command(
    print_to_stdout: bool,
    out_path: Path | None,
    to_clipboard: bool,
    to_gh: bool,
    title: str | None,
    summary: str | None,
    notes: str,
    include_paths: bool,
    quiet: bool,
) -> None:
    """Render a feature / improvement suggestion bundle."""
    project_root = resolve_root()
    summary_text = _resolve_summary(summary)
    final_title = title or f"feedback: {summary_text.splitlines()[0][:60]}"
    try:
        _payload, body = assemble_suggestion(
            project_root,
            title=final_title,
            summary=summary_text,
            user_notes=notes,
            include_paths=include_paths,
        )
    except Exception as e:
        raise CataforgeError(f"failed to assemble suggestion bundle: {e}") from e
    _emit(
        body,
        project_root=project_root,
        print_to_stdout=print_to_stdout,
        out_path=out_path,
        to_clipboard=to_clipboard,
        to_gh=to_gh,
        title=final_title,
        quiet=quiet,
        gh_kind="suggest",
    )


@feedback_group.command("correction-export")
@_sink_options
@click.option(
    "--since",
    "since",
    default=None,
    help="Only include corrections dated at or after YYYY-MM-DD.",
)
@click.option(
    "--threshold",
    "threshold",
    type=int,
    default=RETRO_TRIGGER_UPSTREAM_GAP_DEFAULT,
    show_default=True,
    help=("Minimum upstream-gap correction count required before export. Use 0 to always export."),
)
def correction_export_command(
    print_to_stdout: bool,
    out_path: Path | None,
    to_clipboard: bool,
    to_gh: bool,
    title: str | None,
    summary: str | None,
    notes: str,
    include_paths: bool,
    quiet: bool,
    since: str | None,
    threshold: int,
) -> None:
    """Aggregate `upstream-gap` corrections into an upstream-bound issue draft.

    Threshold mirrors RETRO_TRIGGER_SELF_CAUSED for the upstream channel:
    if you have ≥ N upstream-gap signals on disk, opening an issue is
    worth more than logging another one in CORRECTIONS-LOG.
    """
    project_root = resolve_root()
    count = upstream_gap_count(project_root)
    if count == 0:
        raise CataforgeError(
            f"No `{UPSTREAM_GAP}` corrections found in CORRECTIONS-LOG. "
            "Record one first with `cataforge correction record --deviation "
            f"{UPSTREAM_GAP} ...`."
        )
    if count < threshold:
        raise CataforgeError(
            f"Only {count} `{UPSTREAM_GAP}` correction(s) on file (threshold={threshold}). "
            "Lower with --threshold 0 to export anyway."
        )

    summary_text = _resolve_summary(
        summary or f"Aggregated {count} `{UPSTREAM_GAP}` correction signal(s) from downstream."
    )
    final_title = title or f"feedback: {count} upstream-gap signals"
    try:
        _payload, body = assemble_correction_export(
            project_root,
            title=final_title,
            summary=summary_text,
            since=since,
            user_notes=notes,
            include_paths=include_paths,
        )
    except Exception as e:
        raise CataforgeError(f"failed to assemble correction-export bundle: {e}") from e
    _emit(
        body,
        project_root=project_root,
        print_to_stdout=print_to_stdout,
        out_path=out_path,
        to_clipboard=to_clipboard,
        to_gh=to_gh,
        title=final_title,
        quiet=quiet,
        gh_kind="correction-export",
    )
