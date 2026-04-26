"""Regression: doctor must catch deprecated script-name + artifact references."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from cataforge.cli.doctor_cmd import doctor_command


def _scaffold(tmp_path: Path) -> Path:
    cf = tmp_path / ".cataforge"
    cf.mkdir()
    (cf / "framework.json").write_text(
        json.dumps({"version": "0.1.0", "migration_checks": []}),
        encoding="utf-8",
    )
    # Minimal directory layout the doctor expects to scan
    for sub in ("agents", "skills", "rules", "hooks", "commands", "platforms"):
        (cf / sub).mkdir(exist_ok=True)
    return tmp_path


def test_doctor_flags_load_section_py_in_agent_md(tmp_path: Path, monkeypatch) -> None:
    root = _scaffold(tmp_path)
    agent_dir = root / ".cataforge" / "agents" / "demo"
    agent_dir.mkdir()
    (agent_dir / "AGENT.md").write_text(
        "# Demo agent\n\n按 F-xxx 通过 load_section.py 加载章节\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(root)

    result = CliRunner().invoke(doctor_command, [])
    assert result.exit_code != 0, "doctor should fail when load_section.py reference is present"
    assert "load_section.py" in result.output
    assert "cataforge docs load" in result.output
    assert "agents/demo/AGENT.md:3" in result.output


def test_doctor_flags_nav_index_md_in_skill_md(tmp_path: Path, monkeypatch) -> None:
    root = _scaffold(tmp_path)
    skill_dir = root / ".cataforge" / "skills" / "demo"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "# Demo skill\n\n读取 docs/NAV-INDEX.md 获取目录\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(root)

    result = CliRunner().invoke(doctor_command, [])
    assert result.exit_code != 0
    assert "docs/NAV-INDEX.md" in result.output
    assert "migrate-nav" in result.output


def test_doctor_passes_when_no_deprecated_refs(tmp_path: Path, monkeypatch) -> None:
    root = _scaffold(tmp_path)
    agent_dir = root / ".cataforge" / "agents" / "clean"
    agent_dir.mkdir()
    (agent_dir / "AGENT.md").write_text(
        "# Clean agent\n\n通过 `cataforge docs load prd#§2.F-001` 加载章节\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(root)

    result = CliRunner().invoke(doctor_command, [])
    # Other doctor checks may still complain (no hooks.yaml etc.), but the
    # deprecated-references section must report 0 hits — that is the contract
    # being asserted here.
    assert "Deprecated protocol references:" in result.output
    section = result.output.split("Deprecated protocol references:", 1)[1].splitlines()[1]
    assert "0 deprecated references" in section, section


def test_doctor_skips_archive_subtree(tmp_path: Path, monkeypatch) -> None:
    """Archive copies of legacy NAV-INDEX must not re-trigger the linter."""
    root = _scaffold(tmp_path)
    archive = root / ".cataforge" / ".archive"
    archive.mkdir()
    # Place a markdown archive that mentions the deprecated artifact
    (archive / "NAV-INDEX-20260101T000000Z.md").write_text(
        "legacy docs/NAV-INDEX.md content snapshot\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(root)

    result = CliRunner().invoke(doctor_command, [])
    section = result.output.split("Deprecated protocol references:", 1)[1].splitlines()[1]
    assert "0 deprecated references" in section, (
        "archive subtree must be exempt from the deprecated-reference scan"
    )


def _empty_doc_index(root: Path) -> None:
    """Mark the project as having opted into CataForge-managed docs.

    The orphan check only fires when ``docs/.doc-index.json`` exists; tests
    that want the check to run must declare that signal explicitly. Content
    is intentionally empty — the check rebuilds the orphan list from disk,
    not from the index payload.
    """
    (root / "docs").mkdir(exist_ok=True)
    (root / "docs" / ".doc-index.json").write_text(
        '{"version": "1", "documents": {}, "xref": {}}', encoding="utf-8"
    )


def test_doctor_flags_orphan_doc_missing_front_matter(
    tmp_path: Path, monkeypatch
) -> None:
    """A docs/*.md without YAML front matter must trip the index-completeness gate."""
    root = _scaffold(tmp_path)
    _empty_doc_index(root)
    (root / "docs" / "research").mkdir(parents=True)
    # No front matter at all — Bootstrap-style raw user input.
    (root / "docs" / "research" / "raw-requirements-v1.md").write_text(
        "# 原始需求清单\n\n第一段需求 ...\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(root)

    result = CliRunner().invoke(doctor_command, [])
    assert result.exit_code != 0, (
        "doctor must fail when docs/*.md cannot be ingested by the indexer"
    )
    assert "Docs index completeness:" in result.output
    assert "1 orphan document" in result.output
    assert "docs/research/raw-requirements-v1.md" in result.output


def test_doctor_passes_when_every_doc_has_front_matter(
    tmp_path: Path, monkeypatch
) -> None:
    root = _scaffold(tmp_path)
    _empty_doc_index(root)
    (root / "docs" / "prd").mkdir(parents=True)
    (root / "docs" / "prd" / "prd-foo-v1.md").write_text(
        '---\nid: "prd-foo-v1"\ndoc_type: prd\n---\n\n# PRD: Foo\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(root)

    result = CliRunner().invoke(doctor_command, [])
    section = result.output.split("Docs index completeness:", 1)[1].splitlines()[1]
    assert "0 orphan documents" in section, section


def test_doctor_orphan_check_skips_archive(
    tmp_path: Path, monkeypatch
) -> None:
    """Archived NAV-INDEX copies live in docs/.archive or .cataforge/.archive and
    must not be flagged — they are intentional snapshots without front matter."""
    root = _scaffold(tmp_path)
    _empty_doc_index(root)
    archive = root / "docs" / ".archive"
    archive.mkdir(parents=True)
    (archive / "old-nav-snapshot.md").write_text(
        "legacy snapshot, no front matter\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(root)

    result = CliRunner().invoke(doctor_command, [])
    section = result.output.split("Docs index completeness:", 1)[1].splitlines()[1]
    assert "0 orphan documents" in section, section


def test_doctor_orphan_check_skips_when_no_doc_index(
    tmp_path: Path, monkeypatch
) -> None:
    """Projects whose docs/ holds plain README-style content (no .doc-index.json)
    must not be lectured about missing front matter — they never opted in."""
    root = _scaffold(tmp_path)
    (root / "docs" / "architecture").mkdir(parents=True)
    (root / "docs" / "architecture" / "overview.md").write_text(
        "# Architecture overview\n\nPlain prose.\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(root)

    result = CliRunner().invoke(doctor_command, [])
    section = result.output.split("Docs index completeness:", 1)[1].splitlines()[1]
    assert "has not opted into" in section, section


def test_doctor_anti_rot_table_contains_expected_entries() -> None:
    """The deprecation registry must keep the four canonical entries we ship.

    If we ever rename/remove one of these, this test will force the author to
    confirm it is intentional rather than silently dropping CI coverage.
    """
    from cataforge.cli.doctor_cmd import _DEPRECATED_REFS

    names = {entry["name"] for entry in _DEPRECATED_REFS}
    assert names == {
        "load_section.py",
        "build_doc_index.py",
        "docs/NAV-INDEX.md",
        "docs/.nav/",
        "python .cataforge/scripts/framework/event_logger.py",
    }
    for entry in _DEPRECATED_REFS:
        assert entry["replacement"], entry
        assert entry["since"], entry


def test_doctor_flags_relative_event_logger_script_call(
    tmp_path: Path, monkeypatch
) -> None:
    """The old `python .cataforge/scripts/framework/event_logger.py` invocation
    breaks under monorepo subdirectory cwds. doctor must catch any prose that
    reintroduces it so we don't regress the v0.1.14 sweep."""
    root = _scaffold(tmp_path)
    skill_dir = root / ".cataforge" / "skills" / "demo"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "# Demo\n\n"
        "记录事件: `python .cataforge/scripts/framework/event_logger.py "
        "--event phase_start --phase x --detail y`\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(root)

    result = CliRunner().invoke(doctor_command, [])
    assert result.exit_code != 0
    assert "event_logger.py" in result.output
    assert "cataforge event log" in result.output
