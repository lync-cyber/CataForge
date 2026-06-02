"""Tests for target_rel path-traversal prevention in deploy_instruction_files."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from cataforge.adapter.platform.registry import clear_cache, get_adapter
from cataforge.core.errors import CataforgeError


@pytest.fixture(autouse=True)
def _clear() -> None:
    clear_cache()


def _minimal_profile(path: str) -> dict:
    return {
        "platform_id": "claude-code",
        "tool_map": {
            "file_read": "Read",
            "shell_exec": "Bash",
            "agent_dispatch": "Agent",
        },
        "agent_definition": {
            "format": "yaml-frontmatter",
            "scan_dirs": [".claude/agents"],
            "needs_deploy": True,
        },
        "instruction_file": {"targets": [{"type": "project_state_copy", "path": path}]},
        "dispatch": {"tool_name": "Agent", "is_async": False},
    }


def _setup(tmp_path: Path, target_rel: str) -> tuple[Path, Path]:
    cataforge_dir = tmp_path / ".cataforge"
    cataforge_dir.mkdir()
    (cataforge_dir / "framework.json").write_text(
        json.dumps({"version": "0.1.0", "runtime": {"platform": "claude-code"}}),
        encoding="utf-8",
    )
    project_state = cataforge_dir / "PROJECT-STATE.md"
    project_state.write_text("# state\n运行时: {platform}\n", encoding="utf-8")

    platforms_dir = cataforge_dir / "platforms" / "claude-code"
    platforms_dir.mkdir(parents=True)
    with open(platforms_dir / "profile.yaml", "w", encoding="utf-8") as f:
        yaml.dump(_minimal_profile(target_rel), f, sort_keys=False)

    return project_state, tmp_path


class TestPathTraversal:
    def test_traversal_raises(self, tmp_path: Path) -> None:
        project_state, root = _setup(tmp_path, "../../etc/foo")
        adapter = get_adapter("claude-code", root / ".cataforge" / "platforms")

        with pytest.raises(CataforgeError, match="escapes project root"):
            adapter.deploy_instruction_files(
                project_state, root, platform_id="claude-code", dry_run=False
            )

    def test_traversal_error_contains_path(self, tmp_path: Path) -> None:
        project_state, root = _setup(tmp_path, "../../etc/passwd")
        adapter = get_adapter("claude-code", root / ".cataforge" / "platforms")

        with pytest.raises(CataforgeError) as exc_info:
            adapter.deploy_instruction_files(
                project_state, root, platform_id="claude-code", dry_run=False
            )
        assert "../../etc/passwd" in str(exc_info.value)

    def test_legitimate_rel_path_writes(self, tmp_path: Path) -> None:
        project_state, root = _setup(tmp_path, "docs/foo.md")
        adapter = get_adapter("claude-code", root / ".cataforge" / "platforms")

        adapter.deploy_instruction_files(
            project_state, root, platform_id="claude-code", dry_run=False
        )

        assert (root / "docs" / "foo.md").is_file()
        assert "运行时: claude-code" in (root / "docs" / "foo.md").read_text(encoding="utf-8")

    def test_root_level_rel_path_writes(self, tmp_path: Path) -> None:
        project_state, root = _setup(tmp_path, "CLAUDE.md")
        adapter = get_adapter("claude-code", root / ".cataforge" / "platforms")

        adapter.deploy_instruction_files(
            project_state, root, platform_id="claude-code", dry_run=False
        )

        assert (root / "CLAUDE.md").is_file()
