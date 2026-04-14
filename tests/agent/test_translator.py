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
