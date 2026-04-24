"""Tests for doctor's EVENT-LOG schema sample and heredoc-bypass guard."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

from click.testing import CliRunner

from cataforge.cli.doctor_cmd import doctor_command


def _project(tmp_path: Path) -> Path:
    cf = tmp_path / ".cataforge"
    (cf / "hooks").mkdir(parents=True)
    (cf / "framework.json").write_text(
        json.dumps({"version": "0.1.0", "runtime": {"platform": "claude-code"}}),
        encoding="utf-8",
    )
    # minimal hooks.yaml so the importability check doesn't choke
    (cf / "hooks" / "hooks.yaml").write_text(
        "schema_version: 2\nhooks: {}\n", encoding="utf-8"
    )
    return tmp_path


def _write_event_log(project: Path, lines: list[str]) -> Path:
    log = project / "docs" / "EVENT-LOG.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return log


def test_doctor_passes_with_clean_event_log(tmp_path: Path, monkeypatch) -> None:
    project = _project(tmp_path)
    _write_event_log(
        project,
        [
            json.dumps({
                "ts": "2026-04-23T16:42:56+08:00",
                "event": "phase_start",
                "phase": "requirements",
                "detail": "OK",
            }),
        ],
    )
    monkeypatch.chdir(project)
    result = CliRunner().invoke(doctor_command, [])
    assert result.exit_code == 0, result.output
    assert "1/1 sampled records valid" in result.output


def test_doctor_flags_unknown_field_in_event_log(
    tmp_path: Path, monkeypatch
) -> None:
    project = _project(tmp_path)
    _write_event_log(
        project,
        [
            json.dumps({
                "timestamp": "2026-04-23T13:09:33Z",
                "event": "doc_revision_completed",
                "phase": "architecture",
                "detail": "bad record from heredoc bypass",
            }),
        ],
    )
    monkeypatch.chdir(project)
    result = CliRunner().invoke(doctor_command, [])
    assert result.exit_code == 1, result.output
    assert "0/1 sampled records valid" in result.output
    assert "timestamp" in result.output
    assert "doc_revision_completed" in result.output


def test_doctor_flags_invalid_json_in_event_log(tmp_path: Path, monkeypatch) -> None:
    project = _project(tmp_path)
    _write_event_log(project, ["{not even json", '{"ts": "x"}'])
    monkeypatch.chdir(project)
    result = CliRunner().invoke(doctor_command, [])
    assert result.exit_code == 1, result.output
    assert "invalid JSON" in result.output


def test_doctor_passes_when_event_log_absent(tmp_path: Path, monkeypatch) -> None:
    project = _project(tmp_path)
    monkeypatch.chdir(project)
    result = CliRunner().invoke(doctor_command, [])
    assert result.exit_code == 0, result.output
    assert "no EVENT-LOG.jsonl yet" in result.output


def test_doctor_flags_heredoc_bypass_in_skill(tmp_path: Path, monkeypatch) -> None:
    project = _project(tmp_path)
    skill_dir = project / ".cataforge" / "skills" / "evil-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        textwrap.dedent("""
            # Evil Skill

            Step 1: log the event:

                echo '{"event":"x","phase":"y","detail":"z"}' >> docs/EVENT-LOG.jsonl
        """),
        encoding="utf-8",
    )
    monkeypatch.chdir(project)
    result = CliRunner().invoke(doctor_command, [])
    assert result.exit_code == 1, result.output
    assert "bypass write" in result.output
    assert ".cataforge/skills/evil-skill/SKILL.md" in result.output


def test_doctor_passes_with_clean_skill_templates(
    tmp_path: Path, monkeypatch
) -> None:
    project = _project(tmp_path)
    skill_dir = project / ".cataforge" / "skills" / "good-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "Step 1: `cataforge event log --event phase_start --phase x --detail y`\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(project)
    result = CliRunner().invoke(doctor_command, [])
    assert result.exit_code == 0, result.output
    assert "no heredoc/redirect writes" in result.output


def _set_cutoff(project: Path, ts: str) -> None:
    """Patch framework.json with a validation cutoff."""
    fw = project / ".cataforge" / "framework.json"
    data = json.loads(fw.read_text(encoding="utf-8"))
    data.setdefault("upgrade", {}).setdefault("state", {})[
        "event_log_validate_since"
    ] = ts
    fw.write_text(json.dumps(data) + "\n", encoding="utf-8")


def test_doctor_skips_pre_cutoff_legacy_records(
    tmp_path: Path, monkeypatch
) -> None:
    """Records with ts < cutoff must not count toward doctor's failure tally."""
    project = _project(tmp_path)
    _write_event_log(
        project,
        [
            # Legacy bypass write — would fail schema validation.
            json.dumps({
                "ts": "2025-12-01T10:00:00+00:00",
                "event": "doc_revision_completed",
                "phase": "architecture",
                "detail": "pre-v0.1.7 bypass",
            }),
            # Post-cutoff, clean record.
            json.dumps({
                "ts": "2026-04-23T16:42:56+08:00",
                "event": "phase_start",
                "phase": "requirements",
                "detail": "OK",
            }),
        ],
    )
    _set_cutoff(project, "2026-01-01T00:00:00+00:00")
    monkeypatch.chdir(project)

    result = CliRunner().invoke(doctor_command, [])
    assert result.exit_code == 0, result.output
    assert "1 pre-cutoff skipped" in result.output
    assert "1/1 sampled records valid" in result.output


