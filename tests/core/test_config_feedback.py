"""Tests for the new feedback / claude_md_limits ConfigManager accessors."""

from __future__ import annotations

import json
from pathlib import Path

from cataforge.core.config import ConfigManager


def _bootstrap(tmp_path: Path, **framework_overrides) -> Path:
    (tmp_path / ".cataforge").mkdir()
    payload = {
        "version": "0.0.0-test",
        "runtime": {"platform": "claude-code"},
        **framework_overrides,
    }
    (tmp_path / ".cataforge" / "framework.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )
    return tmp_path


class TestFeedbackGhLabels:
    def test_default_label_when_missing_returns_empty(self, tmp_path: Path) -> None:
        project = _bootstrap(tmp_path)
        cfg = ConfigManager(project_root=project)
        assert cfg.feedback_gh_labels("bug") == []
        assert cfg.feedback_fallback_on_missing_label() is True

    def test_string_label_normalises_to_list(self, tmp_path: Path) -> None:
        project = _bootstrap(
            tmp_path,
            feedback={"gh": {"labels": {"bug": "bug"}}},
        )
        cfg = ConfigManager(project_root=project)
        assert cfg.feedback_gh_labels("bug") == ["bug"]

    def test_list_labels_returned_in_order(self, tmp_path: Path) -> None:
        project = _bootstrap(
            tmp_path,
            feedback={
                "gh": {
                    "labels": {
                        "bug": ["bug", "triage"],
                        "suggest": ["enhancement"],
                    }
                }
            },
        )
        cfg = ConfigManager(project_root=project)
        assert cfg.feedback_gh_labels("bug") == ["bug", "triage"]
        assert cfg.feedback_gh_labels("suggest") == ["enhancement"]
        assert cfg.feedback_gh_labels("correction-export") == []

    def test_fallback_flag_respected(self, tmp_path: Path) -> None:
        project = _bootstrap(
            tmp_path,
            feedback={"gh": {"fallback_on_missing_label": False}},
        )
        cfg = ConfigManager(project_root=project)
        assert cfg.feedback_fallback_on_missing_label() is False


class TestClaudeMdLimits:
    def test_defaults_when_missing(self, tmp_path: Path) -> None:
        project = _bootstrap(tmp_path)
        limits = ConfigManager(project_root=project).claude_md_limits
        assert limits["max_bytes"] >= 30000
        assert limits["learnings_registry_max_entries"] >= 1

    def test_overrides_merged(self, tmp_path: Path) -> None:
        project = _bootstrap(
            tmp_path,
            claude_md_limits={"max_bytes": 5000},
        )
        limits = ConfigManager(project_root=project).claude_md_limits
        assert limits["max_bytes"] == 5000
        # missing keys still fall back to defaults
        assert "learnings_registry_max_entries" in limits
