"""Upstream-issue triage/close service — logic behind ``cataforge issue``.

Holds the parsing, fact-check, draft-rendering, and ``gh`` fetch logic so the
``triage`` / ``close`` commands stay thin parse→call→render layers. Lives in
``services/`` (not ``core/``) because it shells out to ``gh`` and is consumed
only by the CLI.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from datetime import date as date_cls
from datetime import datetime
from pathlib import Path
from typing import Any

from cataforge import __version__
from cataforge.core.errors import CataforgeError, ExternalToolError
from cataforge.core.version import parse_semver
from cataforge.utils.run_subprocess import run as run_proc

INSTALLED_VERSION = __version__


@dataclass
class ParsedIssue:
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
# `cataforge feedback ... --gh` renders Environment lines as
# `- **CataForge package**: \`0.4.0\`` (markdown bold + inline code) — the
# header regex above can't see past the `**` wrapping.
_VERSION_BOLD_RE = re.compile(
    r"\*\*(?:CataForge\s+)?(?:package|scaffold)(?:\s+version)?\*\*"
    r"\s*[:=]\s*[`'\"]?v?(\d+\.\d+\.\d+(?:[A-Za-z0-9.\-+]*)?)",
    re.IGNORECASE,
)
# Native GitHub issue template form (`cataforge feedback ... --gh` uses an
# H3 + blank line + bare version on the next line).
_VERSION_TEMPLATE_RE = re.compile(
    r"###\s+CataForge\s+version\s*\n+\s*v?(\d+\.\d+\.\d+(?:[A-Za-z0-9.\-+]*)?)",
    re.IGNORECASE,
)
_FRAMEWORK_REVIEW_FAIL_RE = re.compile(
    r"FAIL\s+(?:in\s+)?(?:skill|agent)?[:\s]+(?P<id>[a-z0-9][a-z0-9\-]+)",
    re.IGNORECASE,
)
_UPSTREAM_GAP_RE = re.compile(r"deviation:\s*upstream[-_]gap", re.IGNORECASE)


def parse_issue_body(
    issue: dict[str, Any],
    *,
    skill_ids: set[str],
    agent_ids: set[str],
) -> ParsedIssue:
    body = issue.get("body") or ""

    # Reported version. Order matters: try the most specific issue-template
    # forms first (template H3, then markdown-bold env block) so the looser
    # legacy regexes don't snag a false positive on e.g. a `cataforge 0.3.x`
    # mention deeper in the body.
    reported = None
    for pattern in (
        _VERSION_TEMPLATE_RE,
        _VERSION_BOLD_RE,
        _VERSION_HEADER_RE,
        _VERSION_LINE_RE,
    ):
        m = pattern.search(body)
        if m:
            reported = m.group(1)
            break

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
        return ParsedIssue(
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
        return ParsedIssue(
            verdict="unrelated",
            rationale="No env block or framework-review citation found.",
        )

    # No version block at all → can't fact-check, but the citations are
    # still useful evidence.
    if not reported:
        return ParsedIssue(
            verdict="needs-repro",
            target_skills=cited_skills,
            target_agents=cited_agents,
            upstream_gap_signals=gaps,
            rationale=(
                "Body lacks a `cataforge --version` line — ask reporter to "
                "rerun `cataforge feedback bug --gh` (which embeds env)."
            ),
        )

    return ParsedIssue(
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
        nums = parse_semver(cleaned)
        if nums is None:
            return (0, 0, 0, cleaned)
        suffix = re.sub(r"^\d+\.\d+\.\d+", "", cleaned)
        return (*nums, suffix)

    return _key(a) < _key(b)


def resolve_release_tag(explicit: str | None = None, *, project_root: Path | None = None) -> str:
    """Resolve the release tag the close comment names.

    The comment tells a downstream reporter which released version ships
    the fix, so the value must be the release that contains the merged PR —
    not whatever cataforge build happens to be installed in the maintainer's
    shell. Precedence: an explicit ``--release`` wins; otherwise the latest
    git tag reachable from HEAD (the release just cut); falling back to the
    installed ``v{__version__}`` only when git or tags are unavailable.
    """
    if explicit and explicit.strip():
        v = explicit.strip()
        return v if v.startswith("v") else f"v{v}"
    try:
        result = run_proc(["git", "describe", "--tags", "--abbrev=0"], cwd=project_root)
    except (OSError, subprocess.SubprocessError):
        return f"v{INSTALLED_VERSION}"
    tag = result.stdout.strip()
    if result.returncode != 0 or not tag:
        return f"v{INSTALLED_VERSION}"
    return tag


def render_close_comment(
    *,
    verdict: str,
    pr_number: int | None,
    reason: str | None,
    extra_message: str | None,
    release: str,
) -> str:
    if verdict == "fixed":
        body = f"Fixed in {release} (PR #{pr_number})."
    elif verdict == "already-fixed":
        body = f"Already fixed in {release} (PR #{pr_number})."
    elif verdict == "wontfix":
        body = f"Wontfix — by design: {reason}"
    else:
        raise CataforgeError(f"unknown verdict: {verdict!r}")
    if extra_message:
        body = f"{body}\n\n{extra_message}"
    return body


def write_skill_improve_draft(
    out_dir: Path,
    issue: dict[str, Any],
    parsed: ParsedIssue,
    *,
    repo: str,
) -> Path:
    number = issue.get("number")
    target_id = (
        parsed.target_skills[0]
        if parsed.target_skills
        else parsed.target_agents[0]
        if parsed.target_agents
        else "unknown"
    )
    target_kind = "skill" if parsed.target_skills else "agent"
    today = date_cls.today().isoformat()
    fname = f"SKILL-IMPROVE-{target_id}-issue-{number}.md"
    path = out_dir / fname

    issue_url = issue.get("url") or f"https://github.com/{repo}/issues/{number}"
    body = (
        f"---\n"
        f"author: framework-issue-resolve\n"
        f"date: {today}\n"
        f"status: draft\n"
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
        f"_(maintainer fills in current_text / proposed_text after "
        f"reading the issue body in full. This draft only fact-checks the "
        f"reported context against installed scaffold.)_\n\n"
        f"## Next step\n"
        f"- [ ] Promote this draft to `docs/reviews/retro/SKILL-IMPROVE-"
        f"{target_id}.md` after maintainer review, or close the issue with "
        f"a link to the existing fix.\n"
    )
    path.write_text(body)
    return path


def list_local_skills(project_root: Path) -> set[str]:
    skills_dir = project_root / ".cataforge" / "skills"
    if not skills_dir.is_dir():
        return set()
    return {p.name for p in skills_dir.iterdir() if p.is_dir()}


def list_local_agents(project_root: Path) -> set[str]:
    agents_dir = project_root / ".cataforge" / "agents"
    if not agents_dir.is_dir():
        return set()
    return {p.name for p in agents_dir.iterdir() if p.is_dir()}


def fetch_issues(
    repo: str,
    *,
    labels: list[str],
    state: str,
    since: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    """Issue list with **OR** semantics across ``labels``.

    ``gh issue list`` treats repeated ``--label`` flags as AND — a label
    union (which is what ``framework.json#feedback.gh.labels`` actually
    declares: ``{bug, enhancement}``) needs one ``gh`` call per label and a
    merge by issue number. When ``labels`` is empty the caller wants every
    issue in scope, so we issue a single labelless call.
    """
    base_cmd = [
        "gh",
        "issue",
        "list",
        "-R",
        repo,
        "--state",
        state,
        "--limit",
        str(limit),
        "--json",
        "number,title,body,createdAt,url,labels",
    ]

    label_groups = [[lbl] for lbl in labels] if labels else [[]]
    merged: dict[int, dict[str, Any]] = {}
    for group in label_groups:
        cmd = list(base_cmd)
        for lbl in group:
            cmd.extend(["--label", lbl])
        result = run_proc(cmd)
        if result.returncode != 0:
            raise ExternalToolError(
                f"gh issue list failed (exit {result.returncode}):\n"
                f"{result.stderr or result.stdout}"
            )
        for entry in json.loads(result.stdout or "[]"):
            number = entry.get("number")
            if not isinstance(number, int):
                continue
            # First-write-wins; later passes are duplicates of the same issue.
            merged.setdefault(number, entry)

    issues = sorted(merged.values(), key=lambda e: e.get("createdAt") or "")

    if since:
        try:
            since_dt = datetime.fromisoformat(since).date()
        except ValueError as e:
            raise CataforgeError(f"--since must be YYYY-MM-DD ({e})") from None
        issues = [i for i in issues if (i.get("createdAt") or "")[:10] >= since_dt.isoformat()]
    return issues
