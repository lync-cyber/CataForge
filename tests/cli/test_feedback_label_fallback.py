"""Tests for the new ``_to_gh`` label-fallback path in ``cataforge feedback``."""

from __future__ import annotations

import subprocess
from typing import Any

import pytest

from cataforge.core.errors import ExternalToolError
from cataforge.interface.cli.feedback import _sinks


def _completed(
    *, returncode: int = 0, stdout: str = "", stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["gh"], returncode=returncode, stdout=stdout, stderr=stderr
    )


def _patch_subprocess(
    monkeypatch: pytest.MonkeyPatch,
    *,
    side_effect_seq: list[Any],
) -> list[list[str]]:
    """Replace ``run_proc`` inside _sinks with a queue-driven fake.

    Returns the list that will collect every issued command for assertion.
    """
    calls: list[list[str]] = []
    queue = list(side_effect_seq)

    def fake_run(cmd, **kwargs):  # noqa: ANN001 — passthrough proxy
        calls.append(list(cmd))
        if not queue:
            raise AssertionError(f"unexpected extra run_proc({cmd})")
        outcome = queue.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(_sinks, "run_proc", fake_run)
    monkeypatch.setattr(_sinks.shutil, "which", lambda _: "/usr/local/bin/gh")
    return calls


class TestToGhFallback:
    def test_succeeds_first_try_with_labels(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = _patch_subprocess(
            monkeypatch,
            side_effect_seq=[_completed(stdout="https://example/issues/1")],
        )
        url = _sinks._to_gh(
            "body",
            title="t",
            labels=["bug", "triage"],
        )
        assert url == "https://example/issues/1"
        assert calls[0][:5] == ["gh", "issue", "create", "--title", "t"]
        # All requested labels passed through.
        assert calls[0].count("--label") == 2

    def test_retries_without_label_on_unknown_label(self, monkeypatch: pytest.MonkeyPatch) -> None:
        first = _completed(
            returncode=1,
            stderr="GraphQL: Could not add label: 'feedback' not found",
        )
        calls = _patch_subprocess(
            monkeypatch,
            side_effect_seq=[
                first,
                _completed(stdout="https://example/issues/2"),
            ],
        )
        url = _sinks._to_gh(
            "body",
            title="t",
            labels=["feedback"],
        )
        assert url == "https://example/issues/2"
        assert len(calls) == 2
        assert "--label" in calls[0]
        # Retry must NOT carry --label.
        assert "--label" not in calls[1]

    def test_no_retry_when_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        first = _completed(
            returncode=1,
            stderr="Could not add label: 'feedback' not found",
        )
        _patch_subprocess(monkeypatch, side_effect_seq=[first])
        with pytest.raises(ExternalToolError):
            _sinks._to_gh(
                "body",
                title="t",
                labels=["feedback"],
                fallback_on_missing_label=False,
            )

    def test_propagates_unrelated_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        first = _completed(returncode=2, stderr="HTTP 500 — server fire")
        _patch_subprocess(monkeypatch, side_effect_seq=[first])
        with pytest.raises(ExternalToolError) as exc:
            _sinks._to_gh("body", title="t", labels=["bug"])
        assert "server fire" in str(exc.value)

    def test_back_compat_label_string_form(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Old call site using comma-string ``label="a,b"`` must still work."""
        calls = _patch_subprocess(
            monkeypatch,
            side_effect_seq=[_completed(stdout="https://example/issues/3")],
        )
        url = _sinks._to_gh("body", title="t", label="bug,enhancement")
        assert url == "https://example/issues/3"
        assert calls[0].count("--label") == 2


class TestToGhRepoInjection:
    def test_repo_flag_injected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = _patch_subprocess(
            monkeypatch,
            side_effect_seq=[_completed(stdout="https://example/issues/4")],
        )
        _sinks._to_gh("body", title="t", repo="owner/name")
        idx = calls[0].index("-R")
        assert calls[0][idx + 1] == "owner/name"

    def test_repo_flag_carried_on_label_retry(self, monkeypatch: pytest.MonkeyPatch) -> None:
        first = _completed(returncode=1, stderr="Could not add label: 'feedback' not found")
        calls = _patch_subprocess(
            monkeypatch,
            side_effect_seq=[first, _completed(stdout="https://example/issues/5")],
        )
        _sinks._to_gh("body", title="t", labels=["feedback"], repo="owner/name")
        assert "-R" in calls[1]

    def test_emit_resolves_repo_from_upgrade_source(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        """`--gh` must target framework.json#upgrade.source.repo — projects
        without a git remote (or with a downstream remote) otherwise fail."""
        calls = _patch_subprocess(
            monkeypatch,
            side_effect_seq=[_completed(stdout="https://example/issues/6")],
        )

        class FakeCfg:
            upgrade_source = {"repo": "lync-cyber/CataForge"}

            def feedback_gh_labels(self, kind):  # noqa: ANN001
                return []

            def feedback_fallback_on_missing_label(self):
                return True

        monkeypatch.setattr(_sinks, "get_config_manager", lambda: FakeCfg())
        _sinks._emit(
            "body",
            project_root=tmp_path,
            print_to_stdout=False,
            out_path=None,
            to_clipboard=False,
            to_gh=True,
            title="t",
            quiet=True,
            gh_kind="bug",
        )
        idx = calls[0].index("-R")
        assert calls[0][idx + 1] == "lync-cyber/CataForge"
