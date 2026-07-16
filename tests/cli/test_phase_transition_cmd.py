"""Tests for ``cataforge phase transition`` — the deterministic gate chain."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from click.testing import CliRunner

from cataforge.core.claude_md_hygiene import limit_breaches, measure_claude_md
from cataforge.interface.cli.main import cli

_WORKFLOW = {
    "modes": {
        "standard": {
            "phases": [
                {"phase": "architecture", "role": "architect", "execution_host": "inline"},
                {"phase": "ui_design", "role": "ui-designer", "execution_host": "inline"},
                {"phase": "dev_planning", "role": "tech-lead", "execution_host": "subagent"},
            ]
        }
    }
}


def _write_doc(
    tmp: Path, doc_type: str, *, status: str = "approved", deps: list[str] | None = None
) -> None:
    subdir = tmp / "docs" / doc_type
    subdir.mkdir(parents=True, exist_ok=True)
    dep_line = f"deps: [{', '.join(deps)}]\n" if deps else ""
    (subdir / f"{doc_type}-proj.md").write_text(
        f"---\nid: {doc_type}-proj\ndoc_type: {doc_type}\nstatus: {status}\n"
        f'version: "1.0"\n{dep_line}---\n# {doc_type}\n## §1 节\n内容。\n',
        encoding="utf-8",
    )


def _make_project(
    tmp: Path,
    *,
    phase: str = "architecture",
    doc_status: dict[str, str] | None = None,
    docs: tuple[str, ...] = ("prd",),
    index: bool = True,
) -> Path:
    (tmp / ".cataforge").mkdir()
    (tmp / ".cataforge" / "framework.json").write_text(
        json.dumps({"schema_version": 2, "context": {"mode": "markdown"}, "workflow": _WORKFLOW}),
        encoding="utf-8",
    )
    lines = ["# Proj", "## 项目状态", f"- 当前阶段: {phase}", "- 文档状态:"]
    for dt, st in (doc_status or {"prd": "approved"}).items():
        lines.append(f"  - {dt}: {st}")
    (tmp / "CLAUDE.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    for doc_type in docs:
        _write_doc(tmp, doc_type)
    if index:
        result = CliRunner().invoke(cli, ["context", "index", "--project-root", str(tmp)])
        assert result.exit_code == 0, result.output
    return tmp


def _transition(tmp: Path, *args: str) -> subprocess.CompletedProcess[str] | object:
    return CliRunner().invoke(
        cli,
        ["phase", "transition", "--project-root", str(tmp), *args],
    )


def _read_events(tmp: Path) -> list[dict]:
    log = tmp / "docs" / "EVENT-LOG.jsonl"
    if not log.is_file():
        return []
    return [json.loads(line) for line in log.read_text().splitlines() if line.strip()]


class TestTransitionHappyPath:
    def test_full_pass_appends_batch_and_hints_dispatch(self, tmp_path: Path) -> None:
        proj = _make_project(tmp_path)
        result = _transition(proj, "--from", "requirements", "--to", "architecture")
        assert result.exit_code == 0, result.output
        events = _read_events(proj)
        assert [e["event"] for e in events] == [
            "phase_end",
            "review_verdict",
            "state_change",
            "phase_start",
        ]
        assert events[0]["phase"] == "requirements"
        assert events[3]["phase"] == "architecture"
        assert events[2]["detail"] == "CLAUDE.md 阶段更新: requirements → architecture"
        assert "role=architect" in result.output

    def test_rerun_skips_event_batch(self, tmp_path: Path) -> None:
        proj = _make_project(tmp_path)
        first = _transition(proj, "--from", "requirements", "--to", "architecture")
        assert first.exit_code == 0, first.output
        second = _transition(proj, "--from", "requirements", "--to", "architecture")
        assert second.exit_code == 0, second.output
        assert "idempotent re-run" in second.output
        assert len(_read_events(proj)) == 4

    def test_json_report_shape(self, tmp_path: Path) -> None:
        proj = _make_project(tmp_path)
        result = _transition(proj, "--from", "requirements", "--to", "architecture", "--json")
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["ok"] is True
        assert payload["stopped_at"] is None
        assert payload["dispatch"] == {
            "mode": "standard",
            "phase": "architecture",
            "role": "architect",
            "execution_host": "inline",
        }
        assert {g["gate"] for g in payload["gates"]} >= {
            "doc-status",
            "stale-deps",
            "reconcile",
            "doc-consistency",
            "event-batch",
            "claude-md",
        }

    def test_completed_target_hints_retrospective(self, tmp_path: Path) -> None:
        proj = _make_project(
            tmp_path,
            phase="deployment",
            doc_status={"deploy-spec": "approved"},
            docs=("deploy-spec",),
        )
        result = _transition(proj, "--from", "deployment", "--to", "completed", "--json")
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert "Retrospective" in payload["dispatch"]["hint"]


class TestTransitionArgValidation:
    def test_unknown_phase_rejected(self, tmp_path: Path) -> None:
        proj = _make_project(tmp_path)
        result = _transition(proj, "--from", "nonsense", "--to", "architecture")
        assert result.exit_code == 1
        assert "not a recognised phase" in result.output

    def test_same_from_to_rejected(self, tmp_path: Path) -> None:
        proj = _make_project(tmp_path)
        result = _transition(proj, "--from", "architecture", "--to", "architecture")
        assert result.exit_code == 1

    def test_from_completed_rejected(self, tmp_path: Path) -> None:
        proj = _make_project(tmp_path)
        result = _transition(proj, "--from", "completed", "--to", "architecture")
        assert result.exit_code == 1

    def test_missing_instruction_file_rejected(self, tmp_path: Path) -> None:
        (tmp_path / ".cataforge").mkdir()
        (tmp_path / ".cataforge" / "framework.json").write_text("{}", encoding="utf-8")
        result = _transition(tmp_path, "--from", "requirements", "--to", "architecture")
        assert result.exit_code == 1
        assert "not a driven CataForge project" in result.output

    def test_phase_field_mismatch_warns_without_blocking(self, tmp_path: Path) -> None:
        proj = _make_project(tmp_path, phase="testing")
        result = _transition(proj, "--from", "requirements", "--to", "architecture", "--json")
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        warned = [g for g in payload["gates"] if g["gate"] == "phase-field"]
        assert warned and warned[0]["outcome"] == "warn"


class TestDocStatusGate:
    def test_unapproved_doc_stops(self, tmp_path: Path) -> None:
        proj = _make_project(tmp_path, doc_status={"prd": "draft"})
        result = _transition(proj, "--from", "requirements", "--to", "architecture", "--json")
        assert result.exit_code == 3
        payload = json.loads(result.output.splitlines()[0])
        assert payload["stopped_at"] == "doc-status"
        assert payload["gates"][0]["options"]
        assert len(_read_events(proj)) == 0

    def test_frontmatter_draft_stops_even_if_field_approved(self, tmp_path: Path) -> None:
        proj = _make_project(tmp_path, docs=())
        _write_doc(proj, "prd", status="draft")
        CliRunner().invoke(cli, ["context", "index", "--project-root", str(proj)])
        result = _transition(proj, "--from", "requirements", "--to", "architecture", "--json")
        assert result.exit_code == 3
        payload = json.loads(result.output.splitlines()[0])
        assert payload["stopped_at"] == "doc-status"
        assert "frontmatter status = draft" in payload["gates"][0]["detail"]

    def test_phase_without_doc_gate_skips(self, tmp_path: Path) -> None:
        proj = _make_project(tmp_path, phase="development", doc_status={"prd": "approved"})
        result = _transition(proj, "--from", "development", "--to", "testing", "--json")
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        doc_gate = next(g for g in payload["gates"] if g["gate"] == "doc-status")
        assert doc_gate["outcome"] == "skip"

    def test_approved_with_notes_accepted(self, tmp_path: Path) -> None:
        proj = _make_project(tmp_path, docs=())
        _write_doc(proj, "prd", status="approved_with_notes")
        CliRunner().invoke(cli, ["context", "index", "--project-root", str(proj)])
        result = _transition(proj, "--from", "requirements", "--to", "architecture")
        assert result.exit_code == 0, result.output


class TestStaleDepsGate:
    def test_missing_index_stops(self, tmp_path: Path) -> None:
        proj = _make_project(tmp_path, index=False)
        result = _transition(proj, "--from", "requirements", "--to", "architecture", "--json")
        assert result.exit_code == 3
        payload = json.loads(result.output.splitlines()[0])
        assert payload["stopped_at"] == "stale-deps"
        assert "context index" in payload["gates"][1]["options"][0]["action"]

    def test_index_integrity_failure_stops(self, tmp_path: Path) -> None:
        proj = _make_project(tmp_path)
        (proj / "docs" / "orphan.md").write_text("no front matter\n", encoding="utf-8")
        result = _transition(proj, "--from", "requirements", "--to", "architecture", "--json")
        assert result.exit_code == 3
        payload = json.loads(result.output.splitlines()[0])
        assert payload["stopped_at"] == "stale-deps"
        assert "integrity" in payload["gates"][1]["detail"]

    @staticmethod
    def _poison_dep_pin(proj: Path) -> None:
        index_path = proj / "docs" / ".doc-index.json"
        index = json.loads(index_path.read_text())
        index["documents"]["arch-proj"]["dep_hashes"] = {"prd-proj": "deadbeef"}
        index_path.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")

    def test_stale_dep_stops_with_protocol_options(self, tmp_path: Path) -> None:
        proj = _make_project(
            tmp_path,
            doc_status={"prd": "approved", "arch": "approved"},
            docs=("prd", "arch"),
        )
        self._poison_dep_pin(proj)
        result = _transition(proj, "--from", "architecture", "--to", "ui_design", "--json")
        assert result.exit_code == 3
        payload = json.loads(result.output.splitlines()[0])
        assert payload["stopped_at"] == "stale-deps"
        gate = next(g for g in payload["gates"] if g["gate"] == "stale-deps")
        assert len(gate["options"]) == 3
        assert "--ack-stale-deps" in gate["options"][1]["action"]

    def test_ack_degrades_to_warn_and_logs_decision(self, tmp_path: Path) -> None:
        proj = _make_project(
            tmp_path,
            doc_status={"prd": "approved", "arch": "approved"},
            docs=("prd", "arch"),
        )
        self._poison_dep_pin(proj)
        result = _transition(
            proj, "--from", "architecture", "--to", "ui_design", "--ack-stale-deps"
        )
        assert result.exit_code == 0, result.output
        events = _read_events(proj)
        assert len(events) == 5
        assert events[0]["event"] == "state_change"
        assert events[0]["detail"] == "stale deps acknowledged: prd-proj"
        assert events[0]["phase"] == "architecture"


class TestDocConsistencyGate:
    def test_fewer_than_two_approved_docs_skips(self, tmp_path: Path) -> None:
        proj = _make_project(tmp_path)
        result = _transition(proj, "--from", "requirements", "--to", "architecture", "--json")
        payload = json.loads(result.output)
        gate = next(g for g in payload["gates"] if g["gate"] == "doc-consistency")
        assert gate["outcome"] == "skip"

    def test_two_approved_docs_runs_check(self, tmp_path: Path) -> None:
        proj = _make_project(
            tmp_path,
            doc_status={"prd": "approved", "arch": "approved"},
            docs=("prd", "arch"),
        )
        result = _transition(proj, "--from", "architecture", "--to", "ui_design", "--json")
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        gate = next(g for g in payload["gates"] if g["gate"] == "doc-consistency")
        assert gate["outcome"] in ("pass", "warn")

    def _fake_run(self, returncode: int, stdout: str):
        def run(self_, skill_id, args=None, script_name=None, *, agent=None, timeout=None):
            return subprocess.CompletedProcess(
                args=[skill_id], returncode=returncode, stdout=stdout, stderr=""
            )

        return run

    def test_blocking_findings_stop_with_options(self, tmp_path: Path, monkeypatch) -> None:
        proj = _make_project(
            tmp_path,
            doc_status={"prd": "approved", "arch": "approved"},
            docs=("prd", "arch"),
        )
        from cataforge.runtime.skill.runner import SkillRunner

        report = json.dumps({"issues": [{"severity": "HIGH", "message": "AC 未覆盖"}]})
        monkeypatch.setattr(SkillRunner, "run", self._fake_run(1, report))
        result = _transition(proj, "--from", "architecture", "--to", "ui_design", "--json")
        assert result.exit_code == 3
        payload = json.loads(result.output.splitlines()[0])
        assert payload["stopped_at"] == "doc-consistency"
        gate = next(g for g in payload["gates"] if g["gate"] == "doc-consistency")
        assert "1 HIGH" in gate["detail"]
        assert any("--ack-inconsistency" in o["action"] for o in gate["options"])
        assert len(_read_events(proj)) == 0

    def test_ack_inconsistency_degrades_and_logs(self, tmp_path: Path, monkeypatch) -> None:
        proj = _make_project(
            tmp_path,
            doc_status={"prd": "approved", "arch": "approved"},
            docs=("prd", "arch"),
        )
        from cataforge.runtime.skill.runner import SkillRunner

        report = json.dumps({"issues": [{"severity": "CRITICAL", "message": "接口漂移"}]})
        monkeypatch.setattr(SkillRunner, "run", self._fake_run(1, report))
        result = _transition(
            proj, "--from", "architecture", "--to", "ui_design", "--ack-inconsistency"
        )
        assert result.exit_code == 0, result.output
        events = _read_events(proj)
        assert len(events) == 5
        assert "degraded to WARN" in events[0]["detail"]

    def test_medium_findings_warn_and_log_without_blocking(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        proj = _make_project(
            tmp_path,
            doc_status={"prd": "approved", "arch": "approved"},
            docs=("prd", "arch"),
        )
        from cataforge.runtime.skill.runner import SkillRunner

        report = json.dumps({"issues": [{"severity": "MEDIUM", "message": "术语不一致"}]})
        monkeypatch.setattr(SkillRunner, "run", self._fake_run(0, report))
        result = _transition(proj, "--from", "architecture", "--to", "ui_design")
        assert result.exit_code == 0, result.output
        events = _read_events(proj)
        assert len(events) == 5
        assert "doc-consistency WARN" in events[0]["detail"]

    def test_layer1_environment_failure_fails_with_exit_1(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        proj = _make_project(
            tmp_path,
            doc_status={"prd": "approved", "arch": "approved"},
            docs=("prd", "arch"),
        )
        from cataforge.runtime.skill.runner import SkillRunner

        monkeypatch.setattr(SkillRunner, "run", self._fake_run(2, ""))
        result = _transition(proj, "--from", "architecture", "--to", "ui_design", "--json")
        assert result.exit_code == 1
        payload = json.loads(result.output.splitlines()[0])
        assert payload["stopped_at"] == "doc-consistency"
        gate = next(g for g in payload["gates"] if g["gate"] == "doc-consistency")
        assert gate["outcome"] == "fail"
        assert "doctor" in gate["detail"]


class TestClaudeMdGate:
    def _bloat_registry(self, proj: Path, entries: int = 4, limit: int = 2) -> None:
        framework = proj / ".cataforge" / "framework.json"
        data = json.loads(framework.read_text())
        data["claude_md_limits"] = {
            "max_bytes": 30000,
            "max_state_section_lines": 80,
            "learnings_registry_max_entries": limit,
            "max_state_bullet_chars": 500,
        }
        framework.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        claude_md = proj / "CLAUDE.md"
        body = claude_md.read_text() + "- Learnings Registry:\n"
        body += "".join(f"  - L{i} 经验\n" for i in range(entries))
        claude_md.write_text(body, encoding="utf-8")

    def test_breach_stops_after_event_batch(self, tmp_path: Path) -> None:
        proj = _make_project(tmp_path)
        self._bloat_registry(proj)
        result = _transition(proj, "--from", "requirements", "--to", "architecture", "--json")
        assert result.exit_code == 3
        payload = json.loads(result.output.splitlines()[0])
        assert payload["stopped_at"] == "claude-md"
        assert len(_read_events(proj)) == 4  # batch landed before the hygiene stop

    def test_compact_rerun_fixes_and_logs_event(self, tmp_path: Path) -> None:
        proj = _make_project(tmp_path)
        self._bloat_registry(proj)
        first = _transition(proj, "--from", "requirements", "--to", "architecture")
        assert first.exit_code == 3
        second = _transition(proj, "--from", "requirements", "--to", "architecture", "--compact")
        assert second.exit_code == 0, second.output
        events = _read_events(proj)
        assert len(events) == 5  # 4-record batch (not duplicated) + compact record
        assert events[-1]["detail"] == "claude-md compact applied at phase transition"
        assert events[-1]["phase"] == "architecture"
        measurement = measure_claude_md(proj / "CLAUDE.md")
        assert measurement.learnings_entries <= 2


class TestLimitBreaches:
    def test_within_limits_is_empty(self, tmp_path: Path) -> None:
        md = tmp_path / "CLAUDE.md"
        md.write_text("# t\n## 项目状态\n- 当前阶段: x\n", encoding="utf-8")
        limits = {
            "max_bytes": 30000,
            "max_state_section_lines": 80,
            "learnings_registry_max_entries": 10,
            "max_state_bullet_chars": 500,
        }
        assert limit_breaches(measure_claude_md(md), limits) == []

    def test_reports_key_measured_and_limit(self, tmp_path: Path) -> None:
        md = tmp_path / "CLAUDE.md"
        md.write_text("# t\n## 项目状态\n- 当前阶段: x\n", encoding="utf-8")
        limits = {
            "max_bytes": 1,
            "max_state_section_lines": 80,
            "learnings_registry_max_entries": 10,
            "max_state_bullet_chars": 500,
        }
        breaches = limit_breaches(measure_claude_md(md), limits)
        assert len(breaches) == 1
        key, measured, limit = breaches[0]
        assert key == "max_bytes"
        assert measured > limit == 1

    def test_missing_file_never_breaches(self, tmp_path: Path) -> None:
        limits = {
            "max_bytes": 0,
            "max_state_section_lines": 0,
            "learnings_registry_max_entries": 0,
            "max_state_bullet_chars": 0,
        }
        assert limit_breaches(measure_claude_md(tmp_path / "CLAUDE.md"), limits) == []
