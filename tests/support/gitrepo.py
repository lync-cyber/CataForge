"""Reusable on-disk git fixtures + a scriptable GitWorkTree fake.

``build_linked_repos`` builds a ``(work, bare-origin)`` pair so git-hygiene
tests exercise the real git contract offline. ``FakeGitWorkTree`` lets
service-level decision tests assert which git operations fire — and which do
not — without standing up a real repo.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from cataforge.core.errors import ExternalToolError


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=True,
        encoding="utf-8",
    )


def build_linked_repos(tmp_path: Path) -> tuple[Path, Path]:
    """Return ``(work, bare)`` — a clone plus its bare origin, one commit on main."""
    work = tmp_path / "work"
    bare = tmp_path / "origin.git"
    work.mkdir()
    _git(work, "init", "-b", "main")
    _git(work, "config", "user.email", "test@example.com")
    _git(work, "config", "user.name", "test")
    _git(work, "config", "commit.gpgsign", "false")
    (work / "README.md").write_text("hello\n", encoding="utf-8")
    (work / ".cataforge").mkdir()
    (work / ".cataforge" / "framework.json").write_text(
        '{"version": "0.0.0-test"}', encoding="utf-8"
    )
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "init")
    _git(tmp_path, "init", "--bare", "-b", "main", str(bare))
    _git(work, "remote", "add", "origin", str(bare))
    _git(work, "push", "-u", "origin", "main")
    _git(work, "remote", "set-head", "origin", "main")
    return work, bare


def advance_origin(work: Path, bare: Path, *, filename: str = "two.txt") -> None:
    """Push a commit to origin/main from a sibling clone (a simulated teammate)."""
    sibling = work.parent / f"sibling-{filename}"
    _git(work.parent, "clone", str(bare), sibling.name)
    _git(sibling, "config", "user.email", "t@e.com")
    _git(sibling, "config", "user.name", "t")
    _git(sibling, "config", "commit.gpgsign", "false")
    (sibling / filename).write_text("x\n", encoding="utf-8")
    _git(sibling, "add", filename)
    _git(sibling, "commit", "-m", filename)
    _git(sibling, "push")


def squash_merge_and_delete_remote(work: Path, bare: Path, *, branch: str) -> None:
    """Reproduce a squash-merge + head-branch deletion.

    Creates ``branch`` with its own commit, pushes it (so it has an upstream),
    switches back to main, then deletes the remote branch from a *sibling*
    clone so ``work``'s remote-tracking ref stays stale until it runs
    ``fetch --prune``. After that prune the local ``branch`` reads
    ``[gone]`` — the squash-blind state ``git branch --merged`` never sees,
    because the squashed commit is not an ancestor of the local branch.
    """
    slug = branch.replace("/", "_")
    _git(work, "switch", "-c", branch)
    (work / f"{slug}.txt").write_text("feature\n", encoding="utf-8")
    _git(work, "add", "-A")
    _git(work, "commit", "-m", f"work on {branch}")
    _git(work, "push", "-u", "origin", branch)
    _git(work, "switch", "main")
    sibling = work.parent / f"sibling-del-{slug}"
    _git(work.parent, "clone", str(bare), sibling.name)
    _git(sibling, "push", "origin", "--delete", branch)


class FakeGitWorkTree:
    """Scriptable :class:`GitWorkTree` stand-in that records mutating calls.

    Tests construct it with the repo state they want to simulate and then
    assert on :attr:`calls` (e.g. ``("merge_ff_only", "origin/main")`` present
    or absent) — exercising decision logic without a real repo.
    """

    def __init__(
        self,
        *,
        current: str = "main",
        default: str = "main",
        clean: bool = True,
        ahead: int = 0,
        behind: int = 0,
        gone: set[str] | None = None,
        locals_: list[str] | None = None,
        fail_delete: set[str] | None = None,
    ) -> None:
        self._current = current
        self._default = default
        self._clean = clean
        self._ahead = ahead
        self._behind = behind
        self._gone = set(gone or set())
        self._locals = list(locals_ or [])
        self._fail_delete = set(fail_delete or set())
        self.calls: list[tuple] = []

    @property
    def method_names(self) -> list[str]:
        return [call[0] for call in self.calls]

    def is_inside_work_tree(self) -> bool:
        return True

    def detect_default_branch(self) -> str:
        return self._default

    def current_branch(self) -> str:
        return self._current

    def is_clean(self) -> bool:
        return self._clean

    def fetch_prune(self, branch: str | None = None, *, timeout: float | None = None) -> None:
        self.calls.append(("fetch_prune", branch))

    def switch(self, branch: str) -> None:
        self.calls.append(("switch", branch))
        self._current = branch

    def ahead_behind(self, local: str, remote: str) -> tuple[int, int]:
        self.calls.append(("ahead_behind", local, remote))
        return (self._ahead, self._behind)

    def merge_ff_only(self, ref: str) -> None:
        self.calls.append(("merge_ff_only", ref))

    def gone_branches(self) -> list[str]:
        return [b for b in self._locals if b in self._gone]

    def local_branches(self) -> list[str]:
        return list(self._locals)

    def delete_branch(self, name: str, *, force: bool = False) -> None:
        self.calls.append(("delete_branch", name, force))
        if name in self._fail_delete:
            raise ExternalToolError(f"cannot delete {name}")


class FakeGitHubRepo:
    """Scriptable :class:`GitHubRepo` stand-in for prune-decision tests.

    ``merged`` is the set of branch names whose PR is merged; every
    ``pr_is_merged`` call is recorded so a test can assert the gh port was
    (or was not) consulted.
    """

    def __init__(self, *, slug: str = "owner/repo", merged: set[str] | None = None) -> None:
        self.slug = slug
        self._merged = set(merged or set())
        self.calls: list[str] = []

    def pr_is_merged(self, head: str) -> bool:
        self.calls.append(head)
        return head in self._merged
