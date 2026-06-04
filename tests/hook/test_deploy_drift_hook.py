"""SessionStart deploy_drift hook nudges (stderr-only) when a deploy is stale."""

from __future__ import annotations

from pathlib import Path

import pytest

from cataforge.core.paths import ProjectPaths
from cataforge.runtime.deploy.drift import compute_source_digest
from cataforge.runtime.deploy.manifest import DeployManifest, save_manifest
from cataforge.runtime.hook.scripts.deploy_drift import _warn_on_drift


def _seed(root: Path) -> None:
    cf = root / ".cataforge"
    (cf / "rules").mkdir(parents=True)
    (cf / "rules" / "COMMON-RULES.md").write_text("# common\n", encoding="utf-8")
    (cf / "framework.json").write_text('{"version": "0.8.0"}\n', encoding="utf-8")


def _baseline(root: Path, version: str) -> None:
    m = DeployManifest("claude-code")
    m.source_digest = compute_source_digest(ProjectPaths(root))
    m.package_version = version
    save_manifest(root, m)


def test_hook_silent_without_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _seed(tmp_path)
    monkeypatch.chdir(tmp_path)
    _warn_on_drift()
    assert capsys.readouterr().err == ""


def test_hook_silent_when_in_sync(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _seed(tmp_path)
    _baseline(tmp_path, "0.8.0")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("cataforge.__version__", "0.8.0", raising=False)
    _warn_on_drift()
    assert capsys.readouterr().err == ""


def test_hook_warns_on_source_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _seed(tmp_path)
    _baseline(tmp_path, "0.8.0")
    (tmp_path / ".cataforge" / "rules" / "COMMON-RULES.md").write_text(
        "# changed\n", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    _warn_on_drift()
    err = capsys.readouterr().err
    assert "cataforge" in err
    assert "deploy" in err


def test_hook_never_raises_without_cataforge_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Opening a session in a non-CataForge dir must not crash the hook."""
    monkeypatch.chdir(tmp_path)
    _warn_on_drift()  # best-effort: must return, never raise
