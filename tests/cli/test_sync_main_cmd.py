"""Tests for ``cataforge sync-main`` — fast-forward + branch prune logic.

These exercise the command surface against a real on-disk git repo so the
contract with ``git`` itself stays honest. ``origin`` is faked via a bare
sibling repo so we never touch the network.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from cataforge.cli.sync_cmd import sync_main_command


def _run(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=True,
        encoding="utf-8",
    )


@pytest.fixture
def linked_repos(tmp_path: Path) -> tuple[Path, Path]:
    """Build a (working-copy, bare-origin) pair with one commit on main."""
    work = tmp_path / "work"
    bare = tmp_path / "origin.git"
    work.mkdir()
    _run(work, "init", "-b", "main")
    _run(work, "config", "user.email", "test@example.com")
    _run(work, "config", "user.name", "test")
    (work / "README.md").write_text("hello\n", encoding="utf-8")
    _run(work, "add", "README.md")
    _run(work, "commit", "-m", "init")
    _run(tmp_path, "init", "--bare", "-b", "main", str(bare))
    _run(work, "remote", "add", "origin", str(bare))
    _run(work, "push", "-u", "origin", "main")
    # Set origin/HEAD so detection succeeds.
    _run(work, "remote", "set-head", "origin", "main")
    # Drop a project marker so resolve_root() lands on `work`.
    (work / ".cataforge").mkdir()
    (work / ".cataforge" / "framework.json").write_text(
        '{"version": "0.0.0-test"}', encoding="utf-8"
    )
    return work, bare


@pytest.fixture
def in_repo(linked_repos, monkeypatch: pytest.MonkeyPatch) -> Path:
    work, _ = linked_repos
    monkeypatch.chdir(work)
    return work


class TestSyncMainHappyPath:
    def test_already_up_to_date_is_no_op(self, in_repo: Path) -> None:
        result = CliRunner().invoke(sync_main_command, [])
        assert result.exit_code == 0, result.output
        assert "already up to date" in result.output

    def test_fast_forwards_when_origin_advances(
        self, in_repo: Path, linked_repos: tuple[Path, Path]
    ) -> None:
        work, bare = linked_repos
        # Simulate a teammate pushing a commit to origin/main from another clone.
        other = work.parent / "other"
        _run(work.parent, "clone", str(bare), "other")
        _run(other, "config", "user.email", "t@e.com")
        _run(other, "config", "user.name", "t")
        (other / "two.txt").write_text("two\n", encoding="utf-8")
        _run(other, "add", "two.txt")
        _run(other, "commit", "-m", "two")
        _run(other, "push")

        result = CliRunner().invoke(sync_main_command, [])
        assert result.exit_code == 0, result.output
        assert "fast-forwarded" in result.output
        assert (in_repo / "two.txt").is_file()


class TestSyncMainSafetyRails:
    def test_dirty_tree_blocks_switch(
        self, in_repo: Path, linked_repos: tuple[Path, Path]
    ) -> None:
        # Make a feature branch and dirty the working tree.
        _run(in_repo, "switch", "-c", "feat/foo")
        (in_repo / "scratch.txt").write_text("dirty\n", encoding="utf-8")
        result = CliRunner().invoke(sync_main_command, [])
        assert result.exit_code != 0
        assert "uncommitted changes" in result.output

    def test_diverged_history_refuses(
        self, in_repo: Path, linked_repos: tuple[Path, Path]
    ) -> None:
        work, bare = linked_repos
        # Local main gets a commit.
        (work / "local.txt").write_text("L\n", encoding="utf-8")
        _run(work, "add", "local.txt")
        _run(work, "commit", "-m", "local-only")
        # Remote main gets a *different* commit via a sibling clone.
        other = work.parent / "div"
        _run(work.parent, "clone", str(bare), "div")
        _run(other, "config", "user.email", "t@e.com")
        _run(other, "config", "user.name", "t")
        (other / "remote.txt").write_text("R\n", encoding="utf-8")
        _run(other, "add", "remote.txt")
        _run(other, "commit", "-m", "remote-only")
        _run(other, "push")
        result = CliRunner().invoke(sync_main_command, [])
        assert result.exit_code != 0
        assert "diverged" in result.output


class TestSyncMainPruneMerged:
    def test_prune_merged_deletes_merged_feature_branches(
        self, in_repo: Path, linked_repos: tuple[Path, Path]
    ) -> None:
        # Create two feature branches; merge the first into main locally
        # so it counts as fully-merged. Leave the second unmerged.
        _run(in_repo, "switch", "-c", "feat/done")
        (in_repo / "x.txt").write_text("x\n", encoding="utf-8")
        _run(in_repo, "add", "x.txt")
        _run(in_repo, "commit", "-m", "done work")
        _run(in_repo, "switch", "main")
        _run(in_repo, "merge", "--no-ff", "feat/done", "-m", "merge")
        _run(in_repo, "push")
        # Feature branch left dangling locally.
        _run(in_repo, "switch", "-c", "feat/wip")
        (in_repo / "wip.txt").write_text("wip\n", encoding="utf-8")
        _run(in_repo, "add", "wip.txt")
        _run(in_repo, "commit", "-m", "wip")
        _run(in_repo, "switch", "main")

        result = CliRunner().invoke(
            sync_main_command, ["--prune-merged", "--yes"]
        )
        assert result.exit_code == 0, result.output
        # done branch was merged → should be gone.
        branches = subprocess.run(
            ["git", "branch", "--list"],
            cwd=in_repo, text=True, capture_output=True, check=True,
        ).stdout
        assert "feat/done" not in branches
        # wip branch was not merged → should still be there.
        assert "feat/wip" in branches
