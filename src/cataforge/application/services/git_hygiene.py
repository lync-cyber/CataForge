"""Git-hygiene mechanics — the engine behind ``cataforge git``.

Holds every git invocation and the sync/prune decision logic so the CLI,
the SessionStart hook, and bootstrap share one implementation instead of
each shelling out to git on their own. Lives in ``services/`` (not
``core/``) because it shells out to ``git`` / ``gh`` and is consumed by the
interface and runtime adapters.

Two seams keep this testable and free of god-objects:

* :class:`GitWorkTree` is the single git I/O boundary. ``dry_run`` gates
  side effects here (mutations record to ``planned`` instead of running),
  so the decision functions never branch on dry-run.
* The module-level functions hold decisions only — they call port methods
  and return result dataclasses, never print and never shell out directly.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cataforge.core.errors import CataforgeError, ExternalToolError
from cataforge.utils.run_subprocess import DEFAULT_TIMEOUT_SECONDS
from cataforge.utils.run_subprocess import run as run_proc

if TYPE_CHECKING:
    from cataforge.core.schema.framework import FrameworkGitRemotePolicy

_REPO_SLUG_RE = re.compile(r"github\.com[:/]([^/:]+/[^/:]+?)(?:\.git)?/?$")


@dataclass(frozen=True)
class SyncOutcome:
    """What :func:`sync_default_branch` decided and did.

    ``action`` ∈ {``up-to-date``, ``fast-forwarded``, ``ahead-skip``}.
    Divergence and dirty-tree-needing-switch raise rather than return.
    ``switched_from`` names the branch we switched away from to reach
    ``branch`` (``None`` when already on it), so the caller can restore it.
    """

    branch: str
    action: str
    ahead: int
    behind: int
    switched_from: str | None = None


class GitWorkTree:
    """Typed git operations rooted at one work-tree — the only git I/O point.

    Read operations always execute. Branch-state mutations (``switch`` /
    ``merge_ff_only`` / ``delete_branch``) become no-ops that append their
    argv to :attr:`planned` when ``dry_run`` is set, so a caller can preview
    the side effects. ``fetch_prune`` is exempt: it always runs because it
    only refreshes / prunes remote-tracking refs (never a local branch or the
    working tree), and an accurate ``[gone]`` view is what a prune preview
    needs.
    """

    def __init__(self, root: Path, *, dry_run: bool = False) -> None:
        self.root = root
        self.dry_run = dry_run
        self.planned: list[list[str]] = []

    def _run(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        result = run_proc(["git", *args], cwd=self.root)
        if check and result.returncode != 0:
            raise ExternalToolError(
                f"git {' '.join(args)} failed:\n  {result.stderr or result.stdout}".rstrip()
            )
        return result

    def _run_mutating(self, *args: str) -> None:
        if self.dry_run:
            self.planned.append(["git", *args])
            return
        self._run(*args)

    # ---- read operations ----

    def is_inside_work_tree(self) -> bool:
        return self._run("rev-parse", "--is-inside-work-tree", check=False).returncode == 0

    def current_branch(self) -> str:
        return (self._run("rev-parse", "--abbrev-ref", "HEAD").stdout or "").strip()

    def is_clean(self) -> bool:
        return not (self._run("status", "--porcelain").stdout or "").strip()

    def detect_default_branch(self) -> str:
        """Resolve the default branch: origin/HEAD, then init.defaultBranch, then main/master."""
        head = self._run("symbolic-ref", "--short", "refs/remotes/origin/HEAD", check=False)
        if head.returncode == 0:
            ref = (head.stdout or "").strip()
            if ref.startswith("origin/"):
                return ref[len("origin/") :]

        configured = self._run("config", "--get", "init.defaultBranch", check=False)
        if configured.returncode == 0 and (configured.stdout or "").strip():
            return configured.stdout.strip()

        for candidate in ("main", "master"):
            probe = self._run("show-ref", "--verify", f"refs/heads/{candidate}", check=False)
            if probe.returncode == 0:
                return candidate

        raise CataforgeError(
            "Could not detect a default branch. Pass --branch explicitly or set "
            "`git remote set-head origin --auto` so origin/HEAD points somewhere."
        )

    def ahead_behind(self, local: str, remote: str) -> tuple[int, int]:
        """Return ``(ahead, behind)`` of ``local`` vs ``remote``.

        ``git rev-list --left-right --count`` is contractually two
        whitespace-separated integers on one line; a contract drift (or a
        locale warning leaking onto stdout) surfaces a diagnostic instead
        of a bare ``ValueError``.
        """
        raw = self._run("rev-list", "--left-right", "--count", f"{local}...{remote}").stdout or ""
        parts = raw.strip().split() or ["0", "0"]
        if len(parts) != 2:
            raise ExternalToolError(
                f"unexpected `git rev-list --left-right --count` output while "
                f"comparing {local} vs {remote}: {raw!r}"
            )
        try:
            return int(parts[0]), int(parts[1])
        except ValueError:
            raise ExternalToolError(
                f"non-integer ahead/behind counts from git while comparing "
                f"{local} vs {remote}: {raw!r}"
            ) from None

    def gone_branches(self) -> list[str]:
        """Local branches whose upstream is gone (``[gone]`` in ``upstream:track``).

        This is the squash-merge signal: GitHub deletes the head branch on
        squash-merge, so after ``fetch --prune`` the local branch's upstream
        reads ``[gone]`` even though its commit is not an ancestor of the
        default branch (which is why ``git branch --merged`` misses it).
        """
        out = (
            self._run(
                "for-each-ref", "--format=%(refname:short) %(upstream:track)", "refs/heads/"
            ).stdout
            or ""
        )
        gone: list[str] = []
        for line in out.splitlines():
            name, _, track = line.rstrip().partition(" ")
            if name and "[gone]" in track:
                gone.append(name)
        return gone

    def local_branches(self) -> list[str]:
        out = self._run("for-each-ref", "--format=%(refname:short)", "refs/heads/").stdout or ""
        return [line.strip() for line in out.splitlines() if line.strip()]

    def remote_url(self, remote: str = "origin") -> str | None:
        """Return the configured URL of ``remote``, or ``None`` when unset."""
        result = self._run("remote", "get-url", remote, check=False)
        if result.returncode != 0:
            return None
        return (result.stdout or "").strip() or None

    # ---- mutating / network operations ----

    def fetch_prune(
        self, branch: str | None = None, *, timeout: float | None = DEFAULT_TIMEOUT_SECONDS
    ) -> None:
        """Fetch from origin and prune stale remote-tracking refs.

        Always executes (even under ``dry_run``): it never mutates a local
        branch or the working tree, and pruning deleted remote-tracking refs
        is exactly what makes ``gone_branches`` accurate before a prune.
        """
        args = ["fetch", "origin", *([branch] if branch else []), "--prune"]
        result = run_proc(["git", *args], cwd=self.root, timeout=timeout)
        if result.returncode != 0:
            msg = result.stderr or result.stdout
            raise ExternalToolError(f"git fetch failed:\n  {msg}".rstrip())

    def switch(self, branch: str) -> None:
        self._run_mutating("switch", branch)

    def merge_ff_only(self, ref: str) -> None:
        self._run_mutating("merge", "--ff-only", ref)

    def delete_branch(self, name: str, *, force: bool = False) -> None:
        self._run_mutating("branch", "-D" if force else "-d", name)


def sync_default_branch(
    git: GitWorkTree,
    *,
    branch: str | None = None,
    fetch: bool = True,
    fetch_timeout: float | None = DEFAULT_TIMEOUT_SECONDS,
) -> SyncOutcome:
    """Fetch + fast-forward the default branch from origin.

    Fast-forward only: a diverged branch raises rather than creating a
    merge commit. When the caller is on a different branch, switches to the
    target first (refusing on a dirty tree so local edits are never
    overwritten) and reports the origin branch via ``switched_from``.

    ``fetch=False`` skips the network fetch when the caller already fetched
    (the session sweep does one full ``fetch --prune`` up front).
    """
    target = branch or git.detect_default_branch()
    starting = git.current_branch()
    if starting == "HEAD":
        raise CataforgeError(
            "Detached HEAD — checkout a branch first, then re-run `cataforge git sync`."
        )

    if fetch:
        git.fetch_prune(target, timeout=fetch_timeout)

    switched_from: str | None = None
    if starting != target:
        if not git.is_clean():
            raise CataforgeError(
                f"Working tree on `{starting}` has uncommitted changes — "
                "commit or stash before running `cataforge git sync`."
            )
        git.switch(target)
        switched_from = starting

    ahead, behind = git.ahead_behind(target, f"origin/{target}")
    if ahead and behind:
        raise CataforgeError(
            f"`{target}` and `origin/{target}` have diverged "
            f"({ahead} ahead, {behind} behind). `cataforge git sync` only does "
            f"fast-forwards — resolve manually with `git pull --rebase` or "
            f"`git reset --hard origin/{target}` (destructive)."
        )
    if ahead:
        action = "ahead-skip"
    elif behind:
        git.merge_ff_only(f"origin/{target}")
        action = "fast-forwarded"
    else:
        action = "up-to-date"

    return SyncOutcome(
        branch=target, action=action, ahead=ahead, behind=behind, switched_from=switched_from
    )


@dataclass(frozen=True)
class GitHubRepo:
    """A GitHub ``owner/repo`` slug plus the ``gh`` probes prune needs."""

    slug: str

    @classmethod
    def from_remote(cls, git: GitWorkTree, *, remote: str = "origin") -> GitHubRepo | None:
        """Build from ``git remote get-url``; ``None`` when the URL is unparseable."""
        url = git.remote_url(remote)
        if not url:
            return None
        match = _REPO_SLUG_RE.search(url.strip())
        return cls(match.group(1)) if match else None

    def pr_is_merged(self, head: str) -> bool:
        """True when a merged PR exists for the ``head`` branch.

        The guard against deleting a branch whose remote vanished for some
        reason *other* than a merge (manual delete, force-push cleanup).
        """
        result = run_proc(
            [
                "gh",
                "pr",
                "list",
                "--repo",
                self.slug,
                "--head",
                head,
                "--state",
                "merged",
                "--json",
                "number",
            ]
        )
        if result.returncode != 0:
            raise ExternalToolError(
                f"gh pr list failed (exit {result.returncode}):\n"
                f"{result.stderr or result.stdout}".rstrip()
            )
        return bool(json.loads(result.stdout or "[]"))

    def ensure_merge_policy(
        self, policy: FrameworkGitRemotePolicy, *, dry_run: bool = False
    ) -> PolicyChange:
        """Make the repo's merge settings match ``policy`` (idempotent).

        ``--dry-run`` reports the intended settings without any ``gh`` call.
        Otherwise reads the current settings first and only issues a PATCH when
        something actually drifts, so a re-run on a compliant repo is a no-op.
        """
        desired = self._desired_policy(policy)
        fields = {k: ("true" if v else "false") for k, v in desired.items()}
        if dry_run:
            return PolicyChange(slug=self.slug, changed=True, fields=fields, dry_run=True)

        current = self._get_repo_settings()
        if all(current.get(k) == v for k, v in desired.items()):
            return PolicyChange(slug=self.slug, changed=False, fields={})

        args = ["gh", "api", "--method", "PATCH", f"repos/{self.slug}"]
        for key, value in fields.items():
            args += ["-f", f"{key}={value}"]
        result = run_proc(args)
        if result.returncode != 0:
            raise ExternalToolError(
                f"gh api PATCH failed (exit {result.returncode}):\n"
                f"{result.stderr or result.stdout}".rstrip()
            )
        return PolicyChange(slug=self.slug, changed=True, fields=fields)

    @staticmethod
    def _desired_policy(policy: FrameworkGitRemotePolicy) -> dict[str, bool]:
        desired: dict[str, bool] = {"delete_branch_on_merge": policy.delete_branch_on_merge}
        if policy.squash_only:
            desired["allow_squash_merge"] = True
            desired["allow_merge_commit"] = False
            desired["allow_rebase_merge"] = False
        return desired

    def _get_repo_settings(self) -> dict[str, Any]:
        result = run_proc(["gh", "api", f"repos/{self.slug}"])
        if result.returncode != 0:
            raise ExternalToolError(
                f"gh api GET failed (exit {result.returncode}):\n"
                f"{result.stderr or result.stdout}".rstrip()
            )
        data = json.loads(result.stdout or "{}")
        return data if isinstance(data, dict) else {}


@dataclass(frozen=True)
class PolicyChange:
    """The outcome of :meth:`GitHubRepo.ensure_merge_policy`.

    ``changed`` is False when the repo already complied (no PATCH issued);
    ``fields`` carries the settings applied (or that would be, under dry-run).
    """

    slug: str
    changed: bool
    fields: dict[str, str]
    dry_run: bool = False


@dataclass(frozen=True)
class BranchVerdict:
    """Whether one local branch may be pruned, and the evidence behind it."""

    branch: str
    deletable: bool
    upstream_gone: bool
    pr_merged: bool | None = None


def find_prunable_branches(
    git: GitWorkTree,
    gh: GitHubRepo | None,
    *,
    default_branch: str,
    confirm_via_gh: bool,
) -> list[BranchVerdict]:
    """Decide which local branches are safe to delete after a squash-merge.

    A branch is deletable when its upstream is gone — and, when
    ``confirm_via_gh`` and a ``gh`` port are available, only after gh
    confirms a merged PR (so a branch whose remote vanished without a merge
    is kept). The current and default branches are never candidates.
    """
    current = git.current_branch()
    gone = set(git.gone_branches())
    skip = {default_branch, current, "HEAD"}
    verdicts: list[BranchVerdict] = []
    for name in sorted(git.local_branches()):
        if name in skip:
            continue
        if name not in gone:
            verdicts.append(BranchVerdict(name, deletable=False, upstream_gone=False))
            continue
        if confirm_via_gh and gh is not None:
            merged = gh.pr_is_merged(name)
            verdicts.append(
                BranchVerdict(name, deletable=merged, upstream_gone=True, pr_merged=merged)
            )
        else:
            verdicts.append(BranchVerdict(name, deletable=True, upstream_gone=True))
    return verdicts


def prune_branches(git: GitWorkTree, names: list[str]) -> tuple[list[str], list[tuple[str, str]]]:
    """Force-delete each branch with ``git branch -D``; return ``(deleted, failed)``.

    ``-D`` (not ``-d``) because a squash-merged branch's commit is not an
    ancestor of the default branch, so git's own merge check (``-d``) would
    refuse exactly the branches prune targets. The merge safety lives upstream
    in :func:`find_prunable_branches` (the ``[gone]`` + merged-PR vetting);
    a per-branch failure is collected rather than aborting the batch.
    """
    deleted: list[str] = []
    failed: list[tuple[str, str]] = []
    for name in names:
        try:
            git.delete_branch(name, force=True)
            deleted.append(name)
        except ExternalToolError as exc:
            failed.append((name, str(exc)))
    return deleted, failed


@dataclass(frozen=True)
class SessionSyncReport:
    """What :func:`run_session_sync` did in one best-effort sweep."""

    synced: SyncOutcome | None
    pruned: list[str]


def run_session_sync(
    git: GitWorkTree,
    gh: GitHubRepo | None,
    *,
    fast_forward_clean: bool,
    prune_gone: bool,
    confirm_via_gh: bool,
    fetch_timeout: float | None,
) -> SessionSyncReport:
    """Fetch, fast-forward a clean default branch, and prune gone branches.

    Pure orchestration over the existing decision functions — it never prints
    and never switches branches. The fast-forward runs only when the caller is
    already on the default branch with a clean tree, so a session opened on a
    feature branch is never disturbed. One full ``fetch --prune`` up front keeps
    the ``[gone]`` view accurate before pruning.
    """
    target = git.detect_default_branch()
    git.fetch_prune(timeout=fetch_timeout)

    synced: SyncOutcome | None = None
    if fast_forward_clean and git.current_branch() == target and git.is_clean():
        synced = sync_default_branch(git, branch=target, fetch=False)

    pruned: list[str] = []
    if prune_gone:
        verdicts = find_prunable_branches(
            git, gh, default_branch=target, confirm_via_gh=confirm_via_gh
        )
        deleted, _failed = prune_branches(git, [v.branch for v in verdicts if v.deletable])
        pruned = deleted

    return SessionSyncReport(synced=synced, pruned=pruned)
