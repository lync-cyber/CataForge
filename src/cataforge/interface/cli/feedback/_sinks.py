"""Shared sink plumbing for the ``cataforge feedback`` bundle subcommands —
the --print / --out / --clip / --gh flags and their emit machinery."""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

import click

from cataforge.application.feedback import iter_clipboard_commands
from cataforge.core.errors import ExternalToolError
from cataforge.interface.cli._support.helpers import get_config_manager
from cataforge.utils.run_subprocess import run as run_proc

F = TypeVar("F", bound=Callable[..., Any])


def _sink_options(func: F) -> F:
    """Attach the four mutually-exclusive --print / --out / --clip / --gh flags
    plus the shared --title / --include-paths / --notes / --quiet."""
    func = click.option(
        "--print",
        "print_to_stdout",
        is_flag=True,
        default=False,
        help="Write the rendered body to stdout (default sink when none given).",
    )(func)
    func = click.option(
        "--out",
        "out_path",
        type=click.Path(dir_okay=False, writable=True, path_type=Path),
        default=None,
        help="Write the body to PATH (relative resolves under the project root).",
    )(func)
    func = click.option(
        "--clip",
        "to_clipboard",
        is_flag=True,
        default=False,
        help="Copy the body to the system clipboard (pbcopy / xclip / wl-copy / clip).",
    )(func)
    func = click.option(
        "--gh",
        "to_gh",
        is_flag=True,
        default=False,
        help="Open a GitHub issue via `gh issue create` (requires gh + auth).",
    )(func)
    func = click.option(
        "--title",
        "title",
        default=None,
        help="Issue title (default: synthesised from kind + summary).",
    )(func)
    func = click.option(
        "--summary",
        "summary",
        default=None,
        help="One-paragraph summary. Reads from stdin (until EOF) when omitted.",
    )(func)
    func = click.option(
        "--notes",
        "notes",
        default="",
        help="Extra free-form text appended under '## Additional notes'.",
    )(func)
    func = click.option(
        "--include-paths",
        "include_paths",
        is_flag=True,
        default=False,
        help="Disable the ~/<project> path redaction (use only for private filings).",
    )(func)
    func = click.option(
        "--quiet",
        "quiet",
        is_flag=True,
        default=False,
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
        raise click.UsageError("--print / --out / --clip / --gh are mutually exclusive.")
    if chosen == 0:
        print_to_stdout = True

    if print_to_stdout:
        click.echo(body, nl=False)
        return
    if out_path is not None:
        target = out_path if out_path.is_absolute() else project_root / out_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body)
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
        upstream_repo = (cfg.upgrade_source or {}).get("repo")
        url = _to_gh(
            body,
            title=title,
            labels=labels,
            fallback_on_missing_label=fallback,
            repo=str(upstream_repo) if upstream_repo else None,
        )
        # Always print the URL to stdout so CI / pipelines can capture it
        # even with --quiet.
        click.echo(url)


def _to_clipboard(body: str) -> None:
    for cmd in iter_clipboard_commands():
        if shutil.which(cmd[0]):
            result = run_proc(cmd, input=body)
            if result.returncode != 0:
                raise ExternalToolError(f"clipboard tool {cmd[0]} exited {result.returncode}")
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
    repo: str | None = None,
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
    if repo:
        # Explicit target: feedback always files against the upstream repo,
        # not whatever git remote the project directory happens to have.
        base_cmd.extend(["-R", repo])

    def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        return run_proc(cmd, input=body)

    cmd = list(base_cmd)
    for lbl in label_list:
        cmd.extend(["--label", lbl])
    result = _run(cmd)
    if result.returncode != 0:
        stderr = result.stderr or result.stdout or ""
        if label_list and fallback_on_missing_label and _looks_like_missing_label_error(stderr):
            click.secho(
                f"WARN: upstream repo rejected label(s) {label_list!r}; "
                "retrying without --label. Run `cataforge feedback ensure-labels` "
                "to create them on the upstream repo if you have push access.",
                fg="yellow",
                err=True,
            )
            result = _run(base_cmd)
            if result.returncode != 0:
                raise ExternalToolError(
                    f"gh issue create failed even after dropping --label "
                    f"(exit {result.returncode}):\n{result.stderr or result.stdout}"
                )
        else:
            raise ExternalToolError(f"gh issue create failed (exit {result.returncode}):\n{stderr}")
    return (result.stdout or "").strip()
