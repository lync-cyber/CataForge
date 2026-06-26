"""Tests for scaffold copy + merge behavior."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cataforge.core.scaffold import (
    BACKUPS_DIRNAME,
    SIDECAR_SUFFIX,
    copy_scaffold_to,
    create_backup,
    iter_scaffold_files,
    list_backups,
    restore_backup,
)


def test_copy_scaffold_fresh(tmp_path: Path) -> None:
    dest = tmp_path / ".cataforge"
    result = copy_scaffold_to(dest, force=False)
    assert result.written, "scaffold should have produced some files"
    assert result.skipped == []
    assert result.protected == []
    assert result.backup is None, "fresh copy must not create a backup"
    assert (dest / "framework.json").is_file()
    # PROJECT-STATE.md is a packaged template only — never copied downstream.
    assert not (dest / "PROJECT-STATE.md").exists()


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


def test_copy_scaffold_preserves_project_languages_on_force(tmp_path: Path) -> None:
    """--force-scaffold must not reset user-declared project.languages."""
    dest = tmp_path / ".cataforge"
    copy_scaffold_to(dest, force=False)

    fw_path = dest / "framework.json"
    fw = json.loads(fw_path.read_text(encoding="utf-8"))
    fw.setdefault("project", {})["languages"] = ["python", "go"]
    fw_path.write_text(json.dumps(fw), encoding="utf-8")

    copy_scaffold_to(dest, force=True)

    refreshed = json.loads(fw_path.read_text(encoding="utf-8"))
    assert refreshed["project"]["languages"] == ["python", "go"]


def test_copy_scaffold_preserves_project_design_tool_on_force(tmp_path: Path) -> None:
    """--force-scaffold must not reset a user-enabled project.design_tool."""
    dest = tmp_path / ".cataforge"
    copy_scaffold_to(dest, force=False)

    fw_path = dest / "framework.json"
    fw = json.loads(fw_path.read_text(encoding="utf-8"))
    fw.setdefault("project", {})["design_tool"] = "penpot"
    fw_path.write_text(json.dumps(fw), encoding="utf-8")

    copy_scaffold_to(dest, force=True)

    refreshed = json.loads(fw_path.read_text(encoding="utf-8"))
    assert refreshed["project"]["design_tool"] == "penpot"


def test_copy_scaffold_preserves_context_overrides_on_force(tmp_path: Path) -> None:
    """--force-scaffold must preserve user-owned context routing config —
    kg_active_doc_types, kg_definition_authority and an explicit mode the
    upgrade must not stomp back to the scaffold default."""
    dest = tmp_path / ".cataforge"
    copy_scaffold_to(dest, force=False)

    fw_path = dest / "framework.json"
    fw = json.loads(fw_path.read_text(encoding="utf-8"))
    ctx = fw.setdefault("context", {})
    ctx["kg_active_doc_types"] = ["prd", "arch"]
    ctx["kg_definition_authority"] = {"UIComponent": ["ui-spec", "prd"]}
    ctx["mode"] = "graph"
    fw_path.write_text(json.dumps(fw), encoding="utf-8")

    copy_scaffold_to(dest, force=True)

    refreshed = json.loads(fw_path.read_text(encoding="utf-8"))
    rctx = refreshed["context"]
    assert rctx["kg_active_doc_types"] == ["prd", "arch"]
    assert rctx["kg_definition_authority"] == {"UIComponent": ["ui-spec", "prd"]}
    assert rctx["mode"] == "graph"


def test_merge_framework_json_migrates_legacy_strategy_authoring_to_mode(tmp_path: Path) -> None:
    """A project carrying the retired strategy × authoring axes is collapsed to
    a single context.mode on merge; the legacy keys are dropped so the doctor's
    validity gate stops failing, and the derived mode wins over the scaffold
    default."""
    from cataforge.core.scaffold import _merge_framework_json

    scaffold = json.dumps({"context": {"mode": "graph", "kg_active_doc_types": ["prd"]}}).encode()

    for strategy, authoring, expected in (
        ("doc-only", "md", "markdown"),
        ("kg-first", "md", "graph"),
        ("kg-first", "graph", "graph"),
    ):
        target = tmp_path / f"{strategy}-{authoring}.json"
        target.write_text(
            json.dumps(
                {
                    "context": {
                        "strategy": strategy,
                        "authoring": authoring,
                        "kg_active_doc_types": ["arch"],
                    }
                }
            ),
            encoding="utf-8",
        )

        merged = json.loads(_merge_framework_json(scaffold, target).decode("utf-8"))
        rctx = merged["context"]

        assert rctx["mode"] == expected, (strategy, authoring)
        assert "strategy" not in rctx
        assert "authoring" not in rctx
        # User routing config still wins over the scaffold default.
        assert rctx["kg_active_doc_types"] == ["arch"]


def test_force_refresh_prunes_obsolete_unmodified_files(tmp_path: Path) -> None:
    """A scaffold file recorded in the manifest but absent from the current
    bundle (removed upstream) is deleted on refresh when the user never
    touched it; its now-empty directory goes with it."""
    from cataforge.core.scaffold_backup import _sha256, _write_manifest, read_manifest

    dest = tmp_path / ".cataforge"
    copy_scaffold_to(dest, force=False)

    obsolete = dest / "skills" / "legacy-skill" / "SKILL.md"
    obsolete.parent.mkdir(parents=True)
    obsolete.write_bytes(b"legacy body")
    manifest = read_manifest(dest)
    manifest["skills/legacy-skill/SKILL.md"] = _sha256(b"legacy body")
    _write_manifest(dest, manifest)

    result = copy_scaffold_to(dest, force=True, backup=False)
    assert not obsolete.exists()
    assert not obsolete.parent.exists()
    assert any("legacy-skill" in str(p) for p in result.removed)
    # The pruned entry must not survive into the fresh manifest.
    assert "skills/legacy-skill/SKILL.md" not in read_manifest(dest)


def test_force_refresh_keeps_user_modified_obsolete_file(tmp_path: Path) -> None:
    from cataforge.core.scaffold_backup import _sha256, _write_manifest, read_manifest

    dest = tmp_path / ".cataforge"
    copy_scaffold_to(dest, force=False)

    obsolete = dest / "skills" / "legacy-skill" / "SKILL.md"
    obsolete.parent.mkdir(parents=True)
    obsolete.write_bytes(b"user edited body")
    manifest = read_manifest(dest)
    manifest["skills/legacy-skill/SKILL.md"] = _sha256(b"original body")
    _write_manifest(dest, manifest)

    result = copy_scaffold_to(dest, force=True, backup=False)
    assert obsolete.exists(), "user-modified obsolete file must be kept"
    assert all("legacy-skill" not in str(p) for p in result.removed)


def test_non_force_copy_never_prunes(tmp_path: Path) -> None:
    from cataforge.core.scaffold_backup import _sha256, _write_manifest, read_manifest

    dest = tmp_path / ".cataforge"
    copy_scaffold_to(dest, force=False)
    obsolete = dest / "skills" / "legacy-skill" / "SKILL.md"
    obsolete.parent.mkdir(parents=True)
    obsolete.write_bytes(b"legacy body")
    manifest = read_manifest(dest)
    manifest["skills/legacy-skill/SKILL.md"] = _sha256(b"legacy body")
    _write_manifest(dest, manifest)

    result = copy_scaffold_to(dest, force=False)
    assert obsolete.exists()
    assert result.removed == []


@pytest.mark.parametrize(
    ("rel", "blob"),
    [
        ("kg/store/CURRENT", b"MANIFEST-000152\n"),
        (".mcp-state/cache.json", b"{}"),
        ("overrides/agents/orchestrator/AGENT.md", b"custom override body"),
    ],
)
def test_force_refresh_never_prunes_runtime_state(tmp_path: Path, rel: str, blob: bytes) -> None:
    """A stale manifest written before these dirs were excluded from the
    scaffold must not let the obsolete-file prune delete live runtime state
    (KG store), local caches, or upgrade-immune override layers."""
    from cataforge.core.scaffold_backup import _sha256, _write_manifest, read_manifest

    dest = tmp_path / ".cataforge"
    copy_scaffold_to(dest, force=False)

    runtime_file = dest / rel
    runtime_file.parent.mkdir(parents=True, exist_ok=True)
    runtime_file.write_bytes(blob)
    manifest = read_manifest(dest)
    manifest[rel] = _sha256(blob)  # disk == recorded → meets prune's delete condition
    _write_manifest(dest, manifest)

    result = copy_scaffold_to(dest, force=True, backup=False)

    assert runtime_file.exists(), f"{rel} must survive a forced refresh"
    top = rel.split("/", 1)[0]
    assert all(top not in str(p) for p in result.removed)
    # The stale entry must not linger in the fresh manifest either.
    assert rel not in read_manifest(dest)


def test_scaffold_excludes_project_state_md(tmp_path: Path) -> None:
    """PROJECT-STATE.md is the instruction-file source template, packaged only;
    neither fresh copy nor force refresh emits it into the project."""
    dest = tmp_path / ".cataforge"
    copy_scaffold_to(dest, force=False)
    assert not (dest / "PROJECT-STATE.md").exists()

    copy_scaffold_to(dest, force=True)
    assert not (dest / "PROJECT-STATE.md").exists()


def test_scaffold_ships_cataforge_gitignore(tmp_path: Path) -> None:
    """A bundled .cataforge/.gitignore keeps downstream projects from committing
    framework-generated local state — deploy bookkeeping, rollback snapshots,
    and the binary RocksDB store (a disposable per-clone cache)."""
    rels = {rel for rel, _ in iter_scaffold_files()}
    assert ".gitignore" in rels

    dest = tmp_path / ".cataforge"
    copy_scaffold_to(dest, force=False)
    gitignore = dest / ".gitignore"
    assert gitignore.is_file()
    # Active rules = non-blank, non-comment lines.
    rules = {
        ln.strip()
        for ln in gitignore.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.lstrip().startswith("#")
    }
    assert ".backups/" in rules
    # The RocksDB store is a disposable cache — ignored wholesale (binary churn,
    # and a stale MANIFEST relative to the *.sst set yields an unopenable store).
    assert "kg/store/" in rules
    # Consolidated: no per-file store rule survives beside the directory rule.
    assert not any(r.startswith("kg/store/") and r != "kg/store/" for r in rules)
    # The durable text artifact — NQuads snapshots — stays trackable, not ignored.
    assert not any(r.startswith("kg/snapshots") for r in rules)


def test_cataforge_gitignore_store_ignored_snapshots_tracked(tmp_path: Path) -> None:
    """End-to-end: git ignores the whole kg/store/ tree yet tracks kg/snapshots/."""
    import subprocess

    dest = tmp_path / ".cataforge"
    copy_scaffold_to(dest, force=False)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)

    store = dest / "kg" / "store"
    store.mkdir(parents=True)
    for name in ("CURRENT", "MANIFEST-000005", "OPTIONS-000007", "000009.sst", "000008.log"):
        (store / name).write_bytes(b"x")
    snaps = dest / "kg" / "snapshots"
    snaps.mkdir(parents=True)
    (snaps / "20260101T000000Z.nq").write_bytes(b"x")
    (snaps / "20260101T000000Z.meta.json").write_text("{}", encoding="utf-8")

    def ignored(rel: str) -> bool:
        return subprocess.run(["git", "check-ignore", "-q", rel], cwd=tmp_path).returncode == 0

    assert ignored(".cataforge/kg/store/000009.sst")
    assert ignored(".cataforge/kg/store/MANIFEST-000005")
    assert ignored(".cataforge/kg/store/CURRENT")
    assert not ignored(".cataforge/kg/snapshots/20260101T000000Z.nq")
    assert not ignored(".cataforge/kg/snapshots/20260101T000000Z.meta.json")


def test_force_refresh_prunes_retired_skill_dir(tmp_path: Path) -> None:
    """A retired framework skill's source dir is removed on upgrade even when
    it is untracked and locally edited (which would otherwise protect it)."""
    dest = tmp_path / ".cataforge"
    copy_scaffold_to(dest, force=False)

    # Stale leftover from an old scaffold, never manifest-tracked, user-edited.
    stale = dest / "skills" / "doc-gen"
    stale.mkdir(parents=True)
    (stale / "SKILL.md").write_text("# doc-gen\n运行 cataforge docs index\n", encoding="utf-8")

    result = copy_scaffold_to(dest, force=True, backup=False)
    assert not stale.exists()
    assert any("doc-gen" in str(p) for p in result.removed)
    # A live skill dir is untouched.
    assert (dest / "skills" / "context").is_dir()


def test_scaffold_stamps_runtime_package_version(tmp_path: Path) -> None:
    """framework.json version must match the installed cataforge package."""
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


def test_force_copy_preserves_user_edits_with_sidecar(tmp_path: Path) -> None:
    """A forced refresh keeps user-modified files and writes the framework
    version beside them as ``*.cataforge-new`` instead of overwriting."""
    dest = tmp_path / ".cataforge"
    copy_scaffold_to(dest, force=False)

    target_agent = next((dest / "agents").rglob("AGENT.md"))
    target_agent.write_text("custom edit\n", encoding="utf-8")
    user_rel = target_agent.relative_to(dest).as_posix()

    result = copy_scaffold_to(dest, force=True)
    assert result.backup is not None
    assert result.backup.is_dir()
    assert result.backup.parent.name == BACKUPS_DIRNAME
    # Snapshot still captures pre-refresh bytes.
    assert (result.backup / user_rel).read_text(encoding="utf-8") == "custom edit\n"

    # User edit is preserved in place — not overwritten.
    assert target_agent.read_text(encoding="utf-8") == "custom edit\n"
    assert target_agent in result.protected

    # Framework version landed beside it for manual merge.
    sidecar = target_agent.with_name(target_agent.name + SIDECAR_SUFFIX)
    assert sidecar.is_file()
    assert "custom edit" not in sidecar.read_text(encoding="utf-8")

    # Only the edited file is protected — untouched files refresh silently.
    sidecars = [p for p in dest.rglob(f"*{SIDECAR_SUFFIX}")]
    assert sidecars == [sidecar]


def test_force_refresh_does_not_sidecar_clean_files(tmp_path: Path) -> None:
    """A second forced refresh with no local edits writes no sidecars."""
    dest = tmp_path / ".cataforge"
    copy_scaffold_to(dest, force=False)
    result = copy_scaffold_to(dest, force=True)
    assert result.protected == []
    assert list(dest.rglob(f"*{SIDECAR_SUFFIX}")) == []


def test_drift_file_stays_protected_across_repeated_refresh(tmp_path: Path) -> None:
    """A drift file (edited, no manifest baseline) is protected on every
    refresh — not seeded into the manifest and overwritten on the next pass."""
    from cataforge.core.scaffold import MANIFEST_REL

    dest = tmp_path / ".cataforge"
    copy_scaffold_to(dest, force=False)

    target = next((dest / "agents").rglob("AGENT.md"))
    target.write_text("# drifted\n", encoding="utf-8")
    # Drop the manifest so the edit has no recorded baseline → classified drift.
    (dest / MANIFEST_REL).unlink()

    first = copy_scaffold_to(dest, force=True, backup=False)
    assert target in first.protected
    assert target.read_text(encoding="utf-8") == "# drifted\n"

    second = copy_scaffold_to(dest, force=True, backup=False)
    assert target in second.protected
    assert target.read_text(encoding="utf-8") == "# drifted\n"


def test_fresh_install_does_not_backup(tmp_path: Path) -> None:
    dest = tmp_path / ".cataforge"
    assert copy_scaffold_to(dest, force=True).backup is None


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
    assert (stash / target.relative_to(dest)).read_text(encoding="utf-8").endswith("# v2\n")
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


def test_overrides_dir_excluded_from_scaffold() -> None:
    """Override layers are upgrade-immune — never bundled into the scaffold copy."""
    rels = [rel for rel, _ in iter_scaffold_files()]
    assert rels, "scaffold should yield files"
    assert not any(rel == "overrides" or rel.startswith("overrides/") for rel in rels)


def test_overrides_dir_not_copied_downstream(tmp_path: Path) -> None:
    """A fresh scaffold copy must not materialise the override skeleton."""
    dest = tmp_path / ".cataforge"
    copy_scaffold_to(dest, force=False)
    assert not (dest / "overrides").exists()
