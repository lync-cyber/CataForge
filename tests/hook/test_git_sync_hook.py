"""SessionStart git_sync hook — fetch + fast-forward clean main + prune gone.

Best-effort only: opening a session must never switch branches, never touch a
dirty tree, and never raise. These tests pin those safety invariants against a
real on-disk repo (offline, bare sibling = origin).
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

import pytest

from cataforge.application.services import git_hygiene
from cataforge.core.paths import ProjectPaths
from cataforge.runtime.hook.scripts.git_sync import _run_git_sync
from tests.support.gitrepo import (
    advance_origin,
    build_linked_repos,
    squash_merge_and_delete_remote,
)


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=cwd, text=True, capture_output=True, check=True, encoding="utf-8"
    )


def _set_session_sync(work: Path, **overrides: object) -> None:
    fw = work / ".cataforge" / "framework.json"
    data = json.loads(fw.read_text(encoding="utf-8"))
    data.setdefault("git", {})["session_sync"] = overrides
    fw.write_text(json.dumps(data), encoding="utf-8")


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    work, _bare = build_linked_repos(tmp_path)
    monkeypatch.chdir(work)
    return work


class TestFastForward:
    def test_fetches_and_fast_forwards_clean_main(self, repo: Path, tmp_path: Path) -> None:
        advance_origin(repo, tmp_path / "origin.git")
        _run_git_sync()
        assert (repo / "two.txt").is_file()


class TestSafetyInvariants:
    def test_on_feature_branch_never_switches(self, repo: Path, tmp_path: Path) -> None:
        _git(repo, "switch", "-c", "feat/x")
        advance_origin(repo, tmp_path / "origin.git")
        _run_git_sync()
        assert git_hygiene.GitWorkTree(repo).current_branch() == "feat/x"
        # main must not have been fast-forwarded while we were off it.
        assert not (repo / "two.txt").is_file()

    def test_dirty_tree_degrades_silently(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (repo / "scratch.txt").write_text("dirty\n", encoding="utf-8")
        _run_git_sync()
        assert "Traceback" not in capsys.readouterr().err
        assert (repo / "scratch.txt").read_text(encoding="utf-8") == "dirty\n"

    def test_never_raises_outside_repo(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        outside = tmp_path / "nowhere"
        outside.mkdir()
        monkeypatch.chdir(outside)
        _run_git_sync()  # best-effort: must return, never raise


class TestPrune:
    def test_prunes_gone_branch(self, repo: Path, tmp_path: Path) -> None:
        squash_merge_and_delete_remote(repo, tmp_path / "origin.git", branch="feat/squashed")
        _git(repo, "switch", "-c", "feat/active")
        (repo / "a.txt").write_text("a\n", encoding="utf-8")
        _git(repo, "add", "a.txt")
        _git(repo, "commit", "-m", "active")
        _git(repo, "push", "-u", "origin", "feat/active")
        _git(repo, "switch", "main")

        _run_git_sync()

        branches = _git(repo, "branch", "--list").stdout
        assert "feat/squashed" not in branches
        assert "feat/active" in branches


class TestDegradation:
    def test_offline_fetch_degrades_to_silence(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        def _boom(self: object, *a: object, **k: object) -> None:
            raise subprocess.TimeoutExpired(cmd=["git", "fetch"], timeout=10)

        monkeypatch.setattr(git_hygiene.GitWorkTree, "fetch_prune", _boom)
        _run_git_sync()
        err = capsys.readouterr().err
        assert "Traceback" not in err
        assert "skipped" in err


class TestConfigGating:
    def test_disabled_config_is_noop(self, repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _set_session_sync(repo, enabled=False)
        calls: list[int] = []
        monkeypatch.setattr(
            git_hygiene.GitWorkTree, "fetch_prune", lambda self, *a, **k: calls.append(1)
        )
        _run_git_sync()
        assert calls == []

    def test_debounce_skips_recent_then_fetches_when_stale(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[int] = []
        monkeypatch.setattr(
            git_hygiene.GitWorkTree, "fetch_prune", lambda self, *a, **k: calls.append(1)
        )
        stamp = ProjectPaths(repo).git_sync_stamp
        stamp.parent.mkdir(parents=True, exist_ok=True)
        stamp.write_text("", encoding="utf-8")  # fresh stamp → debounced

        _run_git_sync()
        assert calls == []

        old = time.time() - 3600
        os.utime(stamp, (old, old))  # expire the stamp
        _run_git_sync()
        assert calls == [1]
