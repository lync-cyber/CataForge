"""Tests for agent frontmatter translator."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from cataforge.agent.translator import translate_agent_md
from cataforge.platform.registry import get_adapter


@pytest.fixture()
def project_dir(tmp_path: Path) -> Path:
    cataforge_dir = tmp_path / ".cataforge"
    cataforge_dir.mkdir()
    (cataforge_dir / "framework.json").write_text(
        json.dumps({"version": "0.1.0", "runtime": {"platform": "claude-code"}}),
        encoding="utf-8",
    )

    for pid, profile in {
        "claude-code": {
            "platform_id": "claude-code",
            "tool_map": {
                "file_read": "Read",
                "file_edit": "Edit",
                "shell_exec": "Bash",
                "agent_dispatch": "Agent",
            },
        },
        "cursor": {
            "platform_id": "cursor",
            "tool_map": {
                "file_read": "Read",
                "file_edit": "Write",
                "shell_exec": "Shell",
                "agent_dispatch": "Task",
            },
        },
    }.items():
        p = cataforge_dir / "platforms" / pid
        p.mkdir(parents=True)
        with open(p / "profile.yaml", "w", encoding="utf-8") as f:
            yaml.dump(profile, f)

    return tmp_path


SAMPLE_AGENT_MD = """---
name: test-agent
tools: file_read, file_edit, shell_exec, agent_dispatch
disallowedTools: web_search
model: default
---

# Test Agent

Does testing things.
"""


class TestTranslation:
    def test_translate_claude_code(self, project_dir: Path) -> None:
        platforms_dir = project_dir / ".cataforge" / "platforms"
        adapter = get_adapter("claude-code", platforms_dir)
        result = translate_agent_md(SAMPLE_AGENT_MD, adapter)
        assert "tools: Read, Edit, Bash, Agent" in result
        assert "file_read" not in result.split("tools:")[1].split("\n")[0]

    def test_translate_cursor(self, project_dir: Path) -> None:
        platforms_dir = project_dir / ".cataforge" / "platforms"
        adapter = get_adapter("cursor", platforms_dir)
        result = translate_agent_md(SAMPLE_AGENT_MD, adapter)
        assert "tools: Read, Write, Shell, Task" in result

    def test_body_unchanged(self, project_dir: Path) -> None:
        platforms_dir = project_dir / ".cataforge" / "platforms"
        adapter = get_adapter("claude-code", platforms_dir)
        result = translate_agent_md(SAMPLE_AGENT_MD, adapter)
        assert "# Test Agent" in result
        assert "Does testing things." in result


class TestBracketStripRobustness:
    """Quirky YAML flow-style list values must not spawn '[]' warnings."""

    @pytest.mark.parametrize(
        "frontmatter_line",
        [
            "tools: []",
            "tools: [ ]",
            "tools: '[]'",
            'tools: "[]"',
            "tools: []  # explicitly none",
            "tools: [ ]   # still none",
        ],
    )
    def test_empty_flow_lists_produce_no_warning(
        self,
        project_dir: Path,
        frontmatter_line: str,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        platforms_dir = project_dir / ".cataforge" / "platforms"
        adapter = get_adapter("claude-code", platforms_dir)
        md = f"---\nname: test\n{frontmatter_line}\n---\nbody\n"

        caplog.clear()
        with caplog.at_level("WARNING"):
            translate_agent_md(md, adapter)

        for record in caplog.records:
            assert "[]" not in record.getMessage(), record.getMessage()
            assert "no platform mapping" not in record.getMessage(), record.getMessage()

    def test_dropped_collector_aggregates(self, project_dir: Path) -> None:
        platforms_dir = project_dir / ".cataforge" / "platforms"
        adapter = get_adapter("claude-code", platforms_dir)

        md = (
            "---\n"
            "name: test\n"
            "tools: file_read, web_fetch, user_question\n"
            "disallowedTools: user_question\n"
            "---\nbody\n"
        )
        collector: dict[str, set[str]] = {}
        translate_agent_md(md, adapter, dropped_collector=collector)

        assert "tools" in collector
        assert "web_fetch" in collector["tools"]
        assert "user_question" in collector["tools"]
        assert "disallowedTools" in collector
        assert collector["disallowedTools"] == {"user_question"}

    def test_collector_suppresses_per_call_warning(
        self, project_dir: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """When a collector is provided, the function must not log warnings."""
        platforms_dir = project_dir / ".cataforge" / "platforms"
        adapter = get_adapter("claude-code", platforms_dir)
        md = "---\nname: test\ntools: unknown_cap\n---\nbody\n"

        caplog.clear()
        collector: dict[str, set[str]] = {}
        with caplog.at_level("WARNING"):
            translate_agent_md(md, adapter, dropped_collector=collector)

        # Collector should have captured the miss, but logger should be silent.
        assert collector == {"tools": {"unknown_cap"}}
        warning_records = [
            r for r in caplog.records if "no platform mapping" in r.getMessage()
        ]
        assert warning_records == []

    def test_fallback_logger_dedups_within_call(
        self, project_dir: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Legacy path (no collector): identical caps in tools+disallowed log once per field."""
        platforms_dir = project_dir / ".cataforge" / "platforms"
        adapter = get_adapter("claude-code", platforms_dir)
        md = (
            "---\nname: test\n"
            "tools: unknown, unknown, unknown\n"
            "disallowedTools: unknown\n"
            "---\nbody\n"
        )

        caplog.clear()
        with caplog.at_level("WARNING"):
            translate_agent_md(md, adapter)

        # One WARN per field — two total, not four.
        warning_records = [
            r for r in caplog.records if "no platform mapping" in r.getMessage()
        ]
        assert len(warning_records) == 2, [r.getMessage() for r in warning_records]
