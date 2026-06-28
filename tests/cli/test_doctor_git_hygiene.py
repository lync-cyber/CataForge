"""doctor git-hygiene check — reports gone branches, never gates (returns 0)."""

from __future__ import annotations

from pathlib import Path

import pytest

from cataforge.application.services.git_hygiene import GitWorkTree
from cataforge.core.config import ConfigManager
from cataforge.interface.cli.doctor.git_hygiene import check_git_hygiene
from tests.support.gitrepo import build_linked_repos, squash_merge_and_delete_remote


def test_reports_gone_branch_count_and_remedy(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    work, _bare = build_linked_repos(tmp_path)
    squash_merge_and_delete_remote(work, tmp_path / "origin.git", branch="feat/squashed")
    GitWorkTree(work).fetch_prune()  # make the [gone] state current

    rc = check_git_hygiene(ConfigManager(work))
    out = capsys.readouterr().out
    assert rc == 0  # advisory: branch hygiene is never a CI failure
    assert "feat/squashed" in out
    assert "cataforge git prune" in out


def test_clean_repo_reports_ok(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    work, _bare = build_linked_repos(tmp_path)
    rc = check_git_hygiene(ConfigManager(work))
    assert rc == 0
    out = capsys.readouterr().out
    assert "branches: OK" in out


def test_outside_repo_is_informational(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / ".cataforge").mkdir()
    (tmp_path / ".cataforge" / "framework.json").write_text(
        '{"version": "0.1.0"}', encoding="utf-8"
    )
    rc = check_git_hygiene(ConfigManager(tmp_path))
    assert rc == 0
    assert "skipped" in capsys.readouterr().out


def test_reports_missing_gitattributes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    work, _bare = build_linked_repos(tmp_path)

    rc = check_git_hygiene(ConfigManager(work))
    out = capsys.readouterr().out

    assert rc == 0
    assert ".gitattributes: WARN missing" in out


def test_reports_incomplete_gitattributes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    work, _bare = build_linked_repos(tmp_path)
    (work / ".gitattributes").write_text("* text=auto\n", encoding="utf-8")

    rc = check_git_hygiene(ConfigManager(work))
    out = capsys.readouterr().out

    assert rc == 0
    assert ".gitattributes: WARN missing eol=" in out
