"""End-to-end: fresh install + in-place upgrade with user edits preserved/overwritten.

Exercises the complete user journey:

1. Build a wheel from the current tree.
2. Create an isolated venv and ``pip install`` the wheel.
3. Run ``cataforge setup --platform claude-code --deploy`` in a fresh
   project directory — verifies the 0→1 path.
4. Inspect the scaffold manifest written by ``copy_scaffold_to``.
5. Simulate user edits: mutate an agent file and patch
   ``framework.json`` runtime.platform.
6. Re-install the same wheel (simulating ``pip install --upgrade``).
7. Run ``upgrade apply --dry-run`` and assert the per-file status tags
   (``[user-modified]`` / ``[preserved]``) land on the right paths.
8. Run ``upgrade apply`` and confirm the contract:
   * user-modified scaffold files get overwritten (current design)
   * ``runtime.platform`` is preserved via field-level merge
   * manifest is rewritten with the new hashes
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.e2e.conftest import make_venv, pip_install, run_cataforge

pytestmark = pytest.mark.slow


def test_fresh_install_writes_scaffold_manifest_and_ide_artifacts(
    tmp_path: Path, built_wheel: Path
) -> None:
    """0→1: `pip install <wheel> && cataforge setup --platform X --deploy`."""
    py = make_venv(tmp_path / "venv")
    pip_install(py, str(built_wheel))

    project = tmp_path / "proj"
    project.mkdir()

    result = run_cataforge(py, "setup", "--platform", "claude-code", "--deploy", cwd=project)
    assert result.returncode == 0, result.stdout + result.stderr

    cataforge_dir = project / ".cataforge"
    assert (cataforge_dir / "framework.json").is_file()
    assert (cataforge_dir / "hooks" / "hooks.yaml").is_file()
    assert (cataforge_dir / ".scaffold-manifest.json").is_file()

    # IDE artifacts from --deploy
    assert (project / "CLAUDE.md").is_file()
    assert (project / ".claude" / "settings.json").is_file()

    # Manifest shape: versioned, every entry is a sha256 hex digest
    manifest = json.loads((cataforge_dir / ".scaffold-manifest.json").read_text(encoding="utf-8"))
    assert manifest["manifest_version"] == 1
    assert manifest["package_version"]  # non-empty
    assert len(manifest["files"]) > 50, f"expected >50 tracked files, got {len(manifest['files'])}"
    for rel, digest in manifest["files"].items():
        assert len(digest) == 64, f"{rel}: digest is not sha256 hex ({digest!r})"
        assert all(c in "0123456789abcdef" for c in digest), f"{rel}: non-hex digest"


def test_upgrade_apply_dry_run_flags_user_modified_files(
    tmp_path: Path, built_wheel: Path
) -> None:
    """User-modified scaffold files must surface as ``[user-modified]``
    and framework.json / PROJECT-STATE.md as ``[preserved]``."""
    py = make_venv(tmp_path / "venv")
    pip_install(py, str(built_wheel))

    project = tmp_path / "proj"
    project.mkdir()
    run_cataforge(py, "setup", "--platform", "claude-code", cwd=project)

    cataforge_dir = project / ".cataforge"

    # User edits an agent file — pick the first AGENT.md that exists.
    agents_dir = cataforge_dir / "agents"
    agent_files = sorted(agents_dir.rglob("AGENT.md"))
    assert agent_files, "bundled scaffold should include at least one agent"
    target_agent = agent_files[0]
    original = target_agent.read_text(encoding="utf-8")
    target_agent.write_text(original + "\n# user custom section\n", encoding="utf-8")
    agent_rel = target_agent.relative_to(cataforge_dir).as_posix()

    # Re-install to simulate `pip install --upgrade cataforge`.
    pip_install(py, "--force-reinstall", str(built_wheel))

    result = run_cataforge(py, "upgrade", "apply", "--dry-run", cwd=project)
    assert result.returncode == 0, result.stdout + result.stderr
    out = result.stdout

    # Overall shape
    assert "Would refresh scaffold at" in out
    assert "Summary:" in out

    # The edited agent file must land in the [user-modified] bucket.
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
    tmp_path: Path, built_wheel: Path
) -> None:
    """Locks in the current contract:

    * Arbitrary scaffold files under ``.cataforge/`` get overwritten on
      ``upgrade apply`` — this is intentional; users must put customisations
      in ``.cataforge/plugins/`` or outside the scaffold.
    * ``framework.json.runtime.platform`` is preserved (field-level merge).
    * The scaffold manifest is rewritten to reflect post-apply hashes.
    """
    py = make_venv(tmp_path / "venv")
    pip_install(py, str(built_wheel))

    project = tmp_path / "proj"
    project.mkdir()
    run_cataforge(py, "setup", "--platform", "claude-code", cwd=project)

    cataforge_dir = project / ".cataforge"
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

    pip_install(py, "--force-reinstall", str(built_wheel))

    result = run_cataforge(py, "upgrade", "apply", cwd=project)
    assert result.returncode == 0, result.stdout + result.stderr

    # Contract: user edits to scaffold files are dropped.
    assert "# user custom section" not in target_agent.read_text(encoding="utf-8")

    # Contract: runtime.platform is preserved across refresh.
    fw_after = json.loads(fw_path.read_text(encoding="utf-8"))
    assert fw_after["runtime"]["platform"] == "cursor"

    # Manifest rewritten: hash for the re-written agent file now matches the
    # bundled scaffold, so classify_scaffold_files would report `unchanged`.
    manifest = json.loads((cataforge_dir / ".scaffold-manifest.json").read_text(encoding="utf-8"))
    agent_rel = target_agent.relative_to(cataforge_dir).as_posix()
    import hashlib

    disk_hash = hashlib.sha256(target_agent.read_bytes()).hexdigest()
    assert manifest["files"][agent_rel] == disk_hash


def test_upgrade_check_reports_up_to_date_after_setup(
    tmp_path: Path, built_wheel: Path
) -> None:
    """Immediately after ``setup``, ``upgrade check`` must report parity."""
    py = make_venv(tmp_path / "venv")
    pip_install(py, str(built_wheel))

    project = tmp_path / "proj"
    project.mkdir()
    run_cataforge(py, "setup", "--platform", "claude-code", cwd=project)

    result = run_cataforge(py, "upgrade", "check", cwd=project)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Scaffold is up to date" in result.stdout, result.stdout
