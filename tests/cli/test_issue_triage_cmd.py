"""Tests for ``cataforge issue triage`` Layer 1 verdict logic.

We mock ``gh`` calls so the test runs offline. The interesting behaviour
is the body parser + verdict classifier, exercised via the CLI surface
to keep the contract-shape under test.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from cataforge.cli import issue_cmd
from cataforge.cli.issue_cmd import triage_command


def _bootstrap(tmp_path: Path) -> Path:
    (tmp_path / ".cataforge").mkdir()
    (tmp_path / ".cataforge" / "framework.json").write_text(
        json.dumps(
            {
                "version": "0.0.0-test",
                "runtime": {"platform": "claude-code"},
                "upgrade": {"source": {"repo": "fake/repo"}},
                "feedback": {"gh": {"labels": {"bug": ["bug"]}}},
            }
        ),
        encoding="utf-8",
    )
    # Drop one skill + one agent the tests can reference.
    skills = tmp_path / ".cataforge" / "skills" / "tdd-engine"
    skills.mkdir(parents=True)
    (skills / "SKILL.md").write_text("---\nname: tdd-engine\n---\n", encoding="utf-8")
    agents = tmp_path / ".cataforge" / "agents" / "implementer"
    agents.mkdir(parents=True)
    (agents / "AGENT.md").write_text("---\nname: implementer\n---\n", encoding="utf-8")
    return tmp_path


def _patch_gh(
    monkeypatch: pytest.MonkeyPatch,
    *,
    issues: list[dict],
) -> None:
    def fake_run(cmd, **kwargs):  # noqa: ANN001
        assert cmd[0] == "gh"
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout=json.dumps(issues), stderr=""
        )

    monkeypatch.setattr(issue_cmd.subprocess, "run", fake_run)
    monkeypatch.setattr(issue_cmd.shutil, "which", lambda _: "/usr/local/bin/gh")


class TestTriage:
    def test_already_fixed_when_reported_version_older(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = _bootstrap(tmp_path)
        monkeypatch.chdir(project)
        # Reporter on an old version, current installed __version__ > 0.0.1.
        _patch_gh(
            monkeypatch,
            issues=[
                {
                    "number": 99,
                    "title": "old issue",
                    "body": "Package: 0.0.1\n\nbroken",
                    "createdAt": "2026-01-01T00:00:00Z",
                    "url": "https://example/99",
                    "labels": [],
                },
            ],
        )
        result = CliRunner().invoke(triage_command, ["--dry-run"])
        assert result.exit_code == 0, result.output
        assert "already-fixed" in result.output
        # Dry-run skips writes regardless of verdict.
        assert not (project / "docs" / "reviews" / "triage").exists()

    def test_confirmed_writes_skill_improve_draft(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = _bootstrap(tmp_path)
        monkeypatch.chdir(project)
        from cataforge import __version__
        body = (
            f"Package: {__version__}\n\n"
            "framework-review reported FAIL skill: tdd-engine — light-mode threshold off\n"
        )
        _patch_gh(
            monkeypatch,
            issues=[
                {
                    "number": 42,
                    "title": "feedback: TDD light-mode threshold off",
                    "body": body,
                    "createdAt": "2026-04-01T00:00:00Z",
                    "url": "https://example/42",
                    "labels": [{"name": "bug"}],
                },
            ],
        )
        result = CliRunner().invoke(triage_command, [])
        assert result.exit_code == 0, result.output
        assert "confirmed" in result.output
        draft_path = project / "docs" / "reviews" / "triage" / (
            "SKILL-IMPROVE-tdd-engine-issue-42.md"
        )
        assert draft_path.is_file()
        text = draft_path.read_text(encoding="utf-8")
        assert "status: triage-draft" in text
        assert "tdd-engine" in text

    def test_unrelated_issue_skipped(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = _bootstrap(tmp_path)
        monkeypatch.chdir(project)
        _patch_gh(
            monkeypatch,
            issues=[
                {
                    "number": 7,
                    "title": "Question: how to ignore vendored dirs?",
                    "body": "Hi, can someone explain ...",
                    "createdAt": "2026-04-10T00:00:00Z",
                    "url": "https://example/7",
                    "labels": [],
                },
            ],
        )
        result = CliRunner().invoke(triage_command, [])
        assert result.exit_code == 0
        assert "unrelated" in result.output
        assert not (project / "docs" / "reviews" / "triage").exists()

    def test_needs_repro_when_no_version_block(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = _bootstrap(tmp_path)
        monkeypatch.chdir(project)
        _patch_gh(
            monkeypatch,
            issues=[
                {
                    "number": 12,
                    "title": "framework-review FAIL skill: tdd-engine missing",
                    "body": "framework-review FAIL skill: tdd-engine — broken\n",
                    "createdAt": "2026-04-12T00:00:00Z",
                    "url": "https://example/12",
                    "labels": [],
                },
            ],
        )
        result = CliRunner().invoke(triage_command, [])
        assert result.exit_code == 0
        assert "needs-repro" in result.output
