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

import json
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

import click

from cataforge import __version__
from cataforge.cli.errors import CataforgeError, ExternalToolError
from cataforge.cli.helpers import get_config_manager, resolve_root
from cataforge.cli.main import cli

INSTALLED_VERSION = __version__


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
    "--repo", "repo", default=None,
    help="Source repo (owner/name). Defaults to framework.json#upgrade.source.repo.",
)
@click.option(
    "--label", "labels", multiple=True, default=None,
    help="Filter by label (repeatable). Defaults to every label declared "
         "in framework.json#feedback.gh.labels.",
)
@click.option(
    "--state", "state", type=click.Choice(["open", "closed", "all"]),
    default="open", show_default=True,
    help="Issue state to fetch.",
)
@click.option(
    "--since", "since", default=None,
    help="Only triage issues created at or after this date (YYYY-MM-DD).",
)
@click.option(
    "--limit", "limit", type=int, default=30, show_default=True,
    help="Max issues to fetch from gh.",
)
@click.option(
    "--out-dir", "out_dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="Where to write drafts (default: docs/reviews/triage/).",
)
@click.option(
    "--dry-run", "dry_run", is_flag=True, default=False,
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

    issues = _fetch_issues(repo, labels=list(labels), state=state, since=since, limit=limit)
    if not issues:
        click.echo(f"No issues matched on {repo} (labels={list(labels) or 'any'}).")
        return

    skill_ids = _list_local_skills(project_root)
    agent_ids = _list_local_agents(project_root)

    target_dir = out_dir if out_dir is not None else project_root / "docs" / "reviews" / "triage"

    click.echo(f"{len(issues)} issue(s) fetched from {repo}.")
    click.echo("")
    written = 0
    skipped = 0

    for raw in issues:
        parsed = _parse_issue_body(raw, skill_ids=skill_ids, agent_ids=agent_ids)
        click.echo(_format_verdict_row(raw, parsed))
        if parsed.verdict != "confirmed":
            skipped += 1
            continue
        if dry_run:
            continue
        if not target_dir.exists():
            target_dir.mkdir(parents=True, exist_ok=True)
        path = _write_skill_improve_draft(target_dir, raw, parsed, repo=repo)
        click.secho(f"  → wrote {path.relative_to(project_root)}", fg="green")
        written += 1

    click.echo("")
    click.echo(f"Drafts written: {written} · skipped: {skipped}")
    if dry_run:
        click.echo("(dry-run; pass without --dry-run to write drafts)")


@issue_group.command("close")
@click.argument("number", type=int)
@click.option(
    "--verdict", "verdict",
    type=click.Choice(["fixed", "wontfix", "already-fixed"]),
    required=True,
    help="Closure reason. fixed/already-fixed need --pr; wontfix needs --reason.",
)
@click.option(
    "--pr", "pr_number", type=int, default=None,
    help="PR number that fixed (or previously fixed) the issue.",
)
@click.option(
    "--reason", "reason", default=None,
    help="One-line wontfix justification (required when --verdict wontfix).",
)
@click.option(
    "--repo", "repo", default=None,
    help="Source repo (owner/name). Defaults to framework.json#upgrade.source.repo.",
)
@click.option(
    "--message", "extra_message", default=None,
    help="Extra trailing line appended to the templated comment (optional).",
)
@click.option(
    "--dry-run", "dry_run", is_flag=True, default=False,
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

    comment = _render_close_comment(
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
    try:
        subprocess.run(cmd, check=True, text=True, encoding="utf-8")
    except subprocess.CalledProcessError as e:
        raise ExternalToolError(
            f"gh issue close failed (exit {e.returncode}):\n{e.stderr or e.stdout}"
        ) from None
    click.secho(f"\nClosed #{number}.", fg="green")


def _render_close_comment(
    *,
    verdict: str,
    pr_number: int | None,
    reason: str | None,
    extra_message: str | None,
) -> str:
    if verdict == "fixed":
        body = f"Fixed in v{INSTALLED_VERSION} (PR #{pr_number})."
    elif verdict == "already-fixed":
        body = f"Already fixed in v{INSTALLED_VERSION} (PR #{pr_number})."
    elif verdict == "wontfix":
        body = f"Wontfix — by design: {reason}"
    else:
        raise CataforgeError(f"unknown verdict: {verdict!r}")
    if extra_message:
        body = f"{body}\n\n{extra_message}"
    return body


# ─── helpers ──────────────────────────────────────────────────────────────────


@dataclass
class _ParsedIssue:
    # Auto verdicts: "confirmed" | "already-fixed" | "needs-repro" |
    # "unrelated". A 5th value "wontfix-by-design" is valid in draft
    # frontmatter but only set by maintainer hand-edit on a confirmed
    # draft when the report turns out to misread an intentional design.
    verdict: str
    reported_version: str | None = None
    target_skills: list[str] = field(default_factory=list)
    target_agents: list[str] = field(default_factory=list)
    upstream_gap_signals: int = 0
    review_fail_summary: str = ""
    rationale: str = ""


_VERSION_LINE_RE = re.compile(
    r"cataforge[^\n]*?\bversion\b[^\n]*?(\d+\.\d+\.\d+(?:[A-Za-z0-9.\-+]*)?)",
    re.IGNORECASE,
)
_VERSION_HEADER_RE = re.compile(
    r"^\s*[*\-]?\s*(?:package|cataforge)\s*[:=]\s*v?(\d+\.\d+\.\d+(?:[A-Za-z0-9.\-+]*)?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_FRAMEWORK_REVIEW_FAIL_RE = re.compile(
    r"FAIL\s+(?:in\s+)?(?:skill|agent)?[:\s]+(?P<id>[a-z0-9][a-z0-9\-]+)",
    re.IGNORECASE,
)
_UPSTREAM_GAP_RE = re.compile(
    r"deviation:\s*upstream[-_]gap", re.IGNORECASE
)


def _parse_issue_body(
    issue: dict[str, Any],
    *,
    skill_ids: set[str],
    agent_ids: set[str],
) -> _ParsedIssue:
    body = issue.get("body") or ""

    # Reported version.
    reported = None
    m = _VERSION_HEADER_RE.search(body)
    if m:
        reported = m.group(1)
    else:
        m = _VERSION_LINE_RE.search(body)
        if m:
            reported = m.group(1)

    # Skill / agent IDs cited in framework-review FAIL lines.
    cited_skills: list[str] = []
    cited_agents: list[str] = []
    for fm in _FRAMEWORK_REVIEW_FAIL_RE.finditer(body):
        ident = fm.group("id").lower()
        if ident in skill_ids and ident not in cited_skills:
            cited_skills.append(ident)
        elif ident in agent_ids and ident not in cited_agents:
            cited_agents.append(ident)

    # Upstream-gap mentions.
    gaps = len(_UPSTREAM_GAP_RE.findall(body))

    # Layer 1 fact-check.
    if reported and _semver_lt(reported, INSTALLED_VERSION):
        return _ParsedIssue(
            verdict="already-fixed",
            reported_version=reported,
            target_skills=cited_skills,
            target_agents=cited_agents,
            upstream_gap_signals=gaps,
            rationale=(
                f"Issue reports cataforge {reported}; installed is "
                f"{INSTALLED_VERSION}. Verify the fix landed before "
                "auto-closing — a regression test would be ideal."
            ),
        )

    # No version + no skill/agent reference + no gap signals = not a
    # parseable feedback bundle.
    if not reported and not cited_skills and not cited_agents and gaps == 0:
        return _ParsedIssue(
            verdict="unrelated",
            rationale="No env block or framework-review citation found.",
        )

    # No version block at all → can't fact-check, but the citations are
    # still useful evidence.
    if not reported:
        return _ParsedIssue(
            verdict="needs-repro",
            target_skills=cited_skills,
            target_agents=cited_agents,
            upstream_gap_signals=gaps,
            rationale=(
                "Body lacks a `cataforge --version` line — ask reporter to "
                "rerun `cataforge feedback bug --gh` (which embeds env)."
            ),
        )

    return _ParsedIssue(
        verdict="confirmed",
        reported_version=reported,
        target_skills=cited_skills,
        target_agents=cited_agents,
        upstream_gap_signals=gaps,
        review_fail_summary=_extract_fail_excerpt(body),
        rationale=(
            f"reported_version={reported} matches installed {INSTALLED_VERSION}; "
            f"{len(cited_skills)} skill / {len(cited_agents)} agent ref(s) "
            f"and {gaps} upstream-gap signal(s) in body."
        ),
    )


def _extract_fail_excerpt(body: str, *, max_lines: int = 8) -> str:
    """Return up to ``max_lines`` of FAIL-tagged lines from the issue body."""
    out: list[str] = []
    for line in body.splitlines():
        if "FAIL" in line and len(out) < max_lines:
            out.append(line.strip())
    return "\n".join(out)


def _semver_lt(a: str, b: str) -> bool:
    """Loose semver compare: treat anything past `X.Y.Z` as a tiebreaker."""
    def _key(s: str) -> tuple[int, int, int, str]:
        cleaned = s.lstrip("v")
        m = re.match(r"^(\d+)\.(\d+)\.(\d+)(.*)$", cleaned)
        if not m:
            return (0, 0, 0, cleaned)
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4))
    return _key(a) < _key(b)


def _format_verdict_row(issue: dict[str, Any], parsed: _ParsedIssue) -> str:
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


def _write_skill_improve_draft(
    out_dir: Path,
    issue: dict[str, Any],
    parsed: _ParsedIssue,
    *,
    repo: str,
) -> Path:
    number = issue.get("number")
    target_id = (
        parsed.target_skills[0] if parsed.target_skills
        else parsed.target_agents[0] if parsed.target_agents
        else "unknown"
    )
    target_kind = "skill" if parsed.target_skills else "agent"
    today = date.today().isoformat()
    fname = f"SKILL-IMPROVE-{target_id}-issue-{number}.md"
    path = out_dir / fname

    issue_url = issue.get("url") or f"https://github.com/{repo}/issues/{number}"
    body = (
        f"---\n"
        f"author: framework-issue-resolve\n"
        f"date: {today}\n"
        f"status: triage-draft\n"
        f"source_issue: {issue_url}\n"
        f"target_id: {target_id}\n"
        f"target_kind: {target_kind}\n"
        f"installed_version: {INSTALLED_VERSION}\n"
        f"reported_version: {parsed.reported_version or 'unknown'}\n"
        f"---\n\n"
        f"# SKILL-IMPROVE-{target_id} (from issue #{number})\n\n"
        f"## Source\n"
        f"- Issue: {issue_url}\n"
        f"- Title: {issue.get('title', '')}\n"
        f"- Reporter env: cataforge {parsed.reported_version or '?'} "
        f"(installed: {INSTALLED_VERSION})\n\n"
        f"## Triage Verdict\n"
        f"- verdict: **{parsed.verdict}**\n"
        f"- target_kind: {target_kind}\n"
        f"- target_id: {target_id}\n"
        f"- target_file: .cataforge/{target_kind}s/{target_id}/"
        f"{'SKILL.md' if target_kind == 'skill' else 'AGENT.md'}\n"
        f"- upstream_gap_signals: {parsed.upstream_gap_signals}\n\n"
        f"## Rationale\n"
        f"{parsed.rationale or '(none)'}\n\n"
        f"## Evidence (excerpt)\n"
        f"```\n"
        f"{parsed.review_fail_summary or '(no FAIL lines in body)'}\n"
        f"```\n\n"
        f"## Proposed change\n"
        f"_TODO: maintainer fills in current_text / proposed_text after "
        f"reading the issue body in full. This draft only fact-checks the "
        f"reported context against installed scaffold._\n\n"
        f"## Next step\n"
        f"- [ ] Promote this draft to `docs/reviews/retro/SKILL-IMPROVE-"
        f"{target_id}.md` after maintainer review, or close the issue with "
        f"a link to the existing fix.\n"
    )
    path.write_text(body, encoding="utf-8")
    return path


def _list_local_skills(project_root: Path) -> set[str]:
    skills_dir = project_root / ".cataforge" / "skills"
    if not skills_dir.is_dir():
        return set()
    return {p.name for p in skills_dir.iterdir() if p.is_dir()}


def _list_local_agents(project_root: Path) -> set[str]:
    agents_dir = project_root / ".cataforge" / "agents"
    if not agents_dir.is_dir():
        return set()
    return {p.name for p in agents_dir.iterdir() if p.is_dir()}


def _fetch_issues(
    repo: str,
    *,
    labels: list[str],
    state: str,
    since: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    cmd = [
        "gh", "issue", "list", "-R", repo,
        "--state", state,
        "--limit", str(limit),
        "--json", "number,title,body,createdAt,url,labels",
    ]
    for lbl in labels:
        cmd.extend(["--label", lbl])
    try:
        result = subprocess.run(
            cmd,
            text=True,
            capture_output=True,
            check=True,
            encoding="utf-8",
        )
    except subprocess.CalledProcessError as e:
        raise ExternalToolError(
            f"gh issue list failed (exit {e.returncode}):\n{e.stderr or e.stdout}"
        ) from None
    issues: list[dict[str, Any]] = json.loads(result.stdout or "[]")

    if since:
        try:
            since_dt = datetime.fromisoformat(since).date()
        except ValueError as e:
            raise CataforgeError(
                f"--since must be YYYY-MM-DD ({e})"
            ) from None
        issues = [
            i for i in issues
            if (i.get("createdAt") or "")[:10] >= since_dt.isoformat()
        ]
    return issues
