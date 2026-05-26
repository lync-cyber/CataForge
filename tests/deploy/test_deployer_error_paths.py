"""Error-path tests for the Deployer."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from cataforge.core.config import ConfigManager
from cataforge.deploy.deployer import Deployer
from cataforge.platform.registry import clear_cache

# ---------------------------------------------------------------------------
# Shared helpers (mirrors test_deployer.py style)
# ---------------------------------------------------------------------------


def _write_profile(base: Path, platform_id: str, profile: dict) -> None:
    p = base / ".cataforge" / "platforms" / platform_id
    p.mkdir(parents=True, exist_ok=True)
    (p / "profile.yaml").write_text(yaml.safe_dump(profile), encoding="utf-8")


def _init_project(tmp_path: Path) -> Path:
    root = tmp_path
    cf = root / ".cataforge"
    cf.mkdir(exist_ok=True)
    (cf / "framework.json").write_text(
        json.dumps({"version": "0.1.0", "runtime": {"platform": "cursor"}}),
        encoding="utf-8",
    )
    (cf / "PROJECT-STATE.md").write_text("运行时: {platform}\n", encoding="utf-8")
    (cf / "rules").mkdir(exist_ok=True)
    (cf / "rules" / "COMMON-RULES.md").write_text("# common\n", encoding="utf-8")
    (cf / "agents").mkdir(exist_ok=True)
    (cf / "agents" / "orchestrator").mkdir(exist_ok=True)
    (cf / "agents" / "orchestrator" / "AGENT.md").write_text(
        "---\nname: orchestrator\ntools: file_read\n---\ntext\n",
        encoding="utf-8",
    )
    (cf / "hooks").mkdir(exist_ok=True)
    (cf / "hooks" / "hooks.yaml").write_text(
        "hooks: {}\ndegradation_templates: {}\n", encoding="utf-8"
    )
    (cf / "mcp").mkdir(exist_ok=True)
    return root


def _minimal_profile(platform_id: str, path: str = "CLAUDE.md") -> dict:
    return {
        "platform_id": platform_id,
        "display_name": platform_id.capitalize(),
        "tool_map": {"file_read": "Read"},
        "agent_definition": {
            "format": "yaml-frontmatter",
            "scan_dirs": [".claude/agents"],
            "needs_deploy": False,
        },
        "instruction_file": {
            "reads_claude_md": False,
            "targets": [{"type": "project_state_copy", "path": path}],
        },
        "dispatch": {"tool_name": "Agent", "is_async": False},
        "hooks": {
            "config_format": None,
            "config_path": None,
            "event_map": {},
            "degradation": {},
        },
    }


# ---------------------------------------------------------------------------
# (a) Unsupported instruction_file type → action contains "SKIP"
# ---------------------------------------------------------------------------


def test_unknown_instruction_type_emits_skip_action(tmp_path: Path) -> None:
    root = _init_project(tmp_path)
    profile = _minimal_profile("claude-code")
    profile["instruction_file"]["targets"] = [
        {"type": "magic_unknown_type", "path": "CLAUDE.md"}
    ]
    _write_profile(root, "claude-code", profile)

    clear_cache()
    deployer = Deployer(ConfigManager(root))
    actions = deployer.deploy("claude-code")

    skip_actions = [a for a in actions if "SKIP" in a and "magic_unknown_type" in a]
    assert skip_actions, (
        f"expected a SKIP action mentioning 'magic_unknown_type', got: {actions}"
    )


# ---------------------------------------------------------------------------
# (b) Invalid on_conflict value → action contains "SKIP" with field name
# ---------------------------------------------------------------------------


def test_invalid_on_conflict_emits_skip_with_field_name(tmp_path: Path) -> None:
    root = _init_project(tmp_path)
    profile = _minimal_profile("claude-code")
    profile["instruction_file"]["targets"] = [
        {
            "type": "project_state_copy",
            "path": "CLAUDE.md",
            "on_conflict": "not_a_valid_value",
        }
    ]
    _write_profile(root, "claude-code", profile)

    clear_cache()
    deployer = Deployer(ConfigManager(root))
    actions = deployer.deploy("claude-code")

    skip_actions = [a for a in actions if "SKIP" in a and "on_conflict" in a]
    assert skip_actions, (
        f"expected a SKIP action mentioning 'on_conflict', got: {actions}"
    )


# ---------------------------------------------------------------------------
# (c) MCP yaml format error → spec is silently skipped (registry logs warning,
#     deploy still completes without raising, problematic spec absent from output)
# ---------------------------------------------------------------------------


def test_malformed_mcp_yaml_does_not_raise(tmp_path: Path) -> None:
    root = _init_project(tmp_path)
    profile = _minimal_profile("claude-code")
    _write_profile(root, "claude-code", profile)

    mcp_dir = root / ".cataforge" / "mcp"
    mcp_dir.mkdir(exist_ok=True)
    (mcp_dir / "bad.yaml").write_text(": invalid: yaml: : \n", encoding="utf-8")

    clear_cache()
    deployer = Deployer(ConfigManager(root))
    # Must not raise even when MCP spec is malformed
    actions = deployer.deploy("claude-code")
    assert isinstance(actions, list)


# ---------------------------------------------------------------------------
# (d) File write failure → PermissionError propagates (no silent swallow)
# ---------------------------------------------------------------------------


def test_write_failure_propagates(tmp_path: Path) -> None:
    root = _init_project(tmp_path)
    profile = _minimal_profile("claude-code")
    _write_profile(root, "claude-code", profile)

    clear_cache()
    deployer = Deployer(ConfigManager(root))

    original_write = Path.write_text

    def failing_write(self: Path, *args, **kwargs):
        if self.name == "CLAUDE.md":
            raise PermissionError(f"no write permission: {self}")
        return original_write(self, *args, **kwargs)

    with patch.object(Path, "write_text", failing_write), pytest.raises(PermissionError):
        deployer.deploy("claude-code")


# ---------------------------------------------------------------------------
# (e) Missing PROJECT-STATE.md → SKIP action, no crash
# ---------------------------------------------------------------------------


def test_missing_project_state_md_yields_skip(tmp_path: Path) -> None:
    root = _init_project(tmp_path)
    # Remove the PROJECT-STATE.md that _init_project created
    (root / ".cataforge" / "PROJECT-STATE.md").unlink()

    profile = _minimal_profile("claude-code")
    _write_profile(root, "claude-code", profile)

    clear_cache()
    deployer = Deployer(ConfigManager(root))
    actions = deployer.deploy("claude-code")

    skip_actions = [a for a in actions if "SKIP" in a and "PROJECT-STATE" in a]
    assert skip_actions, (
        f"expected a SKIP action for missing PROJECT-STATE.md, got: {actions}"
    )
