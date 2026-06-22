"""GitHubRepo — remote-URL parsing and the ``gh pr`` merged probe.

URL parsing is exercised through :meth:`GitHubRepo.from_remote` against a
tiny git stub; the ``gh`` shell-out is pinned by a fake ``run_proc`` that
records the exact argv so the ``--state merged --head <branch>`` contract
can't drift silently.
"""

from __future__ import annotations

import json
import subprocess
from typing import Any

import pytest

from cataforge.application.services import git_hygiene
from cataforge.application.services.git_hygiene import GitHubRepo
from cataforge.core.schema.framework import FrameworkGitRemotePolicy


class _UrlGit:
    """Minimal GitWorkTree stand-in returning a fixed remote URL."""

    def __init__(self, url: str | None) -> None:
        self._url = url

    def remote_url(self, remote: str = "origin") -> str | None:
        return self._url


class TestFromRemote:
    def test_parses_ssh_url(self) -> None:
        repo = GitHubRepo.from_remote(_UrlGit("git@github.com:owner/repo.git"))
        assert repo is not None
        assert repo.slug == "owner/repo"

    def test_parses_https_url(self) -> None:
        repo = GitHubRepo.from_remote(_UrlGit("https://github.com/owner/repo.git"))
        assert repo is not None
        assert repo.slug == "owner/repo"

    def test_parses_https_url_without_git_suffix(self) -> None:
        repo = GitHubRepo.from_remote(_UrlGit("https://github.com/owner/repo"))
        assert repo is not None
        assert repo.slug == "owner/repo"

    def test_no_remote_returns_none(self) -> None:
        assert GitHubRepo.from_remote(_UrlGit(None)) is None

    def test_non_github_remote_returns_none(self) -> None:
        # A local bare-repo path (the offline test origin) is not GitHub.
        assert GitHubRepo.from_remote(_UrlGit("/tmp/x/origin.git")) is None
        assert GitHubRepo.from_remote(_UrlGit("https://gitlab.com/o/r.git")) is None


def _fake_run(captured: list[list[str]], stdout: str, returncode: int = 0):
    def runner(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured.append(list(argv))
        return subprocess.CompletedProcess(list(argv), returncode, stdout, "")

    return runner


class TestPrIsMerged:
    def test_true_when_gh_returns_a_merged_pr(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: list[list[str]] = []
        monkeypatch.setattr(git_hygiene, "run_proc", _fake_run(captured, '[{"number": 7}]'))
        assert GitHubRepo("owner/repo").pr_is_merged("feat/x") is True
        argv = captured[0]
        assert argv[:2] == ["gh", "pr"]
        assert "--state" in argv and argv[argv.index("--state") + 1] == "merged"
        assert "--head" in argv and argv[argv.index("--head") + 1] == "feat/x"
        assert "--repo" in argv and argv[argv.index("--repo") + 1] == "owner/repo"

    def test_false_when_gh_returns_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: list[list[str]] = []
        monkeypatch.setattr(git_hygiene, "run_proc", _fake_run(captured, "[]"))
        assert GitHubRepo("owner/repo").pr_is_merged("feat/x") is False


def _policy_fake(captured: list[list[str]], get_payload: dict[str, Any]):
    """Fake run_proc: capture argv, answer GET with ``get_payload``, ack PATCH."""

    def runner(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured.append(list(argv))
        stdout = "{}" if "PATCH" in argv else json.dumps(get_payload)
        return subprocess.CompletedProcess(list(argv), 0, stdout, "")

    return runner


class TestEnsureMergePolicy:
    def test_issues_exact_patch_when_drifted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: list[list[str]] = []
        drifted = {
            "delete_branch_on_merge": False,
            "allow_squash_merge": True,
            "allow_merge_commit": True,
            "allow_rebase_merge": True,
        }
        monkeypatch.setattr(git_hygiene, "run_proc", _policy_fake(captured, drifted))
        change = GitHubRepo("owner/repo").ensure_merge_policy(FrameworkGitRemotePolicy())
        assert change.changed is True
        # captured[0] is the GET; captured[1] is the PATCH — pinned exactly.
        assert captured[1] == [
            "gh",
            "api",
            "--method",
            "PATCH",
            "repos/owner/repo",
            "-f",
            "delete_branch_on_merge=true",
            "-f",
            "allow_squash_merge=true",
            "-f",
            "allow_merge_commit=false",
            "-f",
            "allow_rebase_merge=false",
        ]

    def test_dry_run_calls_no_gh(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: list[list[str]] = []
        monkeypatch.setattr(git_hygiene, "run_proc", _policy_fake(captured, {}))
        change = GitHubRepo("owner/repo").ensure_merge_policy(
            FrameworkGitRemotePolicy(), dry_run=True
        )
        assert change.changed is True
        assert change.dry_run is True
        assert "delete_branch_on_merge" in change.fields
        assert captured == []  # no gh call at all under dry-run

    def test_noop_when_already_compliant(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: list[list[str]] = []
        compliant = {
            "delete_branch_on_merge": True,
            "allow_squash_merge": True,
            "allow_merge_commit": False,
            "allow_rebase_merge": False,
        }
        monkeypatch.setattr(git_hygiene, "run_proc", _policy_fake(captured, compliant))
        change = GitHubRepo("owner/repo").ensure_merge_policy(FrameworkGitRemotePolicy())
        assert change.changed is False
        # GET only, no PATCH issued — idempotent.
        assert len(captured) == 1
        assert all("PATCH" not in c for c in captured)
