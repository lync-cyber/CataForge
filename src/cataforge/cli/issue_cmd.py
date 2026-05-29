"""``cataforge issue`` — upstream issue full-loop resolve.

Backs the ``framework-issue-resolve`` skill: closes the loop between
**downstream feedback** (`cataforge feedback bug --gh` puts a bundle into
a GitHub issue) and **upstream improvement** (SKILL-IMPROVE draft → fix
PR → templated close comment).

Two subcommands cover the automated bookends; the implementation step in
the middle is a normal dev workflow (branch + edit + PR), not CLI'd:

* ``triage`` — fetch, fact-check, render SKILL-IMPROVE drafts. Layer 1
  only (no AI calls). Verdicts: ``confirmed`` / ``already-fixed`` /
  ``needs-repro`` / ``unrelated`` (auto), plus ``wontfix-by-design``
  which the maintainer hand-edits onto a draft after deciding the report
  misreads an intentional design.
* ``close`` — templated wrapper around ``gh issue close --comment`` so
  every closure carries a uniform fixed/wontfix/already-fixed message.

Triage parser fields (best-effort regex, no AI):

* ``cataforge --version`` line → ``reported_version``
* ``framework-review`` FAIL bullets → candidate skill IDs
* ``upstream-gap`` correction blocks → candidate agent / skill IDs
* EVENT-LOG tail → no fact-check value yet, ignored

Drafts land under ``docs/reviews/triage/SKILL-IMPROVE-{target}-issue-{N}.md``
with ``status: triage-draft`` frontmatter so reflector / maintainer knows
to take a second look before promoting them.

``close`` actually calls ``gh issue close`` — the only externally visible
action in this module. Maintainer must invoke it explicitly per issue
(no batch loop). Use ``--dry-run`` to preview the comment.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import click

from cataforge.cli.helpers import get_config_manager, resolve_root
from cataforge.cli.main import cli
from cataforge.core.errors import CataforgeError, ExternalToolError
from cataforge.services.issue import (
    ParsedIssue,
    fetch_issues,
    list_local_agents,
    list_local_skills,
    parse_issue_body,
    render_close_comment,
    write_skill_improve_draft,
)
from cataforge.utils.run_subprocess import run as run_proc


@cli.group("issue")
def issue_group() -> None:
    """Resolve upstream GitHub issues end-to-end.

    Designed for CataForge maintainers / forked-repo owners to consume the
    output of `cataforge feedback bug --gh` from downstream users. Two
    subcommands cover the loop bookends:

    \b
    * `triage` — fetch + fact-check + render SKILL-IMPROVE drafts (no
      external action).
    * `close`  — templated `gh issue close --comment` after a fix PR
      lands or a wontfix decision is made.
    """


@issue_group.command("triage")
@click.option(
    "--repo",
    "repo",
    default=None,
    help="Source repo (owner/name). Defaults to framework.json#upgrade.source.repo.",
)
@click.option(
    "--label",
    "labels",
    multiple=True,
    default=None,
    help="Filter by label (repeatable). Defaults to every label declared "
    "in framework.json#feedback.gh.labels.",
)
@click.option(
    "--state",
    "state",
    type=click.Choice(["open", "closed", "all"]),
    default="open",
    show_default=True,
    help="Issue state to fetch.",
)
@click.option(
    "--since",
    "since",
    default=None,
    help="Only triage issues created at or after this date (YYYY-MM-DD).",
)
@click.option(
    "--limit",
    "limit",
    type=int,
    default=30,
    show_default=True,
    help="Max issues to fetch from gh.",
)
@click.option(
    "--out-dir",
    "out_dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="Where to write drafts (default: docs/reviews/triage/).",
)
@click.option(
    "--dry-run",
    "dry_run",
    is_flag=True,
    default=False,
    help="Print the verdict table without writing any draft files.",
)
def triage_command(
    repo: str | None,
    labels: tuple[str, ...] | None,
    state: str,
    since: str | None,
    limit: int,
    out_dir: Path | None,
    dry_run: bool,
) -> None:
    """Layer 1 triage of upstream issues into SKILL-IMPROVE drafts.

    Exits 0 with a verdict table even when no drafts are produced — the
    table itself is the maintainer's worklist.
    """
    if not shutil.which("gh"):
        raise ExternalToolError(
            "GitHub CLI `gh` not found on PATH. Install from https://cli.github.com/ "
            "and authenticate before running `cataforge issue triage`."
        )

    cfg = get_config_manager()
    project_root = resolve_root()

    if repo is None:
        upstream = cfg.upgrade_source
        owner_repo = upstream.get("repo")
        if not owner_repo:
            raise CataforgeError(
                "framework.json#upgrade.source.repo is not configured; "
                "pass --repo owner/name explicitly."
            )
        repo = str(owner_repo)

    if not labels:
        # Union all configured feedback labels.
        merged: set[str] = set()
        for kind in ("bug", "suggest", "correction-export"):
            for lbl in cfg.feedback_gh_labels(kind):
                merged.add(lbl)
        labels = tuple(sorted(merged))

    issues = fetch_issues(repo, labels=list(labels), state=state, since=since, limit=limit)
    if not issues:
        click.echo(f"No issues matched on {repo} (labels={list(labels) or 'any'}).")
        return

    skill_ids = list_local_skills(project_root)
    agent_ids = list_local_agents(project_root)

    target_dir = out_dir if out_dir is not None else project_root / "docs" / "reviews" / "triage"

    click.echo(f"{len(issues)} issue(s) fetched from {repo}.")
    click.echo("")
    written = 0
    skipped = 0

    for raw in issues:
        parsed = parse_issue_body(raw, skill_ids=skill_ids, agent_ids=agent_ids)
        click.echo(_format_verdict_row(raw, parsed))
        if parsed.verdict != "confirmed":
            skipped += 1
            continue
        if dry_run:
            continue
        if not target_dir.exists():
            target_dir.mkdir(parents=True, exist_ok=True)
        path = write_skill_improve_draft(target_dir, raw, parsed, repo=repo)
        click.secho(f"  → wrote {path.relative_to(project_root)}", fg="green")
        written += 1

    click.echo("")
    click.echo(f"Drafts written: {written} · skipped: {skipped}")
    if dry_run:
        click.echo("(dry-run; pass without --dry-run to write drafts)")


@issue_group.command("close")
@click.argument("number", type=int)
@click.option(
    "--verdict",
    "verdict",
    type=click.Choice(["fixed", "wontfix", "already-fixed"]),
    required=True,
    help="Closure reason. fixed/already-fixed need --pr; wontfix needs --reason.",
)
@click.option(
    "--pr",
    "pr_number",
    type=int,
    default=None,
    help="PR number that fixed (or previously fixed) the issue.",
)
@click.option(
    "--reason",
    "reason",
    default=None,
    help="One-line wontfix justification (required when --verdict wontfix).",
)
@click.option(
    "--repo",
    "repo",
    default=None,
    help="Source repo (owner/name). Defaults to framework.json#upgrade.source.repo.",
)
@click.option(
    "--message",
    "extra_message",
    default=None,
    help="Extra trailing line appended to the templated comment (optional).",
)
@click.option(
    "--dry-run",
    "dry_run",
    is_flag=True,
    default=False,
    help="Print the comment that would be posted; do not call gh.",
)
def close_command(
    number: int,
    verdict: str,
    pr_number: int | None,
    reason: str | None,
    repo: str | None,
    extra_message: str | None,
    dry_run: bool,
) -> None:
    """Close an issue with a templated comment.

    Wraps ``gh issue close N --comment <templated>`` so every closure carries
    a uniform fixed/wontfix/already-fixed message tied to the installed
    cataforge version. Maintainer must invoke per issue (no batch).
    """
    if verdict in {"fixed", "already-fixed"} and pr_number is None:
        raise CataforgeError(f"--verdict {verdict} requires --pr <PR_NUMBER>.")
    if verdict == "wontfix" and not reason:
        raise CataforgeError("--verdict wontfix requires --reason <TEXT>.")

    if not dry_run and not shutil.which("gh"):
        raise ExternalToolError(
            "GitHub CLI `gh` not found on PATH. Install from https://cli.github.com/ "
            "and authenticate before running `cataforge issue close`."
        )

    if repo is None:
        cfg = get_config_manager()
        upstream = cfg.upgrade_source
        owner_repo = upstream.get("repo")
        if not owner_repo:
            raise CataforgeError(
                "framework.json#upgrade.source.repo is not configured; "
                "pass --repo owner/name explicitly."
            )
        repo = str(owner_repo)

    comment = render_close_comment(
        verdict=verdict,
        pr_number=pr_number,
        reason=reason,
        extra_message=extra_message,
    )

    click.echo(f"Repo:    {repo}")
    click.echo(f"Issue:   #{number}")
    click.echo(f"Verdict: {verdict}")
    click.echo("Comment:")
    click.echo(comment)

    if dry_run:
        click.echo("")
        click.echo("(dry-run; pass without --dry-run to call gh issue close)")
        return

    cmd = ["gh", "issue", "close", str(number), "-R", repo, "--comment", comment]
    result = run_proc(cmd)
    if result.returncode != 0:
        raise ExternalToolError(
            f"gh issue close failed (exit {result.returncode}):\n{result.stderr or result.stdout}"
        )
    click.secho(f"\nClosed #{number}.", fg="green")


def _format_verdict_row(issue: dict[str, Any], parsed: ParsedIssue) -> str:
    color = {
        "confirmed": "green",
        "already-fixed": "yellow",
        "needs-repro": "yellow",
        "unrelated": "bright_black",
    }.get(parsed.verdict, "white")
    number = issue.get("number")
    title = (issue.get("title") or "")[:60]
    targets = []
    if parsed.target_skills:
        targets.append(f"skill={','.join(parsed.target_skills)}")
    if parsed.target_agents:
        targets.append(f"agent={','.join(parsed.target_agents)}")
    if parsed.upstream_gap_signals:
        targets.append(f"gaps={parsed.upstream_gap_signals}")
    target_str = " ".join(targets) or "—"
    base = f"#{number}  {parsed.verdict:<14}  {target_str}"
    line = click.style(base, fg=color)
    return f"{line}  {title}"
