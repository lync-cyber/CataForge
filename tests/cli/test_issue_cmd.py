"""Tests for ``cataforge issue triage`` + ``cataforge issue close``.

We mock ``gh`` so the suite runs offline. ``triage`` exercises the body
parser + verdict classifier; ``close`` exercises the comment templates +
gh invocation contract.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from cataforge.application.services import issue as issue_svc
from cataforge.interface.cli import issue_cmd
from cataforge.interface.cli.issue_cmd import close_command, triage_command
from tests.cli.conftest import invoke_under_group


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

    monkeypatch.setattr(issue_svc, "run_proc", fake_run)
    monkeypatch.setattr(issue_cmd.shutil, "which", lambda _: "/usr/local/bin/gh")


def _patch_gh_per_label(
    monkeypatch: pytest.MonkeyPatch,
    *,
    issues_by_label: dict[str | None, list[dict]],
) -> list[list[str]]:
    """gh stub that returns a different payload depending on ``--label X``.

    Pass ``None`` as the key for the labelless fallback call. Returns a
    list of captured commands so assertions can inspect how many calls were
    issued and with which label each.
    """
    captured: list[list[str]] = []

    def fake_run(cmd, **kwargs):  # noqa: ANN001
        captured.append(list(cmd))
        assert cmd[0] == "gh"
        label = None
        if "--label" in cmd:
            label = cmd[cmd.index("--label") + 1]
        payload = issues_by_label.get(label, [])
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout=json.dumps(payload), stderr=""
        )

    monkeypatch.setattr(issue_svc, "run_proc", fake_run)
    monkeypatch.setattr(issue_cmd.shutil, "which", lambda _: "/usr/local/bin/gh")
    return captured


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
        result = invoke_under_group(triage_command, ["--dry-run"])
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
        result = invoke_under_group(triage_command, [])
        assert result.exit_code == 0, result.output
        assert "confirmed" in result.output
        draft_path = (
            project / "docs" / "reviews" / "triage" / ("SKILL-IMPROVE-tdd-engine-issue-42.md")
        )
        assert draft_path.is_file()
        text = draft_path.read_text(encoding="utf-8")
        assert "status: triage-draft" in text
        assert "tdd-engine" in text

    def test_unrelated_issue_skipped(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
        result = invoke_under_group(triage_command, [])
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
        result = invoke_under_group(triage_command, [])
        assert result.exit_code == 0
        assert "needs-repro" in result.output

    # ─── issue #115 P6: label union (OR) ──────────────────────────────────

    def test_labels_use_or_semantics_across_separate_gh_calls(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`gh issue list --label X --label Y` is AND — we need one call per label.

        Issue #115 P6: a 'feedback: …' issue carrying only `enhancement`
        was being dropped from triage because the default label union
        ``{bug, enhancement}`` was passed as two `--label` flags. After
        the fix we issue one `gh` call per label and merge by issue number.
        """
        project = _bootstrap(tmp_path)
        # Configure two labels so the per-call loop has more than one pass.
        (project / ".cataforge" / "framework.json").write_text(
            json.dumps(
                {
                    "version": "0.0.0-test",
                    "runtime": {"platform": "claude-code"},
                    "upgrade": {"source": {"repo": "fake/repo"}},
                    "feedback": {
                        "gh": {
                            "labels": {
                                "bug": ["bug"],
                                "suggest": ["enhancement"],
                            }
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        monkeypatch.chdir(project)
        captured = _patch_gh_per_label(
            monkeypatch,
            issues_by_label={
                "bug": [
                    {
                        "number": 100,
                        "title": "bug only",
                        "body": "Package: 0.0.0-test\n\nbroken",
                        "createdAt": "2026-04-01T00:00:00Z",
                        "url": "https://example/100",
                        "labels": [{"name": "bug"}],
                    }
                ],
                "enhancement": [
                    {
                        "number": 115,
                        "title": "enhancement only",
                        "body": "Package: 0.0.0-test\n\nsuggestion",
                        "createdAt": "2026-04-02T00:00:00Z",
                        "url": "https://example/115",
                        "labels": [{"name": "enhancement"}],
                    }
                ],
            },
        )

        result = invoke_under_group(triage_command, ["--dry-run"])
        assert result.exit_code == 0, result.output

        # Both issues should appear in the verdict table.
        assert "#100" in result.output, result.output
        assert "#115" in result.output, result.output

        # Two gh calls — one per label, each with exactly one --label flag.
        list_calls = [c for c in captured if "list" in c]
        assert len(list_calls) == 2, list_calls
        label_args = []
        for c in list_calls:
            assert c.count("--label") == 1, c
            label_args.append(c[c.index("--label") + 1])
        assert sorted(label_args) == ["bug", "enhancement"]

    def test_labels_deduplicated_across_label_passes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An issue carrying both labels appears once, not twice.

        After the OR-by-label change in #115 P6, the merge step must
        deduplicate by issue number so the verdict table doesn't double-count.
        """
        project = _bootstrap(tmp_path)
        (project / ".cataforge" / "framework.json").write_text(
            json.dumps(
                {
                    "version": "0.0.0-test",
                    "runtime": {"platform": "claude-code"},
                    "upgrade": {"source": {"repo": "fake/repo"}},
                    "feedback": {
                        "gh": {
                            "labels": {
                                "bug": ["bug"],
                                "suggest": ["enhancement"],
                            }
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        monkeypatch.chdir(project)
        dual = {
            "number": 200,
            "title": "carries both labels",
            "body": "Package: 0.0.0-test\n\ndual",
            "createdAt": "2026-04-03T00:00:00Z",
            "url": "https://example/200",
            "labels": [{"name": "bug"}, {"name": "enhancement"}],
        }
        _patch_gh_per_label(
            monkeypatch,
            issues_by_label={"bug": [dual], "enhancement": [dual]},
        )

        result = invoke_under_group(triage_command, ["--dry-run"])
        assert result.exit_code == 0, result.output
        # The header line says "N issue(s) fetched"; verify it says 1, not 2.
        assert "1 issue(s) fetched" in result.output
        # Issue number appears exactly once in the verdict table.
        assert result.output.count("#200") == 1

    # ─── issue #115 P7: version regex covers issue-template forms ────────

    def test_version_regex_matches_issue_template_h3_form(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`### CataForge version\\n\\n0.4.0` parses as reported_version=0.4.0.

        This is the form produced by ``cataforge feedback suggest --gh``
        in the GitHub issue template body. Pre-fix it was unrecognised
        and the issue fell through to verdict=unrelated.
        """
        project = _bootstrap(tmp_path)
        monkeypatch.chdir(project)
        from cataforge import __version__

        body = (
            "### Bundle kind\n\nsuggest\n\n"
            "### CataForge version\n\n"
            f"{__version__}\n\n"
            "### Generated body\n\n"
            "framework-review FAIL skill: tdd-engine — light-mode threshold off\n"
        )
        _patch_gh(
            monkeypatch,
            issues=[
                {
                    "number": 115,
                    "title": "feedback: TDD light-mode threshold off",
                    "body": body,
                    "createdAt": "2026-05-22T00:00:00Z",
                    "url": "https://example/115",
                    "labels": [{"name": "enhancement"}],
                }
            ],
        )
        result = invoke_under_group(triage_command, [])
        assert result.exit_code == 0, result.output
        # H3 form must be recognised → matches installed version → confirmed.
        assert "confirmed" in result.output, result.output
        assert "unrelated" not in result.output

    def test_version_regex_matches_bold_env_form(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`- **CataForge package**: \\`0.4.0\\`` parses as reported_version=0.4.0.

        This is the form produced by ``_render_environment`` in
        ``cataforge.core.feedback`` — markdown bold wrapping defeats the
        legacy header regex (issue #115 P7).
        """
        project = _bootstrap(tmp_path)
        monkeypatch.chdir(project)
        from cataforge import __version__

        body = (
            "## Environment\n\n"
            f"- **CataForge package**: `{__version__}`\n"
            f"- **Scaffold version**: `{__version__}`\n\n"
            "framework-review FAIL skill: tdd-engine — light-mode threshold off\n"
        )
        _patch_gh(
            monkeypatch,
            issues=[
                {
                    "number": 116,
                    "title": "feedback: TDD light-mode threshold off",
                    "body": body,
                    "createdAt": "2026-05-22T00:00:00Z",
                    "url": "https://example/116",
                    "labels": [{"name": "enhancement"}],
                }
            ],
        )
        result = invoke_under_group(triage_command, [])
        assert result.exit_code == 0, result.output
        assert "confirmed" in result.output, result.output


class TestClose:
    def test_fixed_dry_run_renders_template(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = _bootstrap(tmp_path)
        monkeypatch.chdir(project)
        result = invoke_under_group(
            close_command,
            ["104", "--verdict", "fixed", "--pr", "108", "--dry-run"],
        )
        assert result.exit_code == 0, result.output
        assert "Fixed in v" in result.output
        assert "(PR #108)" in result.output
        assert "dry-run" in result.output

    def test_wontfix_dry_run_renders_reason(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = _bootstrap(tmp_path)
        monkeypatch.chdir(project)
        result = invoke_under_group(
            close_command,
            [
                "102",
                "--verdict",
                "wontfix",
                "--reason",
                "doc_id slug-only is intentional design",
                "--dry-run",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "Wontfix" in result.output
        assert "doc_id slug-only is intentional design" in result.output

    def test_already_fixed_dry_run_renders_template(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = _bootstrap(tmp_path)
        monkeypatch.chdir(project)
        result = invoke_under_group(
            close_command,
            ["77", "--verdict", "already-fixed", "--pr", "65", "--dry-run"],
        )
        assert result.exit_code == 0, result.output
        assert "Already fixed in v" in result.output
        assert "(PR #65)" in result.output

    def test_fixed_requires_pr(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        project = _bootstrap(tmp_path)
        monkeypatch.chdir(project)
        result = invoke_under_group(close_command, ["104", "--verdict", "fixed", "--dry-run"])
        assert result.exit_code != 0
        assert "--pr" in result.output

    def test_wontfix_requires_reason(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        project = _bootstrap(tmp_path)
        monkeypatch.chdir(project)
        result = invoke_under_group(close_command, ["102", "--verdict", "wontfix", "--dry-run"])
        assert result.exit_code != 0
        assert "--reason" in result.output

    def test_invokes_gh_with_close_and_comment(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = _bootstrap(tmp_path)
        monkeypatch.chdir(project)
        captured: list[list[str]] = []

        def fake_run(cmd, **kwargs):  # noqa: ANN001
            captured.append(list(cmd))
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

        monkeypatch.setattr(issue_cmd, "run_proc", fake_run)
        monkeypatch.setattr(issue_cmd.shutil, "which", lambda _: "/usr/local/bin/gh")

        result = invoke_under_group(
            close_command,
            ["104", "--verdict", "fixed", "--pr", "108", "--repo", "fake/repo"],
        )
        assert result.exit_code == 0, result.output
        assert len(captured) == 1
        cmd = captured[0]
        assert cmd[:5] == ["gh", "issue", "close", "104", "-R"]
        assert "fake/repo" in cmd
        assert "--comment" in cmd
        comment = cmd[cmd.index("--comment") + 1]
        assert "Fixed in v" in comment
        assert "(PR #108)" in comment

    def test_extra_message_appended(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        project = _bootstrap(tmp_path)
        monkeypatch.chdir(project)
        result = invoke_under_group(
            close_command,
            [
                "104",
                "--verdict",
                "fixed",
                "--pr",
                "108",
                "--message",
                "Triage: docs/reviews/triage/foo.md",
                "--dry-run",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "Fixed in v" in result.output
        assert "Triage: docs/reviews/triage/foo.md" in result.output


class TestGhFailurePaths:
    def test_triage_surfaces_gh_rate_limit_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = _bootstrap(tmp_path)
        monkeypatch.chdir(project)
        monkeypatch.setattr(issue_cmd.shutil, "which", lambda _: "/usr/local/bin/gh")

        def fake_run(cmd, **kwargs):  # noqa: ANN001
            return subprocess.CompletedProcess(
                args=cmd, returncode=1, stdout="", stderr="error: API rate limit exceeded"
            )

        monkeypatch.setattr(issue_svc, "run_proc", fake_run)
        result = invoke_under_group(triage_command, ["--repo", "fake/repo"])
        assert result.exit_code != 0
        assert "rate limit" in result.output

    def test_close_surfaces_gh_auth_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = _bootstrap(tmp_path)
        monkeypatch.chdir(project)
        monkeypatch.setattr(issue_cmd.shutil, "which", lambda _: "/usr/local/bin/gh")

        def fake_run(cmd, **kwargs):  # noqa: ANN001
            return subprocess.CompletedProcess(
                args=cmd, returncode=1, stdout="", stderr="error: authentication required"
            )

        monkeypatch.setattr(issue_cmd, "run_proc", fake_run)
        result = invoke_under_group(
            close_command,
            ["104", "--verdict", "fixed", "--pr", "108", "--repo", "fake/repo"],
        )
        assert result.exit_code != 0
        assert "authentication" in result.output


class TestTriageGhParams:
    def test_gh_cmd_carries_repo_json_state_flags(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = _bootstrap(tmp_path)
        monkeypatch.chdir(project)
        captured: list[list[str]] = []

        def fake_run(cmd, **kwargs):  # noqa: ANN001
            captured.append(list(cmd))
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="[]", stderr="")

        monkeypatch.setattr(issue_svc, "run_proc", fake_run)
        monkeypatch.setattr(issue_cmd.shutil, "which", lambda _: "/usr/local/bin/gh")
        result = invoke_under_group(triage_command, ["--repo", "fake/repo", "--dry-run"])
        assert result.exit_code == 0, result.output
        assert len(captured) >= 1
        cmd = captured[0]
        assert cmd[0] == "gh"
        assert "-R" in cmd
        repo_idx = cmd.index("-R")
        assert cmd[repo_idx + 1] == "fake/repo"
        assert "--json" in cmd
        assert "--state" in cmd
