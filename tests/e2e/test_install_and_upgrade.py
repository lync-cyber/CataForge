"""End-to-end: fresh install + in-place upgrade with user edits preserved/overwritten.

Exercises the complete user journey against a *real* wheel installed into
a venv via subprocess (not in-process CliRunner):

1. Build the wheel once per session (``built_wheel`` fixture).
2. Create one venv per session and ``pip install`` the wheel
   (``cataforge_venv`` fixture).
3. Each test runs ``cataforge setup`` in its own fresh ``tmp_path``
   project directory, mutates it if needed, and inspects the result.

We intentionally do *not* ``pip install --force-reinstall`` between the
"setup" and "upgrade" steps within a test. The reinstall would gesture
at a user's ``pip install --upgrade`` action, but functionally
``cataforge upgrade apply`` reads the scaffold from the *currently
installed* package at invocation time — whether the package was just
installed or installed an hour ago makes no difference. Skipping the
reinstall keeps each test at ~5-10s of CLI work instead of ~30s.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tests.e2e.conftest import run_cataforge

pytestmark = pytest.mark.slow


@pytest.fixture
def fresh_project(tmp_path: Path, cataforge_venv: Path) -> Path:
    """A clean project directory, sibling-isolated from other tests' state."""
    project = tmp_path / "proj"
    project.mkdir()
    return project


def test_fresh_install_writes_scaffold_manifest_and_ide_artifacts(
    fresh_project: Path, cataforge_venv: Path
) -> None:
    """0→1: `cataforge setup --platform X --deploy` in a fresh project."""
    result = run_cataforge(
        cataforge_venv, "setup", "--platform", "claude-code", "--deploy",
        cwd=fresh_project,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    cataforge_dir = fresh_project / ".cataforge"
    assert (cataforge_dir / "framework.json").is_file()
    assert (cataforge_dir / "hooks" / "hooks.yaml").is_file()
    assert (cataforge_dir / ".scaffold-manifest.json").is_file()

    # IDE artifacts from --deploy
    assert (fresh_project / "CLAUDE.md").is_file()
    assert (fresh_project / ".claude" / "settings.json").is_file()

    # Manifest shape: versioned, every entry is a sha256 hex digest
    manifest = json.loads(
        (cataforge_dir / ".scaffold-manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["manifest_version"] == 1
    assert manifest["package_version"]  # non-empty
    assert len(manifest["files"]) > 50, (
        f"expected >50 tracked files, got {len(manifest['files'])}"
    )
    for rel, digest in manifest["files"].items():
        assert len(digest) == 64, f"{rel}: digest is not sha256 hex ({digest!r})"
        assert all(c in "0123456789abcdef" for c in digest), f"{rel}: non-hex digest"


def test_upgrade_apply_dry_run_flags_user_modified_files(
    fresh_project: Path, cataforge_venv: Path
) -> None:
    """User-modified scaffold files must surface as ``[user-modified]``
    and framework.json / PROJECT-STATE.md as ``[preserved]``."""
    run_cataforge(
        cataforge_venv, "setup", "--platform", "claude-code", cwd=fresh_project
    )

    cataforge_dir = fresh_project / ".cataforge"
    agents_dir = cataforge_dir / "agents"
    agent_files = sorted(agents_dir.rglob("AGENT.md"))
    assert agent_files, "bundled scaffold should include at least one agent"
    target_agent = agent_files[0]
    target_agent.write_text(
        target_agent.read_text(encoding="utf-8") + "\n# user custom section\n",
        encoding="utf-8",
    )
    agent_rel = target_agent.relative_to(cataforge_dir).as_posix()

    result = run_cataforge(
        cataforge_venv, "upgrade", "apply", "--dry-run", cwd=fresh_project
    )
    assert result.returncode == 0, result.stdout + result.stderr
    out = result.stdout

    # Overall shape
    assert "Would refresh scaffold at" in out
    assert "Summary:" in out

    # The edited agent file lands in the [user-modified] bucket.
    user_modified_lines = [ln for ln in out.splitlines() if "[user-modified]" in ln]
    assert any(agent_rel in ln for ln in user_modified_lines), (
        f"expected {agent_rel} flagged [user-modified]; actual user-modified lines:\n"
        + "\n".join(user_modified_lines)
        + "\n\nFull output:\n"
        + out
    )

    # framework.json + PROJECT-STATE.md are merge-handled → always [preserved].
    preserved_lines = [ln for ln in out.splitlines() if "[preserved]" in ln]
    assert any("framework.json" in ln for ln in preserved_lines), out
    assert any("PROJECT-STATE.md" in ln for ln in preserved_lines), out

    # The yellow WARNING fires on stderr when any file is user-modified/drift.
    assert "WARNING" in result.stderr or "WARNING" in out, (result.stdout, result.stderr)


def test_upgrade_apply_overwrites_user_mods_but_preserves_runtime_platform(
    fresh_project: Path, cataforge_venv: Path
) -> None:
    """Locks in the current contract:

    * Arbitrary scaffold files under ``.cataforge/`` get overwritten on
      ``upgrade apply`` — this is intentional; users must put customisations
      in ``.cataforge/plugins/`` or outside the scaffold.
    * ``framework.json.runtime.platform`` is preserved (field-level merge).
    * The scaffold manifest is rewritten to reflect post-apply hashes.
    """
    run_cataforge(
        cataforge_venv, "setup", "--platform", "claude-code", cwd=fresh_project
    )

    cataforge_dir = fresh_project / ".cataforge"
    agent_files = sorted((cataforge_dir / "agents").rglob("AGENT.md"))
    target_agent = agent_files[0]
    target_agent.write_text(
        target_agent.read_text(encoding="utf-8") + "\n# user custom section\n",
        encoding="utf-8",
    )

    fw_path = cataforge_dir / "framework.json"
    fw = json.loads(fw_path.read_text(encoding="utf-8"))
    assert fw["runtime"]["platform"] == "claude-code"
    fw["runtime"]["platform"] = "cursor"
    fw_path.write_text(json.dumps(fw, indent=2), encoding="utf-8")

    result = run_cataforge(
        cataforge_venv, "upgrade", "apply", cwd=fresh_project
    )
    assert result.returncode == 0, result.stdout + result.stderr

    # Contract: user edits to scaffold files are dropped.
    assert "# user custom section" not in target_agent.read_text(encoding="utf-8")

    # Contract: runtime.platform is preserved across refresh.
    fw_after = json.loads(fw_path.read_text(encoding="utf-8"))
    assert fw_after["runtime"]["platform"] == "cursor"

    # Manifest rewritten: hash for the re-written agent file now matches the
    # bundled scaffold, so classify_scaffold_files would report `unchanged`.
    manifest = json.loads(
        (cataforge_dir / ".scaffold-manifest.json").read_text(encoding="utf-8")
    )
    agent_rel = target_agent.relative_to(cataforge_dir).as_posix()
    disk_hash = hashlib.sha256(target_agent.read_bytes()).hexdigest()
    assert manifest["files"][agent_rel] == disk_hash


def test_upgrade_check_reports_up_to_date_after_setup(
    fresh_project: Path, cataforge_venv: Path
) -> None:
    """Immediately after ``setup``, ``upgrade check`` must report parity."""
    run_cataforge(
        cataforge_venv, "setup", "--platform", "claude-code", cwd=fresh_project
    )

    result = run_cataforge(
        cataforge_venv, "upgrade", "check", cwd=fresh_project
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Scaffold is up to date" in result.stdout, result.stdout
