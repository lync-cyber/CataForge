"""doctor must flag hooks.yaml scripts whose Python module is unimportable."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

from click.testing import CliRunner

from cataforge.cli.doctor_cmd import doctor_command


def _project(tmp_path: Path, hooks_yaml: str) -> Path:
    cf = tmp_path / ".cataforge"
    (cf / "hooks").mkdir(parents=True)
    (cf / "framework.json").write_text(
        json.dumps({
            "version": "0.1.0",
            "runtime_api_version": "1.0",
            "runtime": {"platform": "claude-code"},
        }),
        encoding="utf-8",
    )
    (cf / "hooks" / "hooks.yaml").write_text(hooks_yaml, encoding="utf-8")
    return tmp_path


def test_doctor_passes_when_all_declared_scripts_importable(
    tmp_path: Path, monkeypatch
) -> None:
    yaml = textwrap.dedent("""
        schema_version: 2
        hooks:
          PostToolUse:
            - matcher_capability: user_question
              script: detect_correction
              type: observe
    """)
    root = _project(tmp_path, yaml)
    monkeypatch.chdir(root)
    result = CliRunner().invoke(doctor_command, [])
    assert result.exit_code == 0, result.output
    assert "1/1 declared scripts importable" in result.output


def test_doctor_fails_on_missing_hook_module(tmp_path: Path, monkeypatch) -> None:
    yaml = textwrap.dedent("""
        schema_version: 2
        hooks:
          PostToolUse:
            - matcher_capability: user_question
              script: detect_correction
              type: observe
            - matcher_capability: agent_dispatch
              script: this_module_does_not_exist
              type: observe
    """)
    root = _project(tmp_path, yaml)
    monkeypatch.chdir(root)
    result = CliRunner().invoke(doctor_command, [])
    assert result.exit_code == 1, result.output
    assert "this_module_does_not_exist" in result.output
    assert "1/2 declared scripts importable" in result.output


def test_doctor_skips_custom_prefixed_scripts(tmp_path: Path, monkeypatch) -> None:
    yaml = textwrap.dedent("""
        schema_version: 2
        hooks:
          PostToolUse:
            - matcher_capability: user_question
              script: custom:my_project_hook
              type: observe
    """)
    root = _project(tmp_path, yaml)
    monkeypatch.chdir(root)
    result = CliRunner().invoke(doctor_command, [])
    assert result.exit_code == 0, result.output
    assert "(no built-in hook scripts declared)" in result.output


def test_doctor_reports_runtime_degradation(tmp_path: Path, monkeypatch) -> None:
    yaml = textwrap.dedent("""
        schema_version: 2
        hooks:
          PostToolUse:
            - matcher_capability: user_question
              script: detect_correction
              type: observe
    """)
    root = _project(tmp_path, yaml)
    monkeypatch.chdir(root)
    result = CliRunner().invoke(doctor_command, [])
    assert result.exit_code == 0, result.output
    assert (
        "Runtime degradation on claude-code" in result.output
        or "cannot load adapter for 'claude-code'" in result.output
    ), result.output
