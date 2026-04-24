"""Tests for scaffold copy + merge behavior."""

from __future__ import annotations

import json
from pathlib import Path

from cataforge.core.scaffold import (
    BACKUPS_DIRNAME,
    copy_scaffold_to,
    create_backup,
    list_backups,
    restore_backup,
)


def test_copy_scaffold_fresh(tmp_path: Path) -> None:
    dest = tmp_path / ".cataforge"
    written, skipped, backup = copy_scaffold_to(dest, force=False)
    assert written, "scaffold should have produced some files"
    assert skipped == []
    assert backup is None, "fresh copy must not create a backup"
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


def test_force_copy_creates_backup_snapshot(tmp_path: Path) -> None:
    dest = tmp_path / ".cataforge"
    copy_scaffold_to(dest, force=False)

    target_agent = next((dest / "agents").rglob("AGENT.md"))
    target_agent.write_text("custom edit\n", encoding="utf-8")
    user_rel = target_agent.relative_to(dest).as_posix()

    _, _, backup = copy_scaffold_to(dest, force=True)
    assert backup is not None
    assert backup.is_dir()
    assert backup.parent.name == BACKUPS_DIRNAME
    # Snapshot captures pre-overwrite bytes.
    assert (backup / user_rel).read_text(encoding="utf-8") == "custom edit\n"
    # Live scaffold no longer has the user edit.
    assert "custom edit" not in target_agent.read_text(encoding="utf-8")


def test_fresh_install_does_not_backup(tmp_path: Path) -> None:
    dest = tmp_path / ".cataforge"
    _, _, backup = copy_scaffold_to(dest, force=True)
    assert backup is None


def test_create_and_restore_backup_roundtrip(tmp_path: Path) -> None:
    dest = tmp_path / ".cataforge"
    copy_scaffold_to(dest, force=False)

    target = next((dest / "agents").rglob("AGENT.md"))
    original = target.read_text(encoding="utf-8")
    target.write_text(original + "\n# v1\n", encoding="utf-8")
    snap_v1 = create_backup(dest, ts="20260424-010101")
    assert snap_v1 is not None

    target.write_text(original + "\n# v2\n", encoding="utf-8")
    snap_v2 = create_backup(dest, ts="20260424-020202")

    backups = list_backups(dest)
    assert [b.name for b in backups] == ["20260424-020202", "20260424-010101"]

    stash = restore_backup(dest, snap_v1)
    restored = target.read_text(encoding="utf-8")
    assert restored.endswith("# v1\n")
    # Stash captured the v2 state we rolled away from.
    assert (stash / target.relative_to(dest)).read_text(
        encoding="utf-8"
    ).endswith("# v2\n")
    # Earlier snapshots still listable (not wiped).
    assert snap_v2.is_dir()


def test_backups_dir_excluded_from_snapshot(tmp_path: Path) -> None:
    """Snapshots must not recursively include the `.backups/` tree."""
    dest = tmp_path / ".cataforge"
    copy_scaffold_to(dest, force=False)
    first = create_backup(dest, ts="first")
    assert first is not None

    second = create_backup(dest, ts="second")
    assert second is not None
    assert not (second / BACKUPS_DIRNAME).exists()
