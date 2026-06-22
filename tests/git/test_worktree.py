"""GitWorkTree ↔ git contract tests.

The happy-path methods run against a real on-disk repo (offline, bare
sibling = origin) so the port stays honest with git itself. The
``ahead_behind`` parser is pinned separately by a subclass that injects
malformed ``rev-list`` output through the single ``_run`` choke point —
no repo needed and no other git call disturbed.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from cataforge.application.services.git_hygiene import GitWorkTree
from cataforge.core.errors import ExternalToolError
from tests.support.gitrepo import advance_origin, build_linked_repos


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    work, _bare = build_linked_repos(tmp_path)
    return work


class TestGitWorkTreeReads:
    def test_detect_default_branch_from_origin_head(self, repo: Path) -> None:
        assert GitWorkTree(repo).detect_default_branch() == "main"

    def test_is_inside_work_tree_true_in_repo_false_outside(
        self, repo: Path, tmp_path: Path
    ) -> None:
        assert GitWorkTree(repo).is_inside_work_tree() is True
        outside = tmp_path / "nowhere"
        outside.mkdir()
        assert GitWorkTree(outside).is_inside_work_tree() is False

    def test_current_branch(self, repo: Path) -> None:
        assert GitWorkTree(repo).current_branch() == "main"

    def test_is_clean_reflects_worktree(self, repo: Path) -> None:
        git = GitWorkTree(repo)
        assert git.is_clean() is True
        (repo / "dirty.txt").write_text("x", encoding="utf-8")
        assert git.is_clean() is False

    def test_local_branches_lists_only_main_initially(self, repo: Path) -> None:
        assert GitWorkTree(repo).local_branches() == ["main"]

    def test_ahead_behind_one_behind_after_origin_advances(
        self, repo: Path, tmp_path: Path
    ) -> None:
        advance_origin(repo, tmp_path / "origin.git")
        git = GitWorkTree(repo)
        git.fetch_prune("main")
        assert git.ahead_behind("main", "origin/main") == (0, 1)


class _MalformedRevList(GitWorkTree):
    """Overrides the single git choke point to return a bad rev-list shape."""

    def __init__(self, root: Path, bad_stdout: str) -> None:
        super().__init__(root)
        self._bad = bad_stdout

    def _run(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        if args[:1] == ("rev-list",):
            return subprocess.CompletedProcess(["git", *args], 0, self._bad, "")
        return super()._run(*args, check=check)


class TestAheadBehindContract:
    def test_three_token_output_reports_diagnostic(self, tmp_path: Path) -> None:
        with pytest.raises(ExternalToolError, match="unexpected") as exc:
            _MalformedRevList(tmp_path, "1\t2\t3\n").ahead_behind("main", "origin/main")
        assert "1\\t2\\t3" in str(exc.value) or "1\t2\t3" in str(exc.value)

    def test_non_integer_output_reports_diagnostic(self, tmp_path: Path) -> None:
        with pytest.raises(ExternalToolError, match="non-integer"):
            _MalformedRevList(tmp_path, "abc\tdef\n").ahead_behind("main", "origin/main")

    def test_empty_output_is_zero_zero(self, tmp_path: Path) -> None:
        assert _MalformedRevList(tmp_path, "").ahead_behind("main", "origin/main") == (0, 0)
