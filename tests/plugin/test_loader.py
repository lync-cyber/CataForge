"""PluginLoader discovery tests."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from cataforge.plugin.loader import PluginLoader


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / ".cataforge").mkdir()
    return tmp_path


def _write_manifest(project: Path, plugin_id: str, **overrides) -> Path:
    pdir = project / ".cataforge" / "plugins" / plugin_id
    pdir.mkdir(parents=True)
    data = {
        "id": plugin_id,
        "name": overrides.pop("name", plugin_id),
        "version": "0.1.0",
        "description": "test plugin",
        "provides": {"skills": ["demo"]},
        "requires": {},
    }
    data.update(overrides)
    path = pdir / "cataforge-plugin.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


class TestPluginDiscovery:
    def test_empty_project_yields_nothing(self, project: Path) -> None:
        assert PluginLoader(project).discover() == []

    def test_project_plugin_discovered(self, project: Path) -> None:
        _write_manifest(project, "alpha")
        found = PluginLoader(project).discover()
        assert [p.id for p in found] == ["alpha"]
        assert found[0].provides_skills == ["demo"]

    def test_multiple_plugins_sorted(self, project: Path) -> None:
        _write_manifest(project, "beta")
        _write_manifest(project, "alpha")
        ids = [p.id for p in PluginLoader(project).discover()]
        assert ids == ["alpha", "beta"]

    def test_invalid_manifest_skipped(self, project: Path) -> None:
        bad_dir = project / ".cataforge" / "plugins" / "broken"
        bad_dir.mkdir(parents=True)
        (bad_dir / "cataforge-plugin.yaml").write_text(
            "not a mapping\n", encoding="utf-8"
        )
        _write_manifest(project, "good")
        ids = [p.id for p in PluginLoader(project).discover()]
        assert ids == ["good"]

    def test_missing_id_field_skipped(self, project: Path) -> None:
        bad_dir = project / ".cataforge" / "plugins" / "no-id"
        bad_dir.mkdir(parents=True)
        (bad_dir / "cataforge-plugin.yaml").write_text(
            "name: missing-id\nversion: 0.1.0\n", encoding="utf-8"
        )
        assert PluginLoader(project).discover() == []

    def test_manifest_parses_full_spec(self, project: Path) -> None:
        _write_manifest(
            project,
            "full",
            provides={
                "skills": ["s1"],
                "mcp_servers": ["srv1"],
                "agents": ["a1"],
                "hooks": [{"event": "PreToolUse", "script": "x.py"}],
            },
            requires={"commands": ["git"], "pip": ["httpx"], "npm": []},
        )
        [p] = PluginLoader(project).discover()
        assert p.provides_skills == ["s1"]
        assert p.provides_mcp_servers == ["srv1"]
        assert p.provides_agents == ["a1"]
        assert p.requires_commands == ["git"]
        assert p.requires_pip == ["httpx"]
