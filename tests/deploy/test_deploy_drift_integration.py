"""A real deploy records a drift baseline and never self-triggers drift."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from cataforge.adapter.platform.registry import clear_cache
from cataforge.core.config import ConfigManager
from cataforge.core.paths import ProjectPaths
from cataforge.runtime.deploy.deployer import Deployer
from cataforge.runtime.deploy.drift import detect_drift
from cataforge.runtime.deploy.manifest import load_prior_baseline_for

_CLAUDE_PROFILE = {
    "platform_id": "claude-code",
    "display_name": "Claude Code",
    "tool_map": {"file_read": "Read"},
    "agent_definition": {
        "format": "yaml-frontmatter",
        "scan_dirs": [".claude/agents"],
        "needs_deploy": False,
    },
    "instruction_file": {
        "reads_claude_md": False,
        "targets": [{"type": "project_state_copy", "path": "CLAUDE.md"}],
    },
    "dispatch": {"tool_name": "Agent", "is_async": False},
    "hooks": {"config_format": None, "config_path": None, "event_map": {}, "degradation": {}},
}


def _init_project(tmp_path: Path) -> Path:
    cf = tmp_path / ".cataforge"
    cf.mkdir()
    (cf / "framework.json").write_text(
        json.dumps({"version": "0.1.0", "runtime": {"platform": "claude-code"}}), encoding="utf-8"
    )
    (cf / "PROJECT-STATE.md").write_text("运行时: {platform}\n", encoding="utf-8")
    (cf / "rules").mkdir()
    (cf / "rules" / "COMMON-RULES.md").write_text("# common\n", encoding="utf-8")
    (cf / "agents" / "orchestrator").mkdir(parents=True)
    (cf / "agents" / "orchestrator" / "AGENT.md").write_text(
        "---\nname: orchestrator\ntools: file_read\n---\ntext\n", encoding="utf-8"
    )
    (cf / "hooks").mkdir()
    (cf / "hooks" / "hooks.yaml").write_text(
        "hooks: {}\ndegradation_templates: {}\n", encoding="utf-8"
    )
    p = cf / "platforms" / "claude-code"
    p.mkdir(parents=True)
    (p / "profile.yaml").write_text(yaml.safe_dump(_CLAUDE_PROFILE), encoding="utf-8")
    return tmp_path


def _deploy(root: Path) -> None:
    clear_cache()
    Deployer(ConfigManager(root)).deploy("claude-code")


def test_deploy_records_drift_baseline(tmp_path: Path) -> None:
    root = _init_project(tmp_path)
    _deploy(root)
    digest, version = load_prior_baseline_for(root, "claude-code")
    assert digest is not None
    assert version  # the running package version is recorded


def test_deploy_does_not_self_trigger_drift(tmp_path: Path) -> None:
    root = _init_project(tmp_path)
    _deploy(root)
    report = detect_drift(ProjectPaths(root))
    assert report.deployed is True
    assert report.source_drift is False, "deploy must not self-trigger source drift"
    assert report.version_drift is False


def test_redeploy_after_source_edit_clears_drift(tmp_path: Path) -> None:
    root = _init_project(tmp_path)
    _deploy(root)
    (root / ".cataforge" / "rules" / "COMMON-RULES.md").write_text("# changed\n", encoding="utf-8")
    assert detect_drift(ProjectPaths(root)).source_drift is True
    _deploy(root)
    assert detect_drift(ProjectPaths(root)).source_drift is False
