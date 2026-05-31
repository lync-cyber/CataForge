"""Plugin contributions consumed by loaders / resolver / MCP / hooks (P3)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from cataforge.core.paths import ProjectPaths
from cataforge.runtime.plugin.loader import PluginLoader


def _make_plugin(
    project: Path,
    plugin_id: str,
    *,
    skills: tuple[str, ...] = (),
    agents: tuple[str, ...] = (),
    mcp: tuple[str, ...] = (),
    hooks: tuple[dict, ...] = (),
) -> Path:
    pdir = project / ".cataforge" / "plugins" / plugin_id
    pdir.mkdir(parents=True)
    provides: dict = {}
    if skills:
        provides["skills"] = list(skills)
    if agents:
        provides["agents"] = list(agents)
    if mcp:
        provides["mcp_servers"] = list(mcp)
    if hooks:
        provides["hooks"] = list(hooks)
    (pdir / "cataforge-plugin.yaml").write_text(
        yaml.safe_dump({"id": plugin_id, "provides": provides}), encoding="utf-8"
    )
    for sid in skills:
        sd = pdir / "skills" / sid
        sd.mkdir(parents=True)
        (sd / "SKILL.md").write_text(
            f"---\nname: {sid}\ndescription: from {plugin_id}\n---\nbody\n",
            encoding="utf-8",
        )
    for aid in agents:
        ad = pdir / "agents" / aid
        ad.mkdir(parents=True)
        (ad / "AGENT.md").write_text(
            f"---\nname: {aid}\n---\n\n# Role\n\n## Identity\n- plugin agent {aid}\n",
            encoding="utf-8",
        )
    for mid in mcp:
        md = pdir / "mcp"
        md.mkdir(parents=True, exist_ok=True)
        (md / f"{mid}.yaml").write_text(
            yaml.safe_dump({"id": mid, "command": "node", "args": ["server.js"]}),
            encoding="utf-8",
        )
    return pdir


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / ".cataforge").mkdir()
    return tmp_path


def test_provided_skill_and_agent_dirs(project: Path) -> None:
    _make_plugin(project, "p1", skills=("greet",), agents=("helper",))
    loader = PluginLoader(project)
    skills = loader.provided_skill_dirs()
    agents = loader.provided_agent_dirs()
    assert (skills["greet"] / "SKILL.md").is_file()
    assert (agents["helper"] / "AGENT.md").is_file()


def test_provided_hooks_and_mcp(project: Path) -> None:
    _make_plugin(
        project, "p1", mcp=("srv1",),
        hooks=({"event": "PreToolUse", "script": "guard.py"},),
    )
    loader = PluginLoader(project)
    assert loader.provided_hooks() == [{"event": "PreToolUse", "script": "guard.py"}]
    mcp = loader.provided_mcp_spec_files()
    assert mcp["srv1"].name == "srv1.yaml"


def test_first_discoverer_wins_for_dirs(project: Path) -> None:
    # Two local plugins both claim skill id 'dup'; discover order (sorted) →
    # 'a' before 'b', so 'a' wins via setdefault.
    _make_plugin(project, "b-plugin", skills=("dup",))
    _make_plugin(project, "a-plugin", skills=("dup",))
    got = PluginLoader(project).provided_skill_dirs()
    assert got["dup"].parent.parent.name == "a-plugin"


def test_skill_loader_discovers_plugin_skill(project: Path) -> None:
    from cataforge.runtime.skill.loader import SkillLoader

    _make_plugin(project, "p1", skills=("greet",))
    loader = SkillLoader(project)
    assert "greet" in {s.id for s in loader.discover()}
    meta = loader.get_skill("greet")
    assert meta is not None and meta.description == "from p1"


def test_scaffold_skill_overrides_plugin_skill(project: Path) -> None:
    from cataforge.runtime.skill.loader import SkillLoader

    _make_plugin(project, "p1", skills=("greet",))
    # Scaffold layer defines the same id → wins over the plugin.
    sd = project / ".cataforge" / "skills" / "greet"
    sd.mkdir(parents=True)
    (sd / "SKILL.md").write_text(
        "---\nname: greet\ndescription: from scaffold\n---\nbody\n", encoding="utf-8"
    )
    assert SkillLoader(project).get_skill("greet").description == "from scaffold"


def test_resolver_merges_plugin_agent_below_scaffold(project: Path) -> None:
    from cataforge.runtime.assets.resolver import resolve_kind

    _make_plugin(project, "p1", agents=("helper",))
    plugin_dirs = PluginLoader(project).provided_agent_dirs()
    dest = project / "staged" / "agents"
    ids = resolve_kind(ProjectPaths(project), "agents", dest, plugin_dirs=plugin_dirs)
    assert ids == ["helper"]
    assert "plugin agent helper" in (dest / "helper" / "AGENT.md").read_text(encoding="utf-8")


def test_mcp_registry_picks_up_plugin_server(project: Path) -> None:
    from cataforge.runtime.mcp.registry import MCPRegistry

    _make_plugin(project, "p1", mcp=("srv1",))
    reg = MCPRegistry(project)
    assert reg.get_server("srv1") is not None


def test_bridge_merges_plugin_hooks(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cataforge.runtime.hook import bridge

    _make_plugin(
        project, "p1",
        hooks=({"event": "PreToolUse", "script": "guard.py"},),
    )
    monkeypatch.chdir(project)
    spec: dict = {"hooks": {"PreToolUse": [{"script": "existing.py"}]}}
    bridge._merge_plugin_hooks(spec)
    scripts = [h["script"] for h in spec["hooks"]["PreToolUse"]]
    assert scripts == ["existing.py", "guard.py"]
