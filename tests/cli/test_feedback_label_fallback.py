"""Tests for the new ``_to_gh`` label-fallback path in ``cataforge feedback``."""

from __future__ import annotations

import subprocess
from typing import Any

import pytest

from cataforge.cli import feedback_cmd
from cataforge.cli.errors import ExternalToolError


class _FakeCompleted:
    def __init__(self, stdout: str = "", stderr: str = "") -> None:
        self.stdout = stdout
        self.stderr = stderr


def _patch_subprocess(
    monkeypatch: pytest.MonkeyPatch,
    *,
    side_effect_seq: list[Any],
) -> list[list[str]]:
    """Replace ``subprocess.run`` inside feedback_cmd with a queue-driven fake.

    Returns the list that will collect every issued command for assertion.
    """
    calls: list[list[str]] = []
    queue = list(side_effect_seq)

    def fake_run(cmd, **kwargs):  # noqa: ANN001 — passthrough proxy
        calls.append(list(cmd))
        if not queue:
            raise AssertionError(f"unexpected extra subprocess.run({cmd})")
        outcome = queue.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(feedback_cmd, "subprocess", subprocess)  # ensure real symbol
    monkeypatch.setattr(feedback_cmd.subprocess, "run", fake_run)
    monkeypatch.setattr(feedback_cmd.shutil, "which", lambda _: "/usr/local/bin/gh")
    return calls


class TestToGhFallback:
    def test_succeeds_first_try_with_labels(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = _patch_subprocess(
            monkeypatch,
            side_effect_seq=[_FakeCompleted(stdout="https://example/issues/1")],
        )
        url = feedback_cmd._to_gh(
            "body",
            title="t",
            labels=["bug", "triage"],
        )
        assert url == "https://example/issues/1"
        assert calls[0][:5] == ["gh", "issue", "create", "--title", "t"]
        # All requested labels passed through.
        assert calls[0].count("--label") == 2

    def test_retries_without_label_on_unknown_label(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        first = subprocess.CalledProcessError(
            returncode=1,
            cmd=["gh", "issue", "create"],
            output="",
            stderr="GraphQL: Could not add label: 'feedback' not found",
        )
        calls = _patch_subprocess(
            monkeypatch,
            side_effect_seq=[
                first,
                _FakeCompleted(stdout="https://example/issues/2"),
            ],
        )
        url = feedback_cmd._to_gh(
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
        first = subprocess.CalledProcessError(
            returncode=1,
            cmd=["gh"],
            output="",
            stderr="Could not add label: 'feedback' not found",
        )
        _patch_subprocess(monkeypatch, side_effect_seq=[first])
        with pytest.raises(ExternalToolError):
            feedback_cmd._to_gh(
                "body",
                title="t",
                labels=["feedback"],
                fallback_on_missing_label=False,
            )

    def test_propagates_unrelated_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        first = subprocess.CalledProcessError(
            returncode=2,
            cmd=["gh"],
            output="",
            stderr="HTTP 500 — server fire",
        )
        _patch_subprocess(monkeypatch, side_effect_seq=[first])
        with pytest.raises(ExternalToolError) as exc:
            feedback_cmd._to_gh("body", title="t", labels=["bug"])
        assert "server fire" in str(exc.value)

    def test_back_compat_label_string_form(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Old call site using comma-string ``label="a,b"`` must still work."""
        calls = _patch_subprocess(
            monkeypatch,
            side_effect_seq=[_FakeCompleted(stdout="https://example/issues/3")],
        )
        url = feedback_cmd._to_gh("body", title="t", label="bug,enhancement")
        assert url == "https://example/issues/3"
        assert calls[0].count("--label") == 2
