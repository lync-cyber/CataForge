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


@pytest.fixture()
def tier_project_dir(tmp_path: Path) -> Path:
    """Project fixture with model_routing tier_map across 4 platforms."""
    cataforge_dir = tmp_path / ".cataforge"
    cataforge_dir.mkdir()
    (cataforge_dir / "framework.json").write_text(
        json.dumps({"version": "0.1.0", "runtime": {"platform": "claude-code"}}),
        encoding="utf-8",
    )

    profiles = {
        "claude-code": {
            "platform_id": "claude-code",
            "tool_map": {"file_read": "Read", "agent_dispatch": "Agent"},
            "agent_config": {
                "supported_fields": [
                    "name", "description", "tools", "disallowedTools",
                    "model", "skills", "maxTurns",
                ],
            },
            "model_routing": {
                "per_agent_model": True,
                "user_resolved": False,
                "tier_map": {"light": "haiku", "standard": "sonnet", "heavy": "opus"},
            },
        },
        # Stand-in for any per_agent_model=false platform (e.g. codex).
        "codex": {
            "platform_id": "codex",
            "tool_map": {"file_read": "shell"},
            "agent_config": {
                "supported_fields": ["name", "description", "model"],
            },
            "model_routing": {
                "per_agent_model": False,
                "user_resolved": False,
                "tier_map": {"light": "fast", "standard": "default", "heavy": "max"},
            },
        },
        # Stand-in for any user_resolved platform (e.g. opencode).
        "opencode": {
            "platform_id": "opencode",
            "tool_map": {"file_read": "read"},
            "agent_config": {
                "supported_fields": ["name", "description", "tools", "model"],
            },
            "model_routing": {
                "per_agent_model": True,
                "user_resolved": True,
                "tier_map": {},
            },
        },
    }
    for pid, profile in profiles.items():
        p = cataforge_dir / "platforms" / pid
        p.mkdir(parents=True)
        with open(p / "profile.yaml", "w", encoding="utf-8") as f:
            yaml.dump(profile, f)
    return tmp_path


class TestModelTierTranslation:
    def test_tier_resolves_to_native_id(self, tier_project_dir: Path) -> None:
        adapter = get_adapter(
            "claude-code", tier_project_dir / ".cataforge" / "platforms"
        )
        md = (
            "---\nname: test\ntools: file_read\nmodel_tier: heavy\n"
            "---\nbody\n"
        )
        out = translate_agent_md(md, adapter)
        assert "model: opus" in out
        assert "model_tier" not in out

    def test_per_agent_false_drops_model(self, tier_project_dir: Path) -> None:
        """Codex-like (per_agent_model=false) → no model line written."""
        adapter = get_adapter(
            "codex", tier_project_dir / ".cataforge" / "platforms"
        )
        md = (
            "---\nname: test\ntools: file_read\nmodel_tier: standard\n"
            "---\nbody\n"
        )
        out = translate_agent_md(md, adapter)
        assert "model:" not in out
        assert "model_tier" not in out

    def test_user_resolved_drops_model(self, tier_project_dir: Path) -> None:
        """Opencode-like (user_resolved=true) → no model line written."""
        adapter = get_adapter(
            "opencode", tier_project_dir / ".cataforge" / "platforms"
        )
        md = (
            "---\nname: test\ntools: file_read\nmodel_tier: heavy\n"
            "---\nbody\n"
        )
        out = translate_agent_md(md, adapter)
        assert "model:" not in out

    def test_tier_inherit_drops_model(self, tier_project_dir: Path) -> None:
        adapter = get_adapter(
            "claude-code", tier_project_dir / ".cataforge" / "platforms"
        )
        md = (
            "---\nname: test\ntools: file_read\nmodel_tier: inherit\n"
            "---\nbody\n"
        )
        out = translate_agent_md(md, adapter)
        assert "model:" not in out

    def test_legacy_model_field_dropped(self, tier_project_dir: Path) -> None:
        """Direct migration: legacy `model: <id>` is stripped at deploy."""
        adapter = get_adapter(
            "claude-code", tier_project_dir / ".cataforge" / "platforms"
        )
        md = (
            "---\nname: test\ntools: file_read\nmodel: opus\n"
            "---\nbody\n"
        )
        out = translate_agent_md(md, adapter)
        assert "model: opus" not in out
        assert "model:" not in out


class TestSupportedFieldsFilter:
    def test_drops_unsupported_field(self, tier_project_dir: Path) -> None:
        """Codex-like supported_fields excludes `tools` → it's stripped."""
        adapter = get_adapter(
            "codex", tier_project_dir / ".cataforge" / "platforms"
        )
        md = (
            "---\nname: test\ndescription: x\ntools: file_read\n"
            "skills:\n  - foo\n  - bar\nmaxTurns: 30\n---\nbody\n"
        )
        out = translate_agent_md(md, adapter)
        assert "tools:" not in out.split("---\n")[1]  # frontmatter block
        assert "skills:" not in out.split("---\n")[1]
        assert "maxTurns" not in out.split("---\n")[1]
        assert "name: test" in out
        assert "description: x" in out

    def test_drops_internal_allowed_paths_always(
        self, tier_project_dir: Path
    ) -> None:
        adapter = get_adapter(
            "claude-code", tier_project_dir / ".cataforge" / "platforms"
        )
        md = (
            "---\nname: test\ntools: file_read\nallowed_paths:\n"
            "  - src/\n  - tests/\n---\nbody\n"
        )
        out = translate_agent_md(md, adapter)
        assert "allowed_paths" not in out
        assert "- src/" not in out
        assert "- tests/" not in out
        # Body untouched.
        assert "body" in out

    def test_keeps_supported_multiline_field(
        self, tier_project_dir: Path
    ) -> None:
        adapter = get_adapter(
            "claude-code", tier_project_dir / ".cataforge" / "platforms"
        )
        md = (
            "---\nname: test\ntools: file_read\nskills:\n"
            "  - foo\n  - bar\n---\nbody\n"
        )
        out = translate_agent_md(md, adapter)
        assert "skills:" in out
        assert "  - foo" in out
        assert "  - bar" in out
