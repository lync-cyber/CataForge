"""Orphan-prune behaviour for Codex and OpenCode agent deployments.

Both adapters now mirror the prune contract that ``claude_code.py`` and
``platform/base.py`` have implemented for a while — when an agent is
renamed or deleted upstream, the next ``cataforge deploy`` must remove
the stale platform-native file. Without prune, the IDE keeps loading a
phantom agent forever.

The tests use minimal hand-rolled profiles so they don't depend on the
shipped ``.cataforge/platforms/<id>/profile.yaml`` evolving.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cataforge.adapter.platform.codex import CodexAdapter
from cataforge.adapter.platform.opencode import OpenCodeAdapter

# Minimal AGENT.md that survives translator filtering on both platforms.
_AGENT_MD = """---
name: {name}
description: test agent {name}
---
body for {name}
"""


def _seed_source(root: Path, *agent_names: str) -> Path:
    src = root / ".cataforge" / "agents"
    for name in agent_names:
        agent_dir = src / name
        agent_dir.mkdir(parents=True, exist_ok=True)
        (agent_dir / "AGENT.md").write_text(_AGENT_MD.format(name=name), encoding="utf-8")
    return src


# ---- Codex ---------------------------------------------------------------


@pytest.fixture()
def codex_adapter() -> CodexAdapter:
    return CodexAdapter(
        {
            "platform_id": "codex",
            "agent_supported_fields": ["name", "description", "model"],
            "agent_definition": {"scan_dirs": [".codex/agents"]},
        }
    )


def test_codex_prunes_orphan_toml_when_agent_removed(
    tmp_path: Path, codex_adapter: CodexAdapter
) -> None:
    src = _seed_source(tmp_path, "current-agent")

    # Simulate a prior deploy that wrote an obsolete agent's TOML profile.
    target_dir = tmp_path / ".codex" / "agents"
    target_dir.mkdir(parents=True)
    orphan_toml = target_dir / "retired-agent.toml"
    orphan_toml.write_text(
        '# Auto-generated from retired-agent/AGENT.md\nname = "retired-agent"\n',
        encoding="utf-8",
    )

    actions = codex_adapter.deploy_agents(src, tmp_path)

    assert (target_dir / "current-agent.toml").is_file()
    assert not orphan_toml.exists()
    assert any("pruned orphan" in a and "retired-agent.toml" in a for a in actions)


def test_codex_does_not_prune_user_authored_toml(
    tmp_path: Path, codex_adapter: CodexAdapter
) -> None:
    """A .toml without our auto-generated header must survive even when
    its stem doesn't match any current source agent."""
    src = _seed_source(tmp_path, "current-agent")

    target_dir = tmp_path / ".codex" / "agents"
    target_dir.mkdir(parents=True)
    user_toml = target_dir / "my-personal.toml"
    user_toml.write_text('name = "my-personal"\n', encoding="utf-8")

    codex_adapter.deploy_agents(src, tmp_path)

    assert user_toml.is_file(), "user-authored .toml without our header was pruned"


def test_codex_dry_run_reports_prune_without_writing(
    tmp_path: Path, codex_adapter: CodexAdapter
) -> None:
    src = _seed_source(tmp_path, "current-agent")
    target_dir = tmp_path / ".codex" / "agents"
    target_dir.mkdir(parents=True)
    orphan_toml = target_dir / "retired-agent.toml"
    orphan_toml.write_text("# Auto-generated from retired-agent/AGENT.md\n", encoding="utf-8")

    actions = codex_adapter.deploy_agents(src, tmp_path, dry_run=True)

    assert orphan_toml.exists(), "dry-run must not actually delete"
    assert any("would prune orphan" in a for a in actions)


# ---- OpenCode ------------------------------------------------------------


@pytest.fixture()
def opencode_adapter() -> OpenCodeAdapter:
    return OpenCodeAdapter(
        {
            "platform_id": "opencode",
            "agent_supported_fields": ["name", "description", "model"],
            "agent_definition": {"scan_dirs": [".opencode/agents"]},
        }
    )


