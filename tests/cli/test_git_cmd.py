"""Tests for ``cataforge git sync`` (and the hidden ``sync-main`` alias).

Exercise the command surface against a real on-disk git repo so the
contract with ``git`` itself stays honest. ``origin`` is a bare sibling
repo so the network is never touched.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from cataforge.interface.cli.git_cmd import git_group, sync_main_alias
from tests.cli.conftest import invoke_under_group
from tests.support.gitrepo import (
    advance_origin,
    build_linked_repos,
    squash_merge_and_delete_remote,
)


@pytest.fixture
def linked(tmp_path: Path) -> tuple[Path, Path]:
    return build_linked_repos(tmp_path)


@pytest.fixture
def in_repo(linked: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch) -> Path:
    work, _bare = linked
    monkeypatch.chdir(work)
    return work


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=cwd, text=True, capture_output=True, check=True, encoding="utf-8"
    )


def _branch_list(cwd: Path) -> str:
    return _git(cwd, "branch", "--list").stdout


class TestGitSyncHappyPath:
    def test_already_up_to_date_is_no_op(self, in_repo: Path) -> None:
        result = invoke_under_group(git_group, ["sync"])
        assert result.exit_code == 0, result.output
        assert "already up to date" in result.output

    def test_fast_forwards_when_origin_advances(
        self, in_repo: Path, linked: tuple[Path, Path]
    ) -> None:
        work, bare = linked
        advance_origin(work, bare)
        result = invoke_under_group(git_group, ["sync"])
        assert result.exit_code == 0, result.output
        assert "fast-forwarded" in result.output
        assert (in_repo / "two.txt").is_file()


class TestGitSyncSafetyRails:
    def test_dirty_tree_blocks_switch(self, in_repo: Path) -> None:
        _git(in_repo, "switch", "-c", "feat/foo")
        (in_repo / "scratch.txt").write_text("dirty\n", encoding="utf-8")
        result = invoke_under_group(git_group, ["sync"])
        assert result.exit_code != 0
        assert "uncommitted" in result.output

    def test_diverged_history_refuses(self, in_repo: Path, linked: tuple[Path, Path]) -> None:
        work, bare = linked
        (work / "local.txt").write_text("L\n", encoding="utf-8")
        _git(work, "add", "local.txt")
        _git(work, "commit", "-m", "local-only")
        advance_origin(work, bare, filename="remote.txt")
        result = invoke_under_group(git_group, ["sync"])
        assert result.exit_code != 0
        assert "diverged" in result.output


class TestGitPrune:
    def test_prune_deletes_gone_keeps_active(
        self, in_repo: Path, linked: tuple[Path, Path]
    ) -> None:
        work, bare = linked
        squash_merge_and_delete_remote(work, bare, branch="feat/squashed")
        # An active feature branch whose upstream is still alive.
        _git(in_repo, "switch", "-c", "feat/active")
        (in_repo / "a.txt").write_text("a\n", encoding="utf-8")
        _git(in_repo, "add", "a.txt")
        _git(in_repo, "commit", "-m", "active")
        _git(in_repo, "push", "-u", "origin", "feat/active")
        _git(in_repo, "switch", "main")

        result = invoke_under_group(git_group, ["prune", "--yes"])
        assert result.exit_code == 0, result.output
        branches = _branch_list(in_repo)
        assert "feat/squashed" not in branches
        assert "feat/active" in branches

    def test_dry_run_lists_but_does_not_delete(
        self, in_repo: Path, linked: tuple[Path, Path]
    ) -> None:
        work, bare = linked
        squash_merge_and_delete_remote(work, bare, branch="feat/squashed")

        result = invoke_under_group(git_group, ["prune", "--yes", "--dry-run"])
        assert result.exit_code == 0, result.output
        assert "DRY-RUN" in result.output
        assert "feat/squashed" in result.output
        # Nothing actually deleted.
        assert "feat/squashed" in _branch_list(in_repo)

    def test_no_prunable_branches_is_clean(self, in_repo: Path) -> None:
        result = invoke_under_group(git_group, ["prune", "--yes"])
        assert result.exit_code == 0, result.output
        assert "no prunable branches" in result.output


class TestGitSyncPruneGone:
    def test_sync_prune_gone_deletes_squashed(
        self, in_repo: Path, linked: tuple[Path, Path]
    ) -> None:
        work, bare = linked
        squash_merge_and_delete_remote(work, bare, branch="feat/squashed")

        result = invoke_under_group(git_group, ["sync", "--prune-gone", "--yes"])
        assert result.exit_code == 0, result.output
        assert "feat/squashed" not in _branch_list(in_repo)

    def test_prune_merged_alias_still_works(self, in_repo: Path, linked: tuple[Path, Path]) -> None:
        work, bare = linked
        squash_merge_and_delete_remote(work, bare, branch="feat/squashed")

        result = invoke_under_group(git_group, ["sync", "--prune-merged", "--yes"])
        assert result.exit_code == 0, result.output
        assert "feat/squashed" not in _branch_list(in_repo)


class TestSyncMainAlias:
    def test_alias_runs_the_same_path(self, in_repo: Path) -> None:
        result = invoke_under_group(sync_main_alias, [])
        assert result.exit_code == 0, result.output
        assert "already up to date" in result.output


class TestGitEnsurePolicy:
    def test_dry_run_reports_policy_without_calling_gh(
        self, in_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from cataforge.application.services import git_hygiene

        _git(in_repo, "remote", "set-url", "origin", "https://github.com/owner/repo.git")

        real = git_hygiene.run_proc

        def guard(argv, **kwargs):
            assert argv[:1] != ["gh"], "gh must not be called under --dry-run"
            return real(argv, **kwargs)

        monkeypatch.setattr(git_hygiene, "run_proc", guard)

        result = invoke_under_group(git_group, ["ensure-policy", "--dry-run"])
        assert result.exit_code == 0, result.output
        assert "delete_branch_on_merge=true" in result.output

    def test_non_github_remote_refuses(self, in_repo: Path) -> None:
        result = invoke_under_group(git_group, ["ensure-policy", "--dry-run"])
        assert result.exit_code != 0
        assert "not a GitHub remote" in result.output
