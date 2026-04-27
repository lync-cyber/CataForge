"""v2 schema opt-in filters: matcher_file_pattern / _command_pattern / _agent_id.

These filters narrow a hook beyond what IDE-native matchers can express
(they can only pick "Bash" or "Edit" at the tool level).  The evaluator
lives in ``cataforge.hook.base.matches_script_filters``; scripts call it
after their capability gate.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from cataforge.hook.base import matches_script_filters


@pytest.fixture()
def spec_with_filters(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> dict:
    """Stub load_hooks_spec so matches_script_filters sees custom filters."""
    spec = {
        "schema_version": 2,
        "hooks": {
            "PostToolUse": [
                {
                    "script": "lint_format",
                    "type": "observe",
                    "matcher_capability": "file_edit",
                    "matcher_file_pattern": ["*.py", "*.ts"],
                },
                {
                    "script": "validate_agent_result",
                    "type": "observe",
                    "matcher_capability": "agent_dispatch",
                    "matcher_agent_id": ["reviewer", "architect"],
                },
            ],
            "PreToolUse": [
                {
                    "script": "guard_dangerous",
                    "type": "block",
                    "matcher_capability": "shell_exec",
                    "matcher_command_pattern": [r"npm\s+publish"],
                }
            ],
        },
    }
    import cataforge.hook.bridge as bridge

    monkeypatch.setattr(bridge, "load_hooks_spec", lambda _p=None: spec)
    return spec


class TestFilePatternFilter:
    def test_path_matches_pattern(self, spec_with_filters: dict) -> None:
        data = {"tool_input": {"file_path": "src/app/main.py"}}
        assert matches_script_filters(data, "lint_format") is True

    def test_path_does_not_match(self, spec_with_filters: dict) -> None:
        data = {"tool_input": {"file_path": "README.md"}}
        assert matches_script_filters(data, "lint_format") is False

    def test_missing_path_rejects(self, spec_with_filters: dict) -> None:
        assert matches_script_filters({"tool_input": {}}, "lint_format") is False


class TestCommandPatternFilter:
    def test_matches_dangerous_command(self, spec_with_filters: dict) -> None:
        data = {"tool_input": {"command": "npm publish --force"}}
        assert matches_script_filters(data, "guard_dangerous") is True

    def test_does_not_match_unrelated_command(
        self, spec_with_filters: dict
    ) -> None:
        data = {"tool_input": {"command": "ls -la"}}
        assert matches_script_filters(data, "guard_dangerous") is False


class TestAgentIdFilter:
    def test_match_agent_id(self, spec_with_filters: dict) -> None:
        data = {"tool_input": {"subagent_type": "reviewer"}}
        assert matches_script_filters(data, "validate_agent_result") is True

    def test_excluded_agent_id(self, spec_with_filters: dict) -> None:
        data = {"tool_input": {"subagent_type": "random-agent"}}
        assert matches_script_filters(data, "validate_agent_result") is False


class TestNoFiltersDeclared:
    def test_script_not_in_spec_allows(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import cataforge.hook.bridge as bridge

        monkeypatch.setattr(
            bridge, "load_hooks_spec", lambda _p=None: {"hooks": {}}
        )
        assert matches_script_filters({}, "no_such_script") is True

    def test_script_with_no_filters_allows(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import cataforge.hook.bridge as bridge

        spec = {
            "hooks": {
                "PostToolUse": [
                    {"script": "detect_correction", "type": "observe"}
                ]
            }
        }
        monkeypatch.setattr(bridge, "load_hooks_spec", lambda _p=None: spec)

        assert matches_script_filters({}, "detect_correction") is True


def test_builtin_hooks_yaml_loads_and_is_schema_v2() -> None:
    """The canonical hooks.yaml must parse cleanly + declare v2."""
    path = (
        Path(__file__).resolve().parents[2]
        / ".cataforge"
        / "hooks"
        / "hooks.yaml"
    )
    with open(path, encoding="utf-8") as f:
        spec = yaml.safe_load(f)

    assert spec.get("schema_version") == 2
    assert "hooks" in spec
    assert "PreToolUse" in spec["hooks"]
