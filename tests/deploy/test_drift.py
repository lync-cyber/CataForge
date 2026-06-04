"""Deploy drift detection: source-digest + package-version baselines."""

from __future__ import annotations

from pathlib import Path

from cataforge.core.paths import ProjectPaths
from cataforge.runtime.deploy.drift import (
    compute_source_digest,
    detect_drift,
    drift_hint_lines,
)
from cataforge.runtime.deploy.manifest import DeployManifest, save_manifest


def _seed_source(root: Path) -> None:
    cf = root / ".cataforge"
    (cf / "agents" / "architect").mkdir(parents=True)
    (cf / "agents" / "architect" / "AGENT.md").write_text("# architect\n", encoding="utf-8")
    (cf / "skills" / "context").mkdir(parents=True)
    (cf / "skills" / "context" / "SKILL.md").write_text("# context\n", encoding="utf-8")
    (cf / "framework.json").write_text('{"version": "0.8.0"}\n', encoding="utf-8")


class TestComputeSourceDigest:
    def test_deterministic_same_source_same_digest(self, tmp_path: Path) -> None:
        _seed_source(tmp_path)
        paths = ProjectPaths(tmp_path)
        assert compute_source_digest(paths) == compute_source_digest(paths)

    def test_changing_a_source_file_changes_digest(self, tmp_path: Path) -> None:
        _seed_source(tmp_path)
        paths = ProjectPaths(tmp_path)
        before = compute_source_digest(paths)
        (tmp_path / ".cataforge" / "agents" / "architect" / "AGENT.md").write_text(
            "# changed\n", encoding="utf-8"
        )
        assert compute_source_digest(paths) != before

    def test_adding_a_source_file_changes_digest(self, tmp_path: Path) -> None:
        _seed_source(tmp_path)
        paths = ProjectPaths(tmp_path)
        before = compute_source_digest(paths)
        rules = tmp_path / ".cataforge" / "agents" / "architect" / "rules"
        rules.mkdir()
        (rules / "lang-python.md").write_text("py\n", encoding="utf-8")
        assert compute_source_digest(paths) != before

    def test_state_files_excluded_from_digest(self, tmp_path: Path) -> None:
        """Framework-written state must NOT shift the digest, else every
        deploy would self-trigger drift."""
        _seed_source(tmp_path)
        paths = ProjectPaths(tmp_path)
        before = compute_source_digest(paths)
        cf = tmp_path / ".cataforge"
        (cf / ".deploy-state").write_text('{"platform":"claude-code"}', encoding="utf-8")
        (cf / ".deploy-manifest.json").write_text("{}", encoding="utf-8")
        (cf / "kg").mkdir()
        (cf / "kg" / "store").write_text("binary", encoding="utf-8")
        (cf / "agents" / "architect" / "__pycache__").mkdir()
        (cf / "agents" / "architect" / "__pycache__" / "x.pyc").write_text("x", encoding="utf-8")
        assert compute_source_digest(paths) == before


class TestDetectDrift:
    def _deploy_baseline(self, root: Path, paths: ProjectPaths, version: str) -> None:
        m = DeployManifest("claude-code")
        m.source_digest = compute_source_digest(paths)
        m.package_version = version
        save_manifest(root, m)

    def test_no_manifest_means_not_deployed_no_drift(self, tmp_path: Path) -> None:
        _seed_source(tmp_path)
        report = detect_drift(ProjectPaths(tmp_path), current_version="0.8.0")
        assert report.deployed is False
        assert report.source_drift is False
        assert report.version_drift is False
        assert report.any_drift is False

    def test_matching_baseline_no_drift(self, tmp_path: Path) -> None:
        _seed_source(tmp_path)
        paths = ProjectPaths(tmp_path)
        self._deploy_baseline(tmp_path, paths, "0.8.0")
        report = detect_drift(paths, current_version="0.8.0")
        assert report.deployed is True
        assert report.any_drift is False

    def test_source_changed_after_deploy_is_drift(self, tmp_path: Path) -> None:
        _seed_source(tmp_path)
        paths = ProjectPaths(tmp_path)
        self._deploy_baseline(tmp_path, paths, "0.8.0")
        (tmp_path / ".cataforge" / "framework.json").write_text(
            '{"version":"0.8.0","x":1}\n', encoding="utf-8"
        )
        report = detect_drift(paths, current_version="0.8.0")
        assert report.source_drift is True
        assert report.version_drift is False

    def test_package_upgraded_after_deploy_is_version_drift(self, tmp_path: Path) -> None:
        _seed_source(tmp_path)
        paths = ProjectPaths(tmp_path)
        self._deploy_baseline(tmp_path, paths, "0.8.0")
        report = detect_drift(paths, current_version="0.9.0")
        assert report.version_drift is True
        assert report.source_drift is False
        assert report.prior_version == "0.8.0"
        assert report.current_version == "0.9.0"


class TestDriftHintLines:
    def test_source_drift_hint_points_at_deploy(self, tmp_path: Path) -> None:
        report = detect_drift(ProjectPaths(tmp_path), current_version="0.8.0")
        # No baseline → no hints.
        assert drift_hint_lines(report) == []

    def test_version_drift_hint_mentions_versions(self, tmp_path: Path) -> None:
        _seed_source(tmp_path)
        paths = ProjectPaths(tmp_path)
        m = DeployManifest("claude-code")
        m.source_digest = compute_source_digest(paths)
        m.package_version = "0.8.0"
        save_manifest(tmp_path, m)
        lines = drift_hint_lines(detect_drift(paths, current_version="0.9.0"))
        assert any("0.8.0" in ln and "0.9.0" in ln for ln in lines)
        assert any("cataforge deploy" in ln for ln in lines)
