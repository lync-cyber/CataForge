"""Self-test for ``scripts/checks/check_migration_notes_version.py``.

The guard keeps ``.cataforge/skills/framework-update/references/
version-migration.md`` rolling with releases: the newest CHANGELOG
version must have a matching section, and the notes may not name a
version the CHANGELOG does not know.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "checks" / "check_migration_notes_version.py"

CHANGELOG_BODY = """# Changelog

## [0.16.0] — 2026-07-05

### Added

- something new

## [0.15.0] — 2026-06-28

### Fixed

- something fixed

## [0.14.0] — 2026-06-23

### Added

- older stuff
"""


def _run(tmp_root: Path) -> subprocess.CompletedProcess[str]:
    """Run the guard with CHANGELOG / MIGRATION_NOTES pointed at tmp files."""
    runner = (
        "import sys, pathlib;"
        "import importlib.util as iu;"
        f"spec = iu.spec_from_file_location('guard', {str(SCRIPT)!r});"
        "mod = iu.module_from_spec(spec); spec.loader.exec_module(mod);"
        f"mod.CHANGELOG = pathlib.Path({str(tmp_root / 'CHANGELOG.md')!r});"
        f"mod.MIGRATION_NOTES = pathlib.Path({str(tmp_root / 'version-migration.md')!r});"
        "sys.exit(mod.main())"
    )
    return subprocess.run(
        [sys.executable, "-c", runner],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _write(tmp_path: Path, changelog: str | None, notes: str | None) -> None:
    if changelog is not None:
        (tmp_path / "CHANGELOG.md").write_text(changelog, encoding="utf-8")
    if notes is not None:
        (tmp_path / "version-migration.md").write_text(notes, encoding="utf-8")


class TestMigrationNotesVersionGuard:
    def test_passes_when_latest_version_present(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            CHANGELOG_BODY,
            "# notes\n\n## [0.16.0] — 2026-07-05\n\n- x\n\n## [0.15.0] — 2026-06-28\n\n- y\n",
        )
        result = _run(tmp_path)
        assert result.returncode == 0, result.stderr + result.stdout

    def test_rolling_window_subset_passes(self, tmp_path: Path) -> None:
        """Older CHANGELOG versions may be dropped from the notes — only
        the newest release is mandatory."""
        _write(tmp_path, CHANGELOG_BODY, "# notes\n\n## [0.16.0] — 2026-07-05\n\n- x\n")
        result = _run(tmp_path)
        assert result.returncode == 0, result.stderr + result.stdout

    def test_fails_when_latest_version_missing_from_notes(self, tmp_path: Path) -> None:
        _write(tmp_path, CHANGELOG_BODY, "# notes\n\n## [0.15.0] — 2026-06-28\n\n- y\n")
        result = _run(tmp_path)
        assert result.returncode == 1
        assert "0.16.0" in result.stderr

    def test_fails_when_notes_name_unknown_version(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            CHANGELOG_BODY,
            "# notes\n\n## [0.16.0] — 2026-07-05\n\n- x\n\n## [9.9.9] — 2026-01-01\n\n- ghost\n",
        )
        result = _run(tmp_path)
        assert result.returncode == 1
        assert "9.9.9" in result.stderr

    def test_fails_when_notes_file_missing(self, tmp_path: Path) -> None:
        _write(tmp_path, CHANGELOG_BODY, None)
        result = _run(tmp_path)
        assert result.returncode == 1
        assert "version-migration" in result.stderr

    def test_fails_when_changelog_missing(self, tmp_path: Path) -> None:
        _write(tmp_path, None, "# notes\n\n## [0.16.0] — 2026-07-05\n\n- x\n")
        result = _run(tmp_path)
        assert result.returncode == 1

    def test_real_repo_files_pass(self) -> None:
        """The guard must hold on the actual repo state."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT)],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        assert result.returncode == 0, result.stderr + result.stdout
