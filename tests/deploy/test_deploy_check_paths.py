"""Dry-run output format regression tests.

These lock in the shape of ``deploy --check`` action strings so accidental
refactors can't collapse them back into the ambiguous
``... → .cursor/agents/AGENT.md`` pattern that testers repeatedly misread
as "all agents overwrite the same file".
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from cataforge.core.config import ConfigManager
from cataforge.deploy.deployer import Deployer
from cataforge.platform.registry import clear_cache


def _write_profile(base: Path, platform_id: str, profile: dict) -> None:
    p = base / ".cataforge" / "platforms" / platform_id
    p.mkdir(parents=True, exist_ok=True)
    (p / "profile.yaml").write_text(yaml.safe_dump(profile), encoding="utf-8")


def _init_project(tmp_path: Path, *, agents: list[str]) -> Path:
    root = tmp_path
    cf = root / ".cataforge"
    cf.mkdir()
    (cf / "framework.json").write_text(
        json.dumps({"version": "0.1.0", "runtime": {"platform": "cursor"}}),
        encoding="utf-8",
    )
    (cf / "PROJECT-STATE.md").write_text("运行时: {platform}\n", encoding="utf-8")
    (cf / "rules").mkdir()
    (cf / "rules" / "COMMON-RULES.md").write_text("# common\n", encoding="utf-8")
    (cf / "hooks").mkdir()
    (cf / "hooks" / "hooks.yaml").write_text(
        "hooks: {}\ndegradation_templates: {}\n", encoding="utf-8"
    )
    (cf / "mcp").mkdir()

    (cf / "agents").mkdir()
    for name in agents:
        (cf / "agents" / name).mkdir()
        (cf / "agents" / name / "AGENT.md").write_text(
            f"---\nname: {name}\ntools: file_read\n---\nbody\n", encoding="utf-8"
        )
    return root


class TestCursorDryRunPaths:
    def test_cursor_dry_run_shows_distinct_agent_targets(self, tmp_path: Path) -> None:
        root = _init_project(tmp_path, agents=["orchestrator", "implementer"])
        _write_profile(
            root,
            "cursor",
            {
                "platform_id": "cursor",
                "display_name": "Cursor",
                "tool_map": {"file_read": "Read"},
                "agent_definition": {
                    "format": "yaml-frontmatter",
                    "scan_dirs": [".cursor/agents"],
                    "needs_deploy": True,
                },
                "instruction_file": {
                    "reads_claude_md": False,
                    "targets": [{"type": "project_state_copy", "path": "AGENTS.md"}],
                },
                "dispatch": {"tool_name": "Task", "is_async": False},
                "hooks": {
                    "config_format": None, "config_path": None,
                    "event_map": {}, "degradation": {},
                },
            },
        )
        clear_cache()
        cfg = ConfigManager(root)
        actions = Deployer(cfg).deploy("cursor", dry_run=True)

        # Each agent has its own physical path — not "all → .cursor/agents/AGENT.md".
        assert any(
            ".cursor/agents/orchestrator/AGENT.md" in a for a in actions
        ), actions
        assert any(
            ".cursor/agents/implementer/AGENT.md" in a for a in actions
        ), actions
        # The old ambiguous format must not regress.
        for action in actions:
            assert not action.endswith(" → .cursor/agents/AGENT.md"), action


class TestClaudeCodeDryRunPaths:
    def test_claude_dry_run_shows_flat_layout(self, tmp_path: Path) -> None:
        root = _init_project(tmp_path, agents=["orchestrator"])
        _write_profile(
            root,
            "claude-code",
            {
                "platform_id": "claude-code",
                "display_name": "Claude Code",
                "tool_map": {"file_read": "Read"},
                "agent_definition": {
                    "format": "yaml-frontmatter",
                    "scan_dirs": [".claude/agents"],
                    "needs_deploy": True,
                },
                "instruction_file": {
                    "reads_claude_md": False,
                    "targets": [{"type": "project_state_copy", "path": "CLAUDE.md"}],
                },
                "dispatch": {"tool_name": "Agent", "is_async": False},
                "hooks": {
                    "config_format": None, "config_path": None,
                    "event_map": {}, "degradation": {},
                },
            },
        )
        clear_cache()
        cfg = ConfigManager(root)
        actions = Deployer(cfg).deploy("claude-code", dry_run=True)

        # Claude Code emits only the flat ``<name>.md`` file — the legacy
        # ``<name>/AGENT.md`` subdir mirror was removed.
        matches = [a for a in actions if "orchestrator" in a and "would deploy agent" in a]
        assert matches, actions
        joined = " ".join(matches)
        assert ".claude/agents/orchestrator.md" in joined
        assert ".claude/agents/orchestrator/AGENT.md" not in joined
