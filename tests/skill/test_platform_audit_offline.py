"""Tests for the offline platform-audit builtin.

Covers the PR-gate contract: a clean repo exits 0 (consistency WARNs are
advisory, not blocking), a schema-required-key miss or unloadable profile exits
1, and unknown args exit 2.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import yaml

from cataforge.adapter.platform.registry import clear_cache
from cataforge.runtime.skill.builtins.platform_audit.offline import (
    check_profile_schema,
    main,
    run_offline_audit,
)

REAL_PLATFORMS = Path(__file__).resolve().parents[2] / ".cataforge" / "platforms"


def test_check_profile_schema_flags_missing_required_key(tmp_path: Path) -> None:
    shutil.copyfile(REAL_PLATFORMS / "_schema.yaml", tmp_path / "_schema.yaml")
    prof_dir = tmp_path / "codex"
    prof_dir.mkdir()
    (prof_dir / "profile.yaml").write_text(
        yaml.dump({"platform_id": "codex", "tool_map": {}}), encoding="utf-8"
    )
    issues = check_profile_schema(tmp_path)
    assert any("FAIL" in i and "codex" in i and "missing required keys" in i for i in issues)


def test_check_profile_schema_clean_on_real_profiles() -> None:
    assert check_profile_schema(REAL_PLATFORMS) == []


def test_run_offline_audit_clean_exits_zero() -> None:
    clear_cache()
    assert run_offline_audit(REAL_PLATFORMS) == 0


def test_run_offline_audit_blocks_on_schema_fail(tmp_path: Path) -> None:
    platforms = tmp_path / "platforms"
    shutil.copytree(REAL_PLATFORMS, platforms)
    profile_path = platforms / "codex" / "profile.yaml"
    data = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    del data["dispatch"]  # a schema-required key
    profile_path.write_text(yaml.dump(data), encoding="utf-8")

    clear_cache()
    try:
        assert run_offline_audit(platforms) == 1
    finally:
        clear_cache()


def test_main_rejects_unknown_args() -> None:
    assert main(["--bogus"]) == 2
