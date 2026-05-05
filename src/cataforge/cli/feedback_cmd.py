"""``cataforge feedback`` — package downstream signals into an upstream-ready bundle.

Three subcommands sharing one assembler (``cataforge.core.feedback``):

* ``feedback bug``                — diagnostics + doctor + framework-review summary
* ``feedback suggest``            — proposal scaffold (lighter; no doctor noise)
* ``feedback correction-export``  — aggregate ``upstream-gap`` corrections only

Each subcommand renders a single markdown body and emits it via one of
four mutually-exclusive sinks (``--print`` is the default):

    --print           write to stdout (pipe-friendly)
    --out PATH        write to a file (relative resolves under project root)
    --clip            push to the system clipboard via pbcopy / wl-copy / xclip / clip
    --gh              shell out to `gh issue create` (requires gh on PATH +
                      authenticated; passes the body via stdin so no temp file
                      is left on disk)

Privacy: paths are redacted to ``<project>`` / ``~`` by default. Pass
``--include-paths`` only when filing internally.

Exit codes follow the project convention (see ``cli/errors.py``):
* 0 — body produced successfully
* 1 — assembler / sink failed (missing gh, write failed, etc.)
* 2 — Click usage error
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

import click

from cataforge.cli.errors import CataforgeError, ExternalToolError
from cataforge.cli.helpers import get_config_manager, resolve_root
from cataforge.cli.main import cli
from cataforge.core.feedback import (
    RETRO_TRIGGER_UPSTREAM_GAP_DEFAULT,
    UPSTREAM_GAP,
    assemble_bug,
    assemble_correction_export,
    assemble_suggestion,
    iter_clipboard_commands,
    upstream_gap_count,
)

F = TypeVar("F", bound=Callable[..., Any])


@cli.group("feedback")
def feedback_group() -> None:
    """Bundle local signals into upstream-ready feedback (bug / suggest / corrections).

    Aggregates ``cataforge doctor`` + recent EVENT-LOG + ``upstream-gap``
    corrections + ``framework-review`` Layer 1 fails into a single markdown
    body, then emits it via stdout / file / clipboard / `gh issue create`.

    Designed to close the loop from downstream usage back to CataForge
    upstream — pair with ``correction record --deviation upstream-gap``
    when you spot an upstream baseline that was wrong for your context.
    """


# ─── shared options ───────────────────────────────────────────────────────────


def _sink_options(func: F) -> F:
    """Attach the four mutually-exclusive --print / --out / --clip / --gh flags
    plus the shared --title / --include-paths / --notes / --quiet."""
    func = click.option(
        "--print", "print_to_stdout", is_flag=True, default=False,
        help="Write the rendered body to stdout (default sink when none given).",
    )(func)
    func = click.option(
        "--out", "out_path",
        type=click.Path(dir_okay=False, writable=True, path_type=Path),
        default=None,
        help="Write the body to PATH (relative resolves under the project root).",
    )(func)
    func = click.option(
        "--clip", "to_clipboard", is_flag=True, default=False,
        help="Copy the body to the system clipboard (pbcopy / xclip / wl-copy / clip).",
    )(func)
    func = click.option(
        "--gh", "to_gh", is_flag=True, default=False,
        help="Open a GitHub issue via `gh issue create` (requires gh + auth).",
    )(func)
    func = click.option(
        "--title", "title", default=None,
        help="Issue title (default: synthesised from kind + summary).",
    )(func)
    func = click.option(
        "--summary", "summary", default=None,
        help="One-paragraph summary. Reads from stdin (until EOF) when omitted.",
    )(func)
    func = click.option(
        "--notes", "notes", default="",
        help="Extra free-form text appended under '## Additional notes'.",
    )(func)
    func = click.option(
        "--include-paths", "include_paths", is_flag=True, default=False,
        help="Disable the ~/<project> path redaction (use only for private filings).",
    )(func)
    func = click.option(
        "--quiet", "quiet", is_flag=True, default=False,
        help="Suppress non-essential output (sink confirmations).",
    )(func)
    return func


def _resolve_summary(summary: str | None) -> str:
    """``--summary`` wins; otherwise read stdin (terminal-detached pipes only)."""
    if summary is not None:
        return summary.strip()
    if not click.get_text_stream("stdin").isatty():
        text = click.get_text_stream("stdin").read().strip()
        if text:
            return text
    return "(no summary provided)"


def _emit(
    body: str,
    *,
    project_root: Path,
    print_to_stdout: bool,
    out_path: Path | None,
    to_clipboard: bool,
    to_gh: bool,
    title: str,
    quiet: bool,
    gh_kind: str | None = None,
) -> None:
    """Resolve sinks. Mutually exclusive; default = --print.

    ``gh_kind`` (one of "bug" / "suggest" / "correction-export") drives label
    resolution via ``ConfigManager.feedback_gh_labels``; the prior
    ``gh_label`` arg has been retired in favour of config-driven labels so
    the upstream repo's labelset is no longer hardcoded.
    """
    chosen = sum(bool(x) for x in (print_to_stdout, out_path, to_clipboard, to_gh))
    if chosen > 1:
        raise click.UsageError(
            "--print / --out / --clip / --gh are mutually exclusive."
        )
    if chosen == 0:
        print_to_stdout = True

    if print_to_stdout:
        click.echo(body, nl=False)
        return
    if out_path is not None:
        target = out_path if out_path.is_absolute() else project_root / out_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
        if not quiet:
            click.secho(f"Wrote {target}", fg="green", err=True)
        return
    if to_clipboard:
        _to_clipboard(body)
        if not quiet:
            click.secho("Copied feedback body to clipboard.", fg="green", err=True)
        return
    if to_gh:
        cfg = get_config_manager()
        labels = cfg.feedback_gh_labels(gh_kind) if gh_kind else []
        fallback = cfg.feedback_fallback_on_missing_label()
        url = _to_gh(
            body,
            title=title,
            labels=labels,
            fallback_on_missing_label=fallback,
        )
        # Always print the URL to stdout so CI / pipelines can capture it
        # even with --quiet.
        click.echo(url)


def _to_clipboard(body: str) -> None:
    for cmd in iter_clipboard_commands():
        if shutil.which(cmd[0]):
            try:
                subprocess.run(cmd, input=body, text=True, check=True, encoding="utf-8")
            except subprocess.CalledProcessError as e:
                raise ExternalToolError(
                    f"clipboard tool {cmd[0]} exited {e.returncode}"
                ) from None
            return
    raise ExternalToolError(
        "no clipboard tool found on PATH (tried pbcopy / wl-copy / xclip / xsel / clip). "
        "Install one or use --print / --out PATH instead."
    )


_LABEL_NOT_FOUND_PATTERNS = (
    "could not add label",
    "not found",
    "label does not exist",
    "label not found",
)


def _looks_like_missing_label_error(stderr: str) -> bool:
    """Detect ``gh issue create --label X`` failure caused by label X not existing.

    GitHub's API rejects the call with a 422 "Validation Failed" + message
    "Could not add label: ..." when the label hasn't been created on the repo.
    ``gh`` surfaces this via stderr; we match a few substrings rather than
    parsing JSON since the exact wording has shifted across ``gh`` releases.
    """
    if not stderr:
        return False
    lower = stderr.lower()
    return any(pat in lower for pat in _LABEL_NOT_FOUND_PATTERNS)


def _to_gh(
    body: str,
    *,
    title: str,
    labels: list[str] | None = None,
    fallback_on_missing_label: bool = True,
    label: str | None = None,  # deprecated, comma-separated form
) -> str:
    """Spawn `gh issue create --body-file - < body` and return the issue URL.

    The body is fed via stdin so we never write it to a temp file (avoids
    leaking ``--include-paths`` content to disk in CI runners). Caller is
    responsible for handling the resulting URL.

    When ``labels`` is non-empty and the upstream repo lacks one or more of
    those labels (gh exits 1 with a "Could not add label" message), we
    transparently retry without ``--label`` and warn on stderr so the issue
    still lands. Set ``fallback_on_missing_label=False`` to disable.
    """
    if not shutil.which("gh"):
        raise ExternalToolError(
            "GitHub CLI `gh` not found on PATH. Install from https://cli.github.com/ "
            "or use --print / --clip and paste manually."
        )

    # Back-compat: callers used to pass ``label="feedback,bug"`` (comma form).
    label_list: list[str] = []
    if labels:
        label_list = list(labels)
    elif label:
        label_list = [item.strip() for item in label.split(",") if item.strip()]

    base_cmd = ["gh", "issue", "create", "--title", title, "--body-file", "-"]

    def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            cmd,
            input=body,
            text=True,
            capture_output=True,
            check=True,
            encoding="utf-8",
        )

    cmd = list(base_cmd)
    for lbl in label_list:
        cmd.extend(["--label", lbl])
    try:
        result = _run(cmd)
    except subprocess.CalledProcessError as e:
        stderr = e.stderr or e.stdout or ""
        if (
            label_list
            and fallback_on_missing_label
            and _looks_like_missing_label_error(stderr)
        ):
            click.secho(
                f"WARN: upstream repo rejected label(s) {label_list!r}; "
                "retrying without --label. Run `cataforge feedback ensure-labels` "
                "to create them on the upstream repo if you have push access.",
                fg="yellow",
                err=True,
            )
            try:
                result = _run(base_cmd)
            except subprocess.CalledProcessError as e2:
                raise ExternalToolError(
                    f"gh issue create failed even after dropping --label "
                    f"(exit {e2.returncode}):\n{e2.stderr or e2.stdout}"
                ) from None
        else:
            raise ExternalToolError(
                f"gh issue create failed (exit {e.returncode}):\n{stderr}"
            ) from None
    return (result.stdout or "").strip()


# ─── feedback ensure-labels ───────────────────────────────────────────────────


@feedback_group.command("ensure-labels")
@click.option(
    "--repo", "repo", default=None,
    help="Target repo (owner/name). Defaults to the upstream from "
         "`framework.json#upgrade.source.repo`.",
)
@click.option(
    "--dry-run", "dry_run", is_flag=True, default=False,
    help="Print what would be created without calling `gh label create`.",
)
def ensure_labels_command(repo: str | None, dry_run: bool) -> None:
    """Create the GitHub labels declared in `framework.json#feedback.gh.labels`
    on the upstream repo, idempotently.

    Use this once when bootstrapping a fork or when adding a new feedback
    label to `framework.json` — it skips labels that already exist.
    Requires `gh` on PATH and push access to the target repo.
    """
    if not shutil.which("gh"):
        raise ExternalToolError(
            "GitHub CLI `gh` not found on PATH. Install from https://cli.github.com/"
        )
    cfg = get_config_manager()
    if repo is None:
        upstream = cfg.upgrade_source
        owner_repo = upstream.get("repo")
        if not owner_repo:
            raise CataforgeError(
                "framework.json#upgrade.source.repo is not configured; "
                "pass --repo owner/name explicitly."
            )
        repo = str(owner_repo)

    # Collect every distinct label declared across feedback kinds.
    labels: set[str] = set()
    for kind in ("bug", "suggest", "correction-export"):
        for lbl in cfg.feedback_gh_labels(kind):
            labels.add(lbl)
    if not labels:
        click.echo("No labels declared in framework.json#feedback.gh.labels.")
        return

    # gh label list returns existing labels — used to skip duplicates so the
    # call is idempotent (gh label create exits 1 on duplicate).
    existing: set[str] = set()
    try:
        listing = subprocess.run(
            ["gh", "label", "list", "-R", repo, "--limit", "100", "--json", "name"],
            text=True,
            capture_output=True,
            check=True,
            encoding="utf-8",
        )
        import json as _json
        for entry in _json.loads(listing.stdout or "[]"):
            existing.add(entry.get("name", ""))
    except subprocess.CalledProcessError as e:
        raise ExternalToolError(
            f"gh label list failed (exit {e.returncode}):\n{e.stderr or e.stdout}"
        ) from None

    to_create = sorted(labels - existing)
    already_there = sorted(labels & existing)

    if already_there:
        click.echo(f"Already present on {repo}: {', '.join(already_there)}")
    if not to_create:
        click.echo("Nothing to do — all configured labels exist.")
        return

    click.echo(f"Will create on {repo}: {', '.join(to_create)}")
    if dry_run:
        click.echo("(dry-run; pass without --dry-run to apply)")
        return

    for lbl in to_create:
        try:
            subprocess.run(
                ["gh", "label", "create", lbl, "-R", repo],
                text=True,
                capture_output=True,
                check=True,
                encoding="utf-8",
            )
            click.secho(f"  + {lbl}", fg="green")
        except subprocess.CalledProcessError as e:
            click.secho(
                f"  ! {lbl} — gh label create failed: {e.stderr or e.stdout}",
                fg="red",
                err=True,
            )


# ─── feedback bug ─────────────────────────────────────────────────────────────


@feedback_group.command("bug")
@_sink_options
@click.option(
    "--since", "since", default=None,
    help="Only include EVENT-LOG / corrections at or after this date (YYYY-MM-DD).",
)
@click.option(
    "--event-limit", "event_limit", type=int, default=20, show_default=True,
    help="Max number of recent EVENT-LOG records to include (0 = all).",
)
@click.option(
    "--skip-framework-review", "skip_framework_review",
    is_flag=True, default=False,
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
        raise CataforgeError(f"failed to assemble bug bundle: {e}") from None
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


# ─── feedback suggest ─────────────────────────────────────────────────────────


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
        raise CataforgeError(f"failed to assemble suggestion bundle: {e}") from None
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


# ─── feedback correction-export ───────────────────────────────────────────────


@feedback_group.command("correction-export")
@_sink_options
@click.option(
    "--since", "since", default=None,
    help="Only include corrections dated at or after YYYY-MM-DD.",
)
@click.option(
    "--threshold", "threshold", type=int,
    default=RETRO_TRIGGER_UPSTREAM_GAP_DEFAULT, show_default=True,
    help=(
        "Minimum upstream-gap correction count required before export. "
        "Use 0 to always export."
    ),
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
        summary
        or f"Aggregated {count} `{UPSTREAM_GAP}` correction signal(s) from downstream."
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
        raise CataforgeError(
            f"failed to assemble correction-export bundle: {e}"
        ) from None
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