def test_doctor_still_fails_on_post_cutoff_invalid_records(
    tmp_path: Path, monkeypatch
) -> None:
    """The cutoff must not hide failures that happen AFTER it — otherwise
    setting a cutoff would silently suppress legitimate schema breakage."""
    project = _project(tmp_path)
    _write_event_log(
        project,
        [
            json.dumps({
                "ts": "2026-05-01T10:00:00+00:00",
                "event": "doc_revision_completed",  # bogus enum value
                "phase": "architecture",
                "detail": "recent rot",
            }),
        ],
    )
    _set_cutoff(project, "2026-01-01T00:00:00+00:00")
    monkeypatch.chdir(project)

    result = CliRunner().invoke(doctor_command, [])
    assert result.exit_code == 1, result.output
    assert "doc_revision_completed" in result.output


def test_doctor_hints_accept_legacy_when_no_cutoff_set(
    tmp_path: Path, monkeypatch
) -> None:
    """Doctor must point users at `cataforge event accept-legacy` when the
    schema check fails and no cutoff has been established — otherwise the
    escape hatch is undiscoverable."""
    project = _project(tmp_path)
    _write_event_log(
        project,
        [
            json.dumps({
                "ts": "2025-12-01T10:00:00+00:00",
                "event": "doc_revision_completed",
                "phase": "architecture",
                "detail": "legacy",
            }),
        ],
    )
    monkeypatch.chdir(project)

    result = CliRunner().invoke(doctor_command, [])
    assert result.exit_code == 1, result.output
    assert "cataforge event accept-legacy" in result.output


def test_doctor_tolerates_malformed_cutoff(
    tmp_path: Path, monkeypatch
) -> None:
    """A garbage cutoff value must warn and fall back to validating all
    records — doctor should never crash on bad user config."""
    project = _project(tmp_path)
    _write_event_log(
        project,
        [
            json.dumps({
                "ts": "2026-04-23T16:42:56+08:00",
                "event": "phase_start",
                "phase": "requirements",
                "detail": "OK",
            }),
        ],
    )
    _set_cutoff(project, "not-a-timestamp")
    monkeypatch.chdir(project)

    result = CliRunner().invoke(doctor_command, [])
    assert result.exit_code == 0, result.output
    assert "ignoring malformed event_log_validate_since" in result.output
