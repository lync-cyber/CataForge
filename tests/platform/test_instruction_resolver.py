"""Cross-platform instruction-file resolution (CLAUDE.md / AGENTS.md)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from cataforge.adapter.platform.registry import clear_cache, resolve_instruction_file


def _make_project(tmp_path: Path, platform_id: str, profiles: dict) -> Path:
    cataforge = tmp_path / ".cataforge"
    cataforge.mkdir()
    (cataforge / "framework.json").write_text(
        json.dumps({"version": "0.1.0", "runtime": {"platform": platform_id}}),
        encoding="utf-8",
    )
    for pid, profile in profiles.items():
        p = cataforge / "platforms" / pid
        p.mkdir(parents=True)
        (p / "profile.yaml").write_text(yaml.dump(profile), encoding="utf-8")
    return tmp_path


@pytest.fixture(autouse=True)
def _clean_platform_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("CATAFORGE_PLATFORM", "CLAUDE_PROJECT_DIR", "CURSOR_PROJECT_DIR", "CODEX_HOME"):
        monkeypatch.delenv(var, raising=False)
    clear_cache()


def test_resolves_claude_md_for_claude_code(tmp_path: Path) -> None:
    root = _make_project(
        tmp_path,
        "claude-code",
        {
            "claude-code": {
                "platform_id": "claude-code",
                "instruction_file": {
                    "reads_claude_md": True,
                    "targets": [{"type": "project_state_copy", "path": "CLAUDE.md"}],
                },
            }
        },
    )
    assert resolve_instruction_file(root) == root / "CLAUDE.md"


def test_resolves_agents_md_for_cursor(tmp_path: Path) -> None:
    root = _make_project(
        tmp_path,
        "cursor",
        {
            "cursor": {
                "platform_id": "cursor",
                "instruction_file": {
                    "targets": [{"type": "project_state_copy", "path": "AGENTS.md"}],
                },
            }
        },
    )
    assert resolve_instruction_file(root) == root / "AGENTS.md"
