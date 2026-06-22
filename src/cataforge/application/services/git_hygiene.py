"""Git-hygiene mechanics — the engine behind ``cataforge git``.

Holds every git invocation and the sync/prune decision logic so the CLI,
the SessionStart hook, and bootstrap share one implementation instead of
each shelling out to git on their own. Lives in ``services/`` (not
``core/``) because it shells out to ``git`` and is consumed by interface
adapters only.

Two seams keep this testable and free of god-objects:

* :class:`GitWorkTree` is the single git I/O boundary. ``dry_run`` gates
  side effects here (mutations record to ``planned`` instead of running),
  so the decision functions never branch on dry-run.
* The module-level functions hold decisions only — they call port methods
  and return result dataclasses, never print and never shell out directly.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from cataforge.core.errors import CataforgeError, ExternalToolError
from cataforge.utils.run_subprocess import DEFAULT_TIMEOUT_SECONDS
from cataforge.utils.run_subprocess import run as run_proc


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

    Read operations always execute. Mutating / network operations
    (``fetch_prune`` / ``switch`` / ``merge_ff_only`` / ``delete_branch``)
    become no-ops that append their argv to :attr:`planned` when
    ``dry_run`` is set, so a caller can preview the side effects.
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

    def merged_branches(self, target: str) -> set[str]:
        """Local branch names fully merged into ``target`` (ancestor-reachable)."""
        out = self._run("branch", "--merged", target).stdout or ""
        names: set[str] = set()
        for line in out.splitlines():
            name = line.strip().lstrip("*").strip()
            if name and not name.startswith("("):
                names.add(name)
        return names

    def local_branches(self) -> list[str]:
        out = self._run("for-each-ref", "--format=%(refname:short)", "refs/heads/").stdout or ""
        return [line.strip() for line in out.splitlines() if line.strip()]

    # ---- mutating / network operations ----

    def fetch_prune(
        self, branch: str | None = None, *, timeout: float | None = DEFAULT_TIMEOUT_SECONDS
    ) -> None:
        args = ["fetch", "origin", *([branch] if branch else []), "--prune"]
        if self.dry_run:
            self.planned.append(["git", *args])
            return
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
    fetch_timeout: float | None = DEFAULT_TIMEOUT_SECONDS,
) -> SyncOutcome:
    """Fetch + fast-forward the default branch from origin.

    Fast-forward only: a diverged branch raises rather than creating a
    merge commit. When the caller is on a different branch, switches to the
    target first (refusing on a dirty tree so local edits are never
    overwritten) and reports the origin branch via ``switched_from``.
    """
    target = branch or git.detect_default_branch()
    starting = git.current_branch()
    if starting == "HEAD":
        raise CataforgeError(
            "Detached HEAD — checkout a branch first, then re-run `cataforge git sync`."
        )

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


def find_merged_branches(git: GitWorkTree, target: str) -> list[str]:
    """Local branches fully merged into ``target``, excluding it and ``HEAD``."""
    merged = git.merged_branches(target)
    return sorted(b for b in git.local_branches() if b in merged and b != target and b != "HEAD")


def prune_branches(git: GitWorkTree, names: list[str]) -> tuple[list[str], list[tuple[str, str]]]:
    """Delete each branch with ``git branch -d``; return ``(deleted, failed)``.

    ``-d`` (not ``-D``) so git itself refuses to drop an unmerged branch;
    a per-branch failure is collected rather than aborting the batch.
    """
    deleted: list[str] = []
    failed: list[tuple[str, str]] = []
    for name in names:
        try:
            git.delete_branch(name, force=False)
            deleted.append(name)
        except ExternalToolError as exc:
            failed.append((name, str(exc)))
    return deleted, failed
