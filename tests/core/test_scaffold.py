"""Tests for scaffold copy + merge behavior."""

from __future__ import annotations

import json
from pathlib import Path

from cataforge.core.scaffold import copy_scaffold_to


def test_copy_scaffold_fresh(tmp_path: Path) -> None:
    dest = tmp_path / ".cataforge"
    written, skipped = copy_scaffold_to(dest, force=False)
    assert written, "scaffold should have produced some files"
    assert skipped == []
    assert (dest / "framework.json").is_file()
    assert (dest / "PROJECT-STATE.md").is_file()


def test_copy_scaffold_preserves_runtime_platform_on_force(tmp_path: Path) -> None:
    """--force-scaffold must not clobber user-chosen runtime.platform."""
    dest = tmp_path / ".cataforge"
    copy_scaffold_to(dest, force=False)

    # Simulate user flipping platform after setup.
    fw_path = dest / "framework.json"
    fw = json.loads(fw_path.read_text(encoding="utf-8"))
    fw["runtime"]["platform"] = "cursor"
    fw["upgrade"].setdefault("state", {})["last_version"] = "0.0.9"
    fw_path.write_text(json.dumps(fw), encoding="utf-8")

    # Force refresh.
    copy_scaffold_to(dest, force=True)

    refreshed = json.loads(fw_path.read_text(encoding="utf-8"))
    assert refreshed["runtime"]["platform"] == "cursor"
    assert refreshed["upgrade"]["state"]["last_version"] == "0.0.9"
    # Scaffold-owned fields should still be refreshed.
    assert "constants" in refreshed
    assert "migration_checks" in refreshed


def test_copy_scaffold_preserves_project_state_md_on_force(tmp_path: Path) -> None:
    dest = tmp_path / ".cataforge"
    copy_scaffold_to(dest, force=False)

    ps = dest / "PROJECT-STATE.md"
    ps.write_text("# user edits\n", encoding="utf-8")

    copy_scaffold_to(dest, force=True)
    assert ps.read_text(encoding="utf-8") == "# user edits\n"


def test_scaffold_stamps_runtime_package_version(tmp_path: Path) -> None:
    """framework.json version must match the installed cataforge package.

    Regression guard for upgrade convergence: before this fix the scaffold
    template shipped a hard-coded "0.1.0" that would never match a newer
    installed wheel, so ``cataforge upgrade check`` reported "differs" even
    immediately after ``upgrade apply``.
    """
    from cataforge import __version__

    dest = tmp_path / ".cataforge"
    copy_scaffold_to(dest, force=False)
    fresh = json.loads((dest / "framework.json").read_text(encoding="utf-8"))
    assert fresh["version"] == __version__

    # Simulate an older scaffold on disk, then force-refresh.
    fw_path = dest / "framework.json"
    stale = json.loads(fw_path.read_text(encoding="utf-8"))
    stale["version"] = "0.0.1"
    fw_path.write_text(json.dumps(stale), encoding="utf-8")

    copy_scaffold_to(dest, force=True)
    refreshed = json.loads(fw_path.read_text(encoding="utf-8"))
    assert refreshed["version"] == __version__
