"""upgrade.py 升级后验证逻辑测试"""

import os
import sys


_scripts = os.path.join(os.path.dirname(__file__), "..", ".claude", "scripts")
sys.path.insert(0, os.path.join(_scripts, "lib"))
sys.path.insert(0, os.path.join(_scripts, "framework"))
from _upgrade_verify import check_feature_applicability, check_file_integrity


# ── check_feature_applicability ──────────────────────────────────────────


class TestCheckFeatureApplicability:
    def _matrix(self, **kwargs):
        defaults = {
            "min_version": "0.1.0",
            "auto_enable": True,
            "phase_guard": None,
            "description": "test feature",
        }
        defaults.update(kwargs)
        return {"features": {"test-feature": defaults}}

    def test_existing_feature(self):
        matrix = self._matrix(min_version="0.1.0")
        results = check_feature_applicability(matrix, "development", "0.1.0")
        assert results[0]["status"] == "existing"

    def test_auto_enabled_no_guard(self):
        matrix = self._matrix(min_version="0.2.0")
        results = check_feature_applicability(matrix, "development", "0.1.0")
        assert results[0]["status"] == "auto-enabled"

    def test_opt_in(self):
        matrix = self._matrix(min_version="0.2.0", auto_enable=False)
        results = check_feature_applicability(matrix, "development", "0.1.0")
        assert results[0]["status"] == "opt-in"

    def test_phase_guard_before(self):
        matrix = self._matrix(min_version="0.2.0", phase_guard="development")
        results = check_feature_applicability(matrix, "architecture", "0.1.0")
        assert results[0]["status"] == "auto-enabled"

    def test_phase_guard_after(self):
        matrix = self._matrix(min_version="0.2.0", phase_guard="architecture")
        results = check_feature_applicability(matrix, "development", "0.1.0")
        assert results[0]["status"] == "next-project"


# ── check_file_integrity ────────────────────────────────────────────────


class TestCheckFileIntegrity:
    def test_valid_structure(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        # Create agent referencing a skill
        agent_dir = tmp_path / ".claude" / "agents" / "test-agent"
        agent_dir.mkdir(parents=True)
        (agent_dir / "AGENT.md").write_text(
            "---\nname: test-agent\nskills:\n  - test-skill\nmodel: inherit\n---\n"
        )

        # Create the referenced skill
        skill_dir = tmp_path / ".claude" / "skills" / "test-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: test-skill\ndescription: test\n---\n"
        )

        issues = check_file_integrity()
        assert len(issues) == 0

    def test_missing_skill(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        agent_dir = tmp_path / ".claude" / "agents" / "test-agent"
        agent_dir.mkdir(parents=True)
        (agent_dir / "AGENT.md").write_text(
            "---\nname: test-agent\nskills:\n  - nonexistent-skill\nmodel: inherit\n---\n"
        )

        # Don't create the skill
        (tmp_path / ".claude" / "skills").mkdir(parents=True)

        issues = check_file_integrity()
        assert len(issues) >= 1
        assert "nonexistent-skill" in issues[0]
