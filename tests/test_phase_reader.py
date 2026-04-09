"""phase_reader.py shared utility tests"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".claude", "scripts"))
from phase_reader import read_current_phase


class TestReadCurrentPhase:
    def test_returns_phase_from_claude_md(self, tmp_path):
        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text(
            "# CataForge\n\n## 项目状态\n\n- 当前阶段: architecture\n",
            encoding="utf-8",
        )
        assert read_current_phase(str(tmp_path)) == "architecture"

    def test_returns_unknown_when_no_file(self, tmp_path):
        assert read_current_phase(str(tmp_path)) == "unknown"

    def test_returns_unknown_for_template_placeholder(self, tmp_path):
        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text(
            "- 当前阶段: {requirements|architecture|completed}\n",
            encoding="utf-8",
        )
        assert read_current_phase(str(tmp_path)) == "unknown"

    def test_strips_trailing_content(self, tmp_path):
        """Phase line with extra content after pipe should only return the phase"""
        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text(
            "- 当前阶段: development|testing\n",
            encoding="utf-8",
        )
        assert read_current_phase(str(tmp_path)) == "development"

    def test_handles_whitespace(self, tmp_path):
        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text(
            "  - 当前阶段:   testing  \n",
            encoding="utf-8",
        )
        assert read_current_phase(str(tmp_path)) == "testing"

    def test_all_valid_phases(self, tmp_path):
        phases = [
            "requirements",
            "architecture",
            "ui_design",
            "dev_planning",
            "development",
            "testing",
            "deployment",
            "completed",
        ]
        claude_md = tmp_path / "CLAUDE.md"
        for phase in phases:
            claude_md.write_text(f"- 当前阶段: {phase}\n", encoding="utf-8")
            assert read_current_phase(str(tmp_path)) == phase
