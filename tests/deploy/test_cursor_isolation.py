"""Verify a Cursor deploy does NOT spill into .claude/ by default.

Tester feedback from Cursor verification reported confusion about a
``.claude/rules ← .cataforge/rules`` action appearing during ``cataforge
deploy --platform cursor``.  The cross-platform Markdown mirror is useful
for shared Claude Code + Cursor repos but is noise for pure-Cursor users.

Post-M5 behaviour:
- default profile has ``rules.cross_platform_mirror: false``
- pure Cursor deploy produces zero files under ``.claude/``
- opting in with ``cross_platform_mirror: true`` restores the mirror
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from cataforge.core.config import ConfigManager
from cataforge.deploy.deployer import Deployer
from cataforge.platform.registry import clear_cache


_CURSOR_PROFILE_BASE: dict = {
    "platform_id": "cursor",
    "display_name": "Cursor",
    "tool_map": {"file_read": "Read", "file_edit": "Write", "shell_exec": "Shell"},
    "extended_capabilities": {},
    "agent_definition": {
        "format": "yaml-frontmatter",
        "scan_dirs": [".cursor/agents"],
        "needs_deploy": True,
    },
    "instruction_file": {
        "reads_claude_md": False,
        "targets": [{"type": "project_state_copy", "path": "AGENTS.md"}],
        "additional_outputs": [
            {"target": ".cursor/rules/", "format": "mdc", "source": "rules"}
        ],
    },
    "dispatch": {"tool_name": "Task", "is_async": False},
    "hooks": {
        "config_format": None,
        "config_path": None,
        "event_map": {},
        "degradation": {},
    },
}


def _write_profile(base: Path, profile: dict) -> None:
    p = base / ".cataforge" / "platforms" / "cursor"
    p.mkdir(parents=True, exist_ok=True)
    (p / "profile.yaml").write_text(yaml.safe_dump(profile), encoding="utf-8")


def _init_project(tmp_path: Path) -> Path:
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
    (cf / "agents").mkdir()
    (cf / "agents" / "orchestrator").mkdir()
    (cf / "agents" / "orchestrator" / "AGENT.md").write_text(
        "---\nname: orchestrator\ntools: file_read\n---\nbody\n",
        encoding="utf-8",
    )
    (cf / "hooks").mkdir()
    (cf / "hooks" / "hooks.yaml").write_text(
        "hooks: {}\ndegradation_templates: {}\n", encoding="utf-8"
    )
    (cf / "mcp").mkdir()
    return root


def _all_files_under(root: Path) -> list[str]:
    return [
        str(p.relative_to(root)).replace("\\", "/")
        for p in root.rglob("*")
        if p.is_file() or p.is_symlink()
    ]


class TestCursorIsolation:
    def test_default_profile_does_not_touch_claude_dir(self, tmp_path: Path) -> None:
        """A pure Cursor deploy (default profile) must not create ``.claude/*``."""
        root = _init_project(tmp_path)
        _write_profile(root, _CURSOR_PROFILE_BASE)
        clear_cache()

        Deployer(ConfigManager(root)).deploy("cursor")

        files = _all_files_under(root)
        claude_files = [f for f in files if f.startswith(".claude/")]
        assert claude_files == [], f"unexpected .claude/ artifacts: {claude_files}"

    def test_mirror_opt_in_links_claude_rules(self, tmp_path: Path) -> None:
        """With ``rules.cross_platform_mirror: true``, mirror reappears."""
        root = _init_project(tmp_path)
        profile = dict(_CURSOR_PROFILE_BASE)
        profile["rules"] = {"cross_platform_mirror": True}
        _write_profile(root, profile)
        clear_cache()

        Deployer(ConfigManager(root)).deploy("cursor")

        target = root / ".claude" / "rules"
        # symlink, junction, or directory copy — all are valid success shapes.
        assert target.exists() or target.is_symlink(), (
            f"expected .claude/rules mirror, found none. Files: {_all_files_under(root)}"
        )

    def test_dry_run_reports_skip_by_default(self, tmp_path: Path) -> None:
        """Dry-run must explain why ``.claude/rules`` is not being created."""
        root = _init_project(tmp_path)
        _write_profile(root, _CURSOR_PROFILE_BASE)
        clear_cache()

        actions = Deployer(ConfigManager(root)).deploy("cursor", dry_run=True)

        joined = "\n".join(actions)
        assert "SKIP" in joined and ".claude/rules" in joined, actions
        assert "cross_platform_mirror" in joined, actions

    def test_dry_run_notes_mirror_when_enabled(self, tmp_path: Path) -> None:
        root = _init_project(tmp_path)
        profile = dict(_CURSOR_PROFILE_BASE)
        profile["rules"] = {"cross_platform_mirror": True}
        _write_profile(root, profile)
        clear_cache()

        actions = Deployer(ConfigManager(root)).deploy("cursor", dry_run=True)

        joined = "\n".join(actions)
        assert "cross_platform_mirror=true" in joined, actions
        assert ".claude/rules" in joined, actions
