"""Tests for subprocess timeout in SkillRunner."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from cataforge.runtime.skill.runner import SkillRunner, SkillTimeoutError


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / ".cataforge").mkdir()
    return tmp_path


def _write_skill(
    project_root: Path,
    skill_id: str,
    *,
    script_body: str,
    record_event_log: bool = True,
) -> None:
    skill_dir = project_root / ".cataforge" / "skills" / skill_id
    skill_dir.mkdir(parents=True)
    record_flag = "true" if record_event_log else "false"
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {skill_id}\ndescription: test\n"
        f"record-to-event-log: {record_flag}\n---\nBody.\n",
        encoding="utf-8",
    )
    scripts_dir = skill_dir / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "main.py").write_text(script_body, encoding="utf-8")


SLEEP_LONG = Path(__file__).parent / "fixtures" / "sleep_long.py"


class TestSkillRunnerTimeout:
    def test_timeout_raises_skill_timeout_error(self, project: Path) -> None:
        _write_skill(
            project,
            "slow-skill",
            script_body="import time; time.sleep(600)\n",
        )
        runner = SkillRunner(project)
        with pytest.raises(SkillTimeoutError) as exc_info:
            runner.run("slow-skill", timeout=1)
        assert exc_info.value.skill_id == "slow-skill"
        assert exc_info.value.timeout_secs == 1.0

    def test_timeout_returns_within_deadline(self, project: Path) -> None:
        _write_skill(
            project,
            "slow-skill",
            script_body="import time; time.sleep(600)\n",
        )
        runner = SkillRunner(project)
        t0 = time.monotonic()
        with pytest.raises(SkillTimeoutError):
            runner.run("slow-skill", timeout=1)
        elapsed = time.monotonic() - t0
        assert elapsed < 1.5, f"Expected return within 1.5s, got {elapsed:.2f}s"

    def test_timeout_emits_skill_timeout_event(self, project: Path) -> None:
        _write_skill(
            project,
            "slow-review",
            script_body="import time; time.sleep(600)\n",
            record_event_log=True,
        )
        runner = SkillRunner(project)
        with pytest.raises(SkillTimeoutError):
            runner.run("slow-review", timeout=1)

        log = project / "docs" / "EVENT-LOG.jsonl"
        assert log.is_file(), "timeout must write an EVENT-LOG entry"
        records = [
            json.loads(ln)
            for ln in log.read_text().splitlines()
            if ln.strip()
        ]
        timeout_records = [r for r in records if "skill_timeout" in r.get("detail", "")]
        assert timeout_records, "no skill_timeout entry found in EVENT-LOG"
        rec = timeout_records[-1]
        assert rec.get("status") == "blocked"
        assert "slow-review" in rec["detail"]
        assert "1.0s" in rec["detail"] or "1s" in rec["detail"]
        assert "elapsed=" in rec["detail"]

    def test_timeout_zero_disables_limit(self, project: Path) -> None:
        _write_skill(
            project,
            "fast-skill",
            script_body="print('done')\n",
        )
        runner = SkillRunner(project)
        result = runner.run("fast-skill", timeout=0)
        assert result.returncode == 0

    def test_normal_run_unaffected_by_default_timeout(self, project: Path) -> None:
        _write_skill(
            project,
            "quick-skill",
            script_body="print('ok')\n",
        )
        runner = SkillRunner(project)
        result = runner.run("quick-skill")
        assert result.returncode == 0
        assert "ok" in result.stdout
