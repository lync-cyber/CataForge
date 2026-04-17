"""Tests for ``instruction_file.targets[].on_conflict`` semantics.

Covers:
- default (no field) behaves as ``overwrite`` — back-compat
- ``overwrite`` always writes, records hash for future preserve_if_edited
- ``preserve`` skips when target exists
- ``preserve_if_edited`` skips only when user modified the file since last deploy
- invalid on_conflict value is surfaced as an action and skipped
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from cataforge.platform.registry import clear_cache, get_adapter


@pytest.fixture(autouse=True)
def _clear() -> None:
    clear_cache()


def _minimal_profile(path: str, *, on_conflict: str | None = None) -> dict:
    target: dict = {"type": "project_state_copy", "path": path}
    if on_conflict is not None:
        target["on_conflict"] = on_conflict
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
        "instruction_file": {"targets": [target]},
        "dispatch": {"tool_name": "Agent", "is_async": False},
    }


def _setup(tmp_path: Path, **profile_kwargs) -> tuple[Path, Path]:
    """Write PROJECT-STATE.md + profile.yaml, return (project_state, root)."""
    cataforge_dir = tmp_path / ".cataforge"
    cataforge_dir.mkdir()
    (cataforge_dir / "framework.json").write_text(
        json.dumps({"version": "0.1.0", "runtime": {"platform": "claude-code"}}),
        encoding="utf-8",
    )
    project_state = cataforge_dir / "PROJECT-STATE.md"
    project_state.write_text(
        "# state\n运行时: {platform}\n", encoding="utf-8"
    )

    platforms_dir = cataforge_dir / "platforms" / "claude-code"
    platforms_dir.mkdir(parents=True)
    with open(platforms_dir / "profile.yaml", "w", encoding="utf-8") as f:
        yaml.dump(_minimal_profile(**profile_kwargs), f, sort_keys=False)

    return project_state, tmp_path


def _hashes(root: Path) -> dict:
    p = root / ".cataforge" / ".instruction-hashes.json"
    if not p.is_file():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


class TestDefaultIsOverwrite:
    def test_no_field_writes_every_time(self, tmp_path: Path) -> None:
        project_state, root = _setup(tmp_path, path="CLAUDE.md")
        claude_md = root / "CLAUDE.md"
        claude_md.write_text("# manually written\n", encoding="utf-8")

        adapter = get_adapter(
            "claude-code", root / ".cataforge" / "platforms"
        )
        adapter.deploy_instruction_files(
            project_state, root, platform_id="claude-code", dry_run=False
        )

        # Default is overwrite — manual content is replaced
        assert "manually written" not in claude_md.read_text(encoding="utf-8")
        assert "运行时: claude-code" in claude_md.read_text(encoding="utf-8")

    def test_overwrite_records_hash(self, tmp_path: Path) -> None:
        project_state, root = _setup(tmp_path, path="CLAUDE.md")
        adapter = get_adapter(
            "claude-code", root / ".cataforge" / "platforms"
        )
        adapter.deploy_instruction_files(
            project_state, root, platform_id="claude-code", dry_run=False
        )

        # Hash reflects the bytes actually on disk (CRLF-safe on Windows).
        expected = hashlib.sha256((root / "CLAUDE.md").read_bytes()).hexdigest()
        assert _hashes(root).get("CLAUDE.md") == expected


class TestPreserve:
    def test_skip_when_target_exists(self, tmp_path: Path) -> None:
        project_state, root = _setup(
            tmp_path, path="CLAUDE.md", on_conflict="preserve"
        )
        claude_md = root / "CLAUDE.md"
        claude_md.write_text("# hand-curated\n", encoding="utf-8")

        adapter = get_adapter(
            "claude-code", root / ".cataforge" / "platforms"
        )
        actions = adapter.deploy_instruction_files(
            project_state, root, platform_id="claude-code", dry_run=False
        )

        assert claude_md.read_text(encoding="utf-8") == "# hand-curated\n"
        assert any("on_conflict=preserve" in a for a in actions)

    def test_writes_when_target_absent(self, tmp_path: Path) -> None:
        project_state, root = _setup(
            tmp_path, path="CLAUDE.md", on_conflict="preserve"
        )
        adapter = get_adapter(
            "claude-code", root / ".cataforge" / "platforms"
        )
        adapter.deploy_instruction_files(
            project_state, root, platform_id="claude-code", dry_run=False
        )

        assert (root / "CLAUDE.md").is_file()
        assert "运行时: claude-code" in (root / "CLAUDE.md").read_text(
            encoding="utf-8"
        )


class TestPreserveIfEdited:
    def test_overwrites_when_unedited(self, tmp_path: Path) -> None:
        project_state, root = _setup(
            tmp_path, path="CLAUDE.md", on_conflict="preserve_if_edited"
        )
        adapter = get_adapter(
            "claude-code", root / ".cataforge" / "platforms"
        )
        # First deploy records the hash
        adapter.deploy_instruction_files(
            project_state, root, platform_id="claude-code", dry_run=False
        )
        first = (root / "CLAUDE.md").read_text(encoding="utf-8")

        # Mutate the template and re-deploy; file should update because the
        # on-disk content matches last-deployed hash (no user edit).
        project_state.write_text(
            "# state v2\n运行时: {platform}\n", encoding="utf-8"
        )
        adapter.deploy_instruction_files(
            project_state, root, platform_id="claude-code", dry_run=False
        )
        second = (root / "CLAUDE.md").read_text(encoding="utf-8")

        assert first != second
        assert "state v2" in second

    def test_skips_when_user_edited(self, tmp_path: Path) -> None:
        project_state, root = _setup(
            tmp_path, path="CLAUDE.md", on_conflict="preserve_if_edited"
        )
        adapter = get_adapter(
            "claude-code", root / ".cataforge" / "platforms"
        )
        adapter.deploy_instruction_files(
            project_state, root, platform_id="claude-code", dry_run=False
        )

        # User modifies CLAUDE.md
        claude_md = root / "CLAUDE.md"
        claude_md.write_text("# USER EDIT\n", encoding="utf-8")

        # Template changes but re-deploy must not touch user's edits
        project_state.write_text(
            "# state v2\n运行时: {platform}\n", encoding="utf-8"
        )
        actions = adapter.deploy_instruction_files(
            project_state, root, platform_id="claude-code", dry_run=False
        )

        assert claude_md.read_text(encoding="utf-8") == "# USER EDIT\n"
        assert any("preserve_if_edited" in a for a in actions)

    def test_first_deploy_writes_without_prior_hash(
        self, tmp_path: Path
    ) -> None:
        project_state, root = _setup(
            tmp_path, path="CLAUDE.md", on_conflict="preserve_if_edited"
        )
        # Target exists (e.g. from a previous framework version without hash
        # tracking). Missing hash means no basis for diffing, so we treat the
        # file as the trusted state and skip to be safe.
        claude_md = root / "CLAUDE.md"
        claude_md.write_text("# pre-existing\n", encoding="utf-8")

        adapter = get_adapter(
            "claude-code", root / ".cataforge" / "platforms"
        )
        adapter.deploy_instruction_files(
            project_state, root, platform_id="claude-code", dry_run=False
        )

        # No hash recorded → overwrite (first deploy semantics)
        assert "# pre-existing" not in claude_md.read_text(encoding="utf-8")


class TestInvalidValue:
    def test_invalid_on_conflict_skips_target(self, tmp_path: Path) -> None:
        project_state, root = _setup(
            tmp_path, path="CLAUDE.md", on_conflict="bogus"
        )
        adapter = get_adapter(
            "claude-code", root / ".cataforge" / "platforms"
        )
        actions = adapter.deploy_instruction_files(
            project_state, root, platform_id="claude-code", dry_run=False
        )
        assert any("invalid on_conflict" in a for a in actions)
        assert not (root / "CLAUDE.md").exists()