def test_opencode_prunes_orphan_md_when_agent_removed(
    tmp_path: Path, opencode_adapter: OpenCodeAdapter
) -> None:
    src = _seed_source(tmp_path, "current-agent")

    target_dir = tmp_path / ".opencode" / "agents"
    target_dir.mkdir(parents=True)
    orphan = target_dir / "retired-agent.md"
    orphan.write_text("---\nname: retired-agent\n---\nold body\n", encoding="utf-8")

    actions = opencode_adapter.deploy_agents(src, tmp_path)

    assert (target_dir / "current-agent.md").is_file()
    assert not orphan.exists()
    assert any("pruned orphan" in a and "retired-agent.md" in a for a in actions)


def test_opencode_does_not_prune_user_authored_md(
    tmp_path: Path, opencode_adapter: OpenCodeAdapter
) -> None:
    """A .md without a matching ``name:`` frontmatter line is user-authored
    or IDE-native — must survive."""
    src = _seed_source(tmp_path, "current-agent")

    target_dir = tmp_path / ".opencode" / "agents"
    target_dir.mkdir(parents=True)
    user_md = target_dir / "personal-notes.md"
    user_md.write_text("# my notes\n", encoding="utf-8")

    opencode_adapter.deploy_agents(src, tmp_path)

    assert user_md.is_file(), "user-authored .md without our name: was pruned"


def test_opencode_dry_run_reports_prune_without_writing(
    tmp_path: Path, opencode_adapter: OpenCodeAdapter
) -> None:
    src = _seed_source(tmp_path, "current-agent")
    target_dir = tmp_path / ".opencode" / "agents"
    target_dir.mkdir(parents=True)
    orphan = target_dir / "retired-agent.md"
    orphan.write_text("---\nname: retired-agent\n---\n", encoding="utf-8")

    actions = opencode_adapter.deploy_agents(src, tmp_path, dry_run=True)

    assert orphan.exists(), "dry-run must not actually delete"
    assert any("would prune orphan" in a for a in actions)


# ---- Codex TOML passthrough derives from supported_fields ----------------


def _codex_with_fields(*fields: str) -> CodexAdapter:
    return CodexAdapter(
        {
            "platform_id": "codex",
            "agent_config": {"supported_fields": list(fields)},
            "agent_definition": {"scan_dirs": [".codex/agents"]},
        }
    )


def _deploy_one(adapter: CodexAdapter, tmp_path: Path, frontmatter: str) -> str:
    src = tmp_path / ".cataforge" / "agents"
    (src / "a").mkdir(parents=True)
    (src / "a" / "AGENT.md").write_text(f"---\n{frontmatter}---\n# body\n", encoding="utf-8")
    adapter.deploy_agents(src, tmp_path)
    return (tmp_path / ".codex" / "agents" / "a.toml").read_text(encoding="utf-8")


def test_codex_passthrough_honors_extra_supported_field(tmp_path: Path) -> None:
    """Adding a field to the profile's supported_fields makes it survive the
    TOML round-trip with no code change to ``_md_to_toml``."""
    adapter = _codex_with_fields("name", "description", "sandbox_mode", "extra_codex_knob")
    toml = _deploy_one(
        adapter,
        tmp_path,
        "name: a\ndescription: d\nsandbox_mode: full\nextra_codex_knob: tuned\n",
    )
    # name/description still emitted (explicit), body wrapped.
    assert 'name = "a"' in toml
    assert 'description = "d"' in toml
    assert 'developer_instructions = """' in toml
    # Declared extras pass through — including a brand-new profile field that
    # the formatter never hardcoded.
    assert 'sandbox_mode = "full"' in toml
    assert 'extra_codex_knob = "tuned"' in toml


def test_codex_passthrough_excludes_undeclared_field(tmp_path: Path) -> None:
    """A field absent from supported_fields is filtered before TOML and never
    passed through, while a declared sibling survives."""
    adapter = _codex_with_fields("name", "description", "sandbox_mode")
    toml = _deploy_one(
        tmp_path=tmp_path,
        adapter=adapter,
        frontmatter="name: a\ndescription: d\nsandbox_mode: full\nextra_codex_knob: tuned\n",
    )
    assert 'sandbox_mode = "full"' in toml
    assert "extra_codex_knob" not in toml
