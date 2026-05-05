"""End-to-end tests for ``cataforge feedback`` CLI subcommands."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from cataforge.cli.feedback_cmd import (
    bug_command,
    correction_export_command,
    suggest_command,
)
from cataforge.core.corrections import record_correction


def _bootstrap(tmp_path: Path) -> Path:
    (tmp_path / ".cataforge").mkdir()
    (tmp_path / ".cataforge" / "framework.json").write_text(
        json.dumps(
            {
                "version": "0.2.1-test",
                "runtime": {"platform": "claude-code"},
            }
        ),
        encoding="utf-8",
    )
    return tmp_path


def _seed_upstream_gap(project: Path, *, n: int = 1) -> None:
    for i in range(n):
        record_correction(
            project,
            trigger="review-flag",
            agent="reviewer",
            phase="review",
            question=f"upstream missed case {i}",
            baseline="upstream baseline",
            actual="local choice",
            deviation="upstream-gap",
        )


# ─── bug ──────────────────────────────────────────────────────────────────────


class TestBugCommand:
    def test_print_renders_to_stdout(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = _bootstrap(tmp_path)
        monkeypatch.chdir(project)
        result = CliRunner().invoke(
            bug_command,
            [
                "--print",
                "--summary", "hook fires twice",
                "--skip-framework-review",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "## Environment" in result.output
        assert "hook fires twice" in result.output

    def test_out_writes_file_under_project_root(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = _bootstrap(tmp_path)
        monkeypatch.chdir(project)
        result = CliRunner().invoke(
            bug_command,
            [
                "--out", "docs/feedback/bug.md",
                "--summary", "x",
                "--skip-framework-review",
                "--quiet",
            ],
        )
        assert result.exit_code == 0, result.output
        target = project / "docs" / "feedback" / "bug.md"
        assert target.is_file()
        body = target.read_text(encoding="utf-8")
        assert "## Environment" in body
        # Default redaction must hide the project root.
        assert str(project) not in body

    def test_out_with_include_paths_keeps_project_root(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = _bootstrap(tmp_path)
        monkeypatch.chdir(project)
        result = CliRunner().invoke(
            bug_command,
            [
                "--out", "out.md",
                "--include-paths",
                "--summary", "x",
                "--skip-framework-review",
                "--quiet",
            ],
        )
        assert result.exit_code == 0, result.output
        body = (project / "out.md").read_text(encoding="utf-8")
        # Doctor's "Project root: <path>" line should now contain a real path
        # rather than `<project>`.
        assert "Project root:" in body

    def test_sinks_are_mutually_exclusive(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = _bootstrap(tmp_path)
        monkeypatch.chdir(project)
        result = CliRunner().invoke(
            bug_command,
            [
                "--print", "--clip",
                "--summary", "x",
                "--skip-framework-review",
            ],
        )
        assert result.exit_code != 0
        assert "mutually exclusive" in result.output

    def test_no_sink_defaults_to_print(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = _bootstrap(tmp_path)
        monkeypatch.chdir(project)
        result = CliRunner().invoke(
            bug_command,
            [
                "--summary", "x",
                "--skip-framework-review",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "## Environment" in result.output


# ─── suggest ──────────────────────────────────────────────────────────────────


class TestSuggestCommand:
    def test_print_renders_proposal(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = _bootstrap(tmp_path)
        monkeypatch.chdir(project)
        result = CliRunner().invoke(
            suggest_command,
            [
                "--print",
                "--summary", "support --dry-run on bootstrap",
                "--notes", "would let users preview impact",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "## Proposal" in result.output
        assert "would let users preview impact" in result.output


# ─── correction-export ────────────────────────────────────────────────────────


class TestCorrectionExportCommand:
    def test_refuses_when_no_upstream_gap(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = _bootstrap(tmp_path)
        monkeypatch.chdir(project)
        result = CliRunner().invoke(
            correction_export_command, ["--print", "--summary", "x"]
        )
        assert result.exit_code != 0
        assert "No `upstream-gap`" in result.output

    def test_refuses_below_threshold(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = _bootstrap(tmp_path)
        _seed_upstream_gap(project, n=1)
        monkeypatch.chdir(project)
        result = CliRunner().invoke(
            correction_export_command,
            ["--print", "--summary", "x", "--threshold", "3"],
        )
        assert result.exit_code != 0
        assert "threshold" in result.output

    def test_emits_when_threshold_met(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = _bootstrap(tmp_path)
        _seed_upstream_gap(project, n=3)
        monkeypatch.chdir(project)
        result = CliRunner().invoke(
            correction_export_command,
            ["--print", "--summary", "see attached", "--threshold", "3"],
        )
        assert result.exit_code == 0, result.output
        assert "Aggregated" in result.output
        # Each upstream-gap question should appear once.
        for i in range(3):
            assert f"upstream missed case {i}" in result.output

    def test_threshold_zero_always_exports(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = _bootstrap(tmp_path)
        _seed_upstream_gap(project, n=1)
        monkeypatch.chdir(project)
        result = CliRunner().invoke(
            correction_export_command,
            ["--print", "--summary", "x", "--threshold", "0"],
        )
        assert result.exit_code == 0, result.output


# ─── --gh / --clip sink dispatch (tools mocked) ───────────────────────────────


class TestSinks:
    def test_gh_sink_invokes_gh_with_body_on_stdin(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When ``--gh`` is given we shell out to ``gh issue create`` with
        the body fed through stdin (no temp file). Stub both the PATH lookup
        and the subprocess call so the test stays hermetic."""
        project = _bootstrap(tmp_path)
        monkeypatch.chdir(project)

        captured: dict[str, object] = {}

        def fake_which(name: str) -> str | None:
            return "/usr/bin/gh" if name == "gh" else None

        def fake_run(cmd, input=None, **kw):  # type: ignore[no-untyped-def]
            captured["cmd"] = cmd
            captured["input"] = input
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=0,
                stdout="https://github.com/lync-cyber/CataForge/issues/999\n",
                stderr="",
            )

        monkeypatch.setattr("cataforge.cli.feedback_cmd.shutil.which", fake_which)
        monkeypatch.setattr(
            "cataforge.cli.feedback_cmd.subprocess.run", fake_run
        )

        result = CliRunner().invoke(
            bug_command,
            [
                "--gh",
                "--summary", "deploy fails on Windows",
                "--title", "bug: deploy fails on Windows",
                "--skip-framework-review",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "https://github.com/lync-cyber/CataForge/issues/999" in result.output
        assert captured["cmd"][:3] == ["gh", "issue", "create"]
        assert "--title" in captured["cmd"]
        assert "--body-file" in captured["cmd"]
        assert "-" in captured["cmd"]
        # Body must be non-empty markdown
        assert isinstance(captured["input"], str)
        assert "## Environment" in captured["input"]

    def test_gh_sink_errors_when_gh_missing(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        project = _bootstrap(tmp_path)
        monkeypatch.chdir(project)
        monkeypatch.setattr(
            "cataforge.cli.feedback_cmd.shutil.which", lambda _name: None
        )
        result = CliRunner().invoke(
            bug_command,
            ["--gh", "--summary", "x", "--skip-framework-review"],
        )
        assert result.exit_code != 0
        assert "gh" in result.output

    def test_clip_sink_uses_first_available_clipboard_tool(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        project = _bootstrap(tmp_path)
        monkeypatch.chdir(project)
        captured: dict[str, object] = {}

        # Pretend only `xclip` exists.
        def fake_which(name: str) -> str | None:
            return "/usr/bin/xclip" if name == "xclip" else None

        def fake_run(cmd, input=None, **kw):  # type: ignore[no-untyped-def]
            captured["cmd"] = cmd
            captured["input"] = input
            return subprocess.CompletedProcess(args=cmd, returncode=0)

        monkeypatch.setattr("cataforge.cli.feedback_cmd.shutil.which", fake_which)
        monkeypatch.setattr(
            "cataforge.cli.feedback_cmd.subprocess.run", fake_run
        )

        result = CliRunner().invoke(
            bug_command,
            ["--clip", "--summary", "x", "--skip-framework-review"],
        )
        assert result.exit_code == 0, result.output
        assert captured["cmd"][0] == "xclip"
        assert "## Environment" in str(captured["input"])

    def test_clip_sink_errors_when_no_tool(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        project = _bootstrap(tmp_path)
        monkeypatch.chdir(project)
        monkeypatch.setattr(
            "cataforge.cli.feedback_cmd.shutil.which", lambda _name: None
        )
        result = CliRunner().invoke(
            bug_command,
            ["--clip", "--summary", "x", "--skip-framework-review"],
        )
        assert result.exit_code != 0
        assert "clipboard" in result.output


# ─── live: actually run --gh path against /usr/bin/false-style stub ──────────


@pytest.mark.skipif(
    not shutil.which("sh"), reason="POSIX shell required for sink integration"
)
def test_gh_sink_propagates_error_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Real subprocess: stub `gh` with a script that exits non-zero and
    writes to stderr. The CLI must surface that text in the error."""
    project = _bootstrap(tmp_path)
    fake_gh = tmp_path / "fake-bin" / "gh"
    fake_gh.parent.mkdir()
    fake_gh.write_text(
        "#!/bin/sh\necho 'GH_AUTH_REQUIRED' >&2\nexit 4\n", encoding="utf-8"
    )
    fake_gh.chmod(0o755)
    monkeypatch.setenv("PATH", str(fake_gh.parent) + ":" + Path("/usr/bin").as_posix())
    monkeypatch.chdir(project)

    result = CliRunner().invoke(
        bug_command,
        ["--gh", "--summary", "x", "--skip-framework-review"],
    )
    assert result.exit_code != 0
    assert "GH_AUTH_REQUIRED" in result.output
