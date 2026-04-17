"""Tests for context_injection-driven deploy behavior.

Covers three concerns:
1. The base adapter exposes ``context_injection`` as a dict passthrough.
2. Claude Code's CLAUDE.md gets the declared at-mention preamble prepended.
3. OpenCode's ``opencode.json.instructions`` is sourced from the profile
   (with a back-compat fallback when the section is absent).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from cataforge.platform.registry import clear_cache, get_adapter


@pytest.fixture(autouse=True)
def _clear() -> None:
    clear_cache()


def _write_profile(platforms_dir: Path, pid: str, data: dict) -> None:
    p = platforms_dir / pid
    p.mkdir(parents=True, exist_ok=True)
    with open(p / "profile.yaml", "w", encoding="utf-8") as f:
        yaml.dump(data, f, sort_keys=False)


def _minimal(pid: str, *, extra: dict | None = None) -> dict:
    """Produce a profile shaped just well enough for the adapter to load."""
    base: dict = {
        "platform_id": pid,
        "tool_map": {
            "file_read": "read",
            "shell_exec": "bash",
            "agent_dispatch": "task",
        },
        "agent_definition": {
            "format": "yaml-frontmatter",
            "scan_dirs": [f".{pid}/agents"],
            "needs_deploy": True,
        },
        "instruction_file": {
            "targets": [{"type": "project_state_copy", "path": "AGENTS.md"}]
        },
        "dispatch": {"tool_name": "task", "is_async": False},
    }
    if pid == "claude-code":
        base["instruction_file"]["targets"] = [
            {"type": "project_state_copy", "path": "CLAUDE.md"}
        ]
        base["tool_map"]["agent_dispatch"] = "Agent"
    if extra:
        base.update(extra)
    return base


class TestContextInjectionProperty:
    def test_returns_empty_dict_when_missing(self, tmp_path: Path) -> None:
        platforms_dir = tmp_path / ".cataforge" / "platforms"
        _write_profile(platforms_dir, "codex", _minimal("codex"))
        adapter = get_adapter("codex", platforms_dir)
        assert adapter.context_injection == {}

    def test_passes_through_declared_shape(self, tmp_path: Path) -> None:
        platforms_dir = tmp_path / ".cataforge" / "platforms"
        _write_profile(
            platforms_dir,
            "claude-code",
            _minimal(
                "claude-code",
                extra={
                    "context_injection": {
                        "auto_injection": {
                            "mechanism": "claude_md",
                            "eager": True,
                            "preamble_files": [".cataforge/rules/COMMON-RULES.md"],
                        },
                        "inline_file_syntax": {
                            "kind": "at_mention",
                            "template": "@{path}",
                        },
                    }
                },
            ),
        )
        adapter = get_adapter("claude-code", platforms_dir)
        ci = adapter.context_injection
        assert ci["auto_injection"]["mechanism"] == "claude_md"
        assert ci["inline_file_syntax"]["template"] == "@{path}"


class TestInstructionPreamble:
    def _setup(self, tmp_path: Path, *, preamble_files: list[str] | None,
               kind: str = "at_mention") -> Path:
        (tmp_path / ".cataforge").mkdir()
        platforms_dir = tmp_path / ".cataforge" / "platforms"
        ci: dict = {
            "inline_file_syntax": {"kind": kind, "template": "@{path}"},
        }
        if preamble_files is not None:
            ci["auto_injection"] = {"preamble_files": preamble_files}
        _write_profile(
            platforms_dir,
            "claude-code",
            _minimal("claude-code", extra={"context_injection": ci}),
        )
        return platforms_dir

    def test_no_preamble_when_absent(self, tmp_path: Path) -> None:
        platforms_dir = self._setup(tmp_path, preamble_files=None)
        adapter = get_adapter("claude-code", platforms_dir)
        assert adapter.get_instruction_preamble() == ""

    def test_preamble_prepends_at_mentions(self, tmp_path: Path) -> None:
        platforms_dir = self._setup(
            tmp_path,
            preamble_files=[
                ".cataforge/rules/COMMON-RULES.md",
                ".cataforge/rules/SUB-AGENT-PROTOCOLS.md",
            ],
        )
        adapter = get_adapter("claude-code", platforms_dir)
        preamble = adapter.get_instruction_preamble()
        assert preamble.startswith("@.cataforge/rules/COMMON-RULES.md")
        assert "@.cataforge/rules/SUB-AGENT-PROTOCOLS.md" in preamble
        assert preamble.endswith("\n\n")

    def test_no_preamble_for_read_tool_syntax(self, tmp_path: Path) -> None:
        platforms_dir = self._setup(
            tmp_path,
            preamble_files=[".cataforge/rules/COMMON-RULES.md"],
            kind="read_tool",
        )
        adapter = get_adapter("claude-code", platforms_dir)
        # Read-tool platforms can't cheaply preamble — they must rely on
        # rules_distribution instead, so this returns empty.
        assert adapter.get_instruction_preamble() == ""


class TestDeployInstructionFilesPreamble:
    def test_claude_code_prepends_at_preamble_to_claude_md(
        self, tmp_path: Path
    ) -> None:
        cataforge_dir = tmp_path / ".cataforge"
        cataforge_dir.mkdir()
        (cataforge_dir / "framework.json").write_text(
            json.dumps({"version": "0.1.0", "runtime": {"platform": "claude-code"}}),
            encoding="utf-8",
        )
        project_state = cataforge_dir / "PROJECT-STATE.md"
        project_state.write_text("# 项目状态\n运行时: {platform}\n", encoding="utf-8")

        platforms_dir = cataforge_dir / "platforms"
        _write_profile(
            platforms_dir,
            "claude-code",
            _minimal(
                "claude-code",
                extra={
                    "context_injection": {
                        "auto_injection": {
                            "mechanism": "claude_md",
                            "preamble_files": [".cataforge/rules/COMMON-RULES.md"],
                        },
                        "inline_file_syntax": {
                            "kind": "at_mention",
                            "template": "@{path}",
                        },
                    }
                },
            ),
        )

        adapter = get_adapter("claude-code", platforms_dir)
        adapter.deploy_instruction_files(
            project_state, tmp_path, platform_id="claude-code", dry_run=False
        )

        claude_md = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
        assert claude_md.startswith("@.cataforge/rules/COMMON-RULES.md\n\n")
        assert "运行时: claude-code" in claude_md


class TestOpenCodeInstructionsDrivenByProfile:
    def _setup_project(self, tmp_path: Path, *, ci: dict | None) -> Path:
        cataforge_dir = tmp_path / ".cataforge"
        cataforge_dir.mkdir()
        (cataforge_dir / "framework.json").write_text(
            json.dumps({"version": "0.1.0", "runtime": {"platform": "opencode"}}),
            encoding="utf-8",
        )
        project_state = cataforge_dir / "PROJECT-STATE.md"
        project_state.write_text("# state\n", encoding="utf-8")

        extra: dict = {}
        if ci is not None:
            extra["context_injection"] = ci
        _write_profile(
            cataforge_dir / "platforms", "opencode", _minimal("opencode", extra=extra)
        )
        return project_state

    def test_uses_profile_files_list(self, tmp_path: Path) -> None:
        project_state = self._setup_project(
            tmp_path,
            ci={
                "rules_distribution": {
                    "target": "opencode.json",
                    "activation": "opencode_instructions",
                    "files": ["AGENTS.md", ".cataforge/rules/*.md", "custom.md"],
                }
            },
        )
        adapter = get_adapter(
            "opencode", tmp_path / ".cataforge" / "platforms"
        )
        adapter.deploy_instruction_files(
            project_state, tmp_path, platform_id="opencode", dry_run=False
        )

        cfg = json.loads((tmp_path / "opencode.json").read_text(encoding="utf-8"))
        assert cfg["instructions"] == [
            "AGENTS.md",
            ".cataforge/rules/*.md",
            "custom.md",
        ]

    def test_falls_back_when_context_injection_absent(self, tmp_path: Path) -> None:
        project_state = self._setup_project(tmp_path, ci=None)
        adapter = get_adapter(
            "opencode", tmp_path / ".cataforge" / "platforms"
        )
        adapter.deploy_instruction_files(
            project_state, tmp_path, platform_id="opencode", dry_run=False
        )

        cfg = json.loads((tmp_path / "opencode.json").read_text(encoding="utf-8"))
        assert cfg["instructions"] == ["AGENTS.md", ".cataforge/rules/*.md"]
