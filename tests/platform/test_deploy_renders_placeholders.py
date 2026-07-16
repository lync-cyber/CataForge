"""End-to-end tests that runtime placeholders survive every deploy path.

Locks the J-render contract: when a source file under ``.cataforge/`` carries
``{INSTRUCTION_FILE}`` / ``{AGENTS_DIR}`` / ``{RULES_DIR}`` / ``{SKILLS_DIR}``
/ ``{COMMANDS_DIR}``, the file that actually lands at the platform-native
path has those tokens substituted to the platform's concrete value. The
deployed copy is what the LLM reads at runtime, so any leak of a literal
``{TOKEN}`` into a deployed artefact is treated as a J-render bug.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cataforge.adapter.platform.adapter import PlatformAdapter
from cataforge.adapter.platform.profile_schema import PlatformProfile
from cataforge.adapter.platform.registry import get_adapter
from cataforge.runtime.deploy import steps


def _platforms_dir() -> Path:
    return Path.cwd() / ".cataforge" / "platforms"


# ---- deploy_agents: AGENT.md body + sibling *.md ----------------------


class _SubdirAgentAdapter(PlatformAdapter):
    """Minimal adapter exercising the subdir agent deploy + sibling path."""

    def __init__(self) -> None:
        super().__init__(
            PlatformProfile.model_validate(
                {
                    "agent_definition": {"scan_dirs": [".test/agents"], "needs_deploy": True},
                    "skill_definition": {"target_dir": ".test/skills", "needs_deploy": True},
                    "command_definition": {"target_dir": ".test/commands", "needs_deploy": True},
                    "context_injection": {"rules_distribution": {"target": ".test/rules"}},
                    "instruction_file": {
                        "targets": [{"type": "project_state_copy", "path": "AGENTS.md"}]
                    },
                }
            )
        )

    @property
    def platform_id(self) -> str:
        return "test-subdir"

    @property
    def display_name(self) -> str:
        return "TestSubdir"

    def get_agent_scan_dirs(self) -> list[str]:
        return list(self._profile.agent_definition.scan_dirs)

    def get_agent_format(self) -> str:
        return "yaml-frontmatter"


def _write_agent(agents_dir: Path, name: str, body: str) -> None:
    agent_dir = agents_dir / name
    agent_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / "AGENT.md").write_text(
        f"---\nname: {name}\ndescription: test\n---\n\n{body}",
        encoding="utf-8",
    )


def test_deploy_agents_renders_agent_md_body(tmp_path: Path) -> None:
    """AGENT.md body containing ``{INSTRUCTION_FILE}`` lands as ``AGENTS.md``
    on this adapter (whose instruction target is ``AGENTS.md``)."""
    adapter = _SubdirAgentAdapter()
    src = tmp_path / ".cataforge" / "agents"
    _write_agent(src, "orchestrator", "see {INSTRUCTION_FILE} §状态")
    steps.deploy_agents(adapter, src, tmp_path)
    deployed = (tmp_path / ".test" / "agents" / "orchestrator" / "AGENT.md").read_text(
        encoding="utf-8"
    )
    assert "{INSTRUCTION_FILE}" not in deployed
    assert "see AGENTS.md §状态" in deployed


def test_deploy_agents_preserves_and_renders_sibling_md(tmp_path: Path) -> None:
    """Sibling files (PROTOCOLS / META) ship next to AGENT.md and have their
    own placeholder body rendered. This is the contract that lets the LLM
    follow a cross-reference from AGENT.md to a sibling without leaving the
    deployed tree."""
    adapter = _SubdirAgentAdapter()
    src = tmp_path / ".cataforge" / "agents"
    _write_agent(src, "orchestrator", "see ORCHESTRATOR-PROTOCOLS.md")
    (src / "orchestrator" / "ORCHESTRATOR-PROTOCOLS.md").write_text(
        "see {INSTRUCTION_FILE} §X 和 {RULES_DIR}/COMMON-RULES.md", encoding="utf-8"
    )

    steps.deploy_agents(adapter, src, tmp_path)

    sibling = tmp_path / ".test" / "agents" / "orchestrator" / "ORCHESTRATOR-PROTOCOLS.md"
    assert sibling.is_file()
    body = sibling.read_text(encoding="utf-8")
    assert "{INSTRUCTION_FILE}" not in body
    assert "{RULES_DIR}" not in body
    assert "AGENTS.md" in body
    assert ".test/rules/COMMON-RULES.md" in body


def test_deploy_agents_prunes_stale_sibling(tmp_path: Path) -> None:
    """Sibling files the previous deploy wrote but source no longer carries
    are removed — but only when the prior manifest claims ownership."""
    adapter = _SubdirAgentAdapter()
    src = tmp_path / ".cataforge" / "agents"
    _write_agent(src, "orchestrator", "body")
    # First deploy writes a sibling
    (src / "orchestrator" / "STALE-PROTOCOL.md").write_text(
        "v1 {INSTRUCTION_FILE}", encoding="utf-8"
    )
    from cataforge.runtime.deploy.manifest import DeployManifest

    manifest = DeployManifest("test-subdir")
    steps.deploy_agents(adapter, src, tmp_path, manifest=manifest)
    prior = set(manifest.owned)
    assert ".test/agents/orchestrator/STALE-PROTOCOL.md" in prior

    # Second deploy: source dropped the sibling
    (src / "orchestrator" / "STALE-PROTOCOL.md").unlink()
    steps.deploy_agents(adapter, src, tmp_path, prior_manifest=prior)

    assert not (tmp_path / ".test" / "agents" / "orchestrator" / "STALE-PROTOCOL.md").exists()


# ---- deploy_rules / deploy_skills: copy + render -----------------------


def test_deploy_rules_renders_md_files_in_place(tmp_path: Path) -> None:
    adapter = _SubdirAgentAdapter()
    src = tmp_path / ".cataforge" / "rules"
    src.mkdir(parents=True)
    (src / "COMMON-RULES.md").write_text(
        "见 {INSTRUCTION_FILE} §X；agent 协议 {AGENTS_DIR}/orchestrator/AGENT.md",
        encoding="utf-8",
    )

    steps.deploy_rules(adapter, src, tmp_path)

    deployed = (tmp_path / ".test" / "rules" / "COMMON-RULES.md").read_text(encoding="utf-8")
    assert "{INSTRUCTION_FILE}" not in deployed
    assert "AGENTS.md" in deployed
    assert ".test/agents/orchestrator/AGENT.md" in deployed


def test_deploy_skills_copy_renders_md_but_leaves_non_md(tmp_path: Path) -> None:
    """``shutil.copytree`` brings non-md files (scripts, fixtures) into the
    target; only the ``*.md`` files run through the renderer so literal
    braces in code blocks survive."""
    adapter = _SubdirAgentAdapter()
    src = tmp_path / ".cataforge" / "skills"
    skill = src / "research"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: research\ndescription: test\n---\n\n"
        "见 {INSTRUCTION_FILE}；脚本目录 {SKILLS_DIR}/research/scripts",
        encoding="utf-8",
    )
    # Non-md sibling with literal braces that must survive verbatim.
    (skill / "fixture.json").write_text('{"placeholder": "{INSTRUCTION_FILE}"}', encoding="utf-8")

    steps.deploy_skills(adapter, src, tmp_path)

    skill_md = (tmp_path / ".test" / "skills" / "research" / "SKILL.md").read_text(encoding="utf-8")
    fixture = (tmp_path / ".test" / "skills" / "research" / "fixture.json").read_text(
        encoding="utf-8"
    )
    assert "{INSTRUCTION_FILE}" not in skill_md
    assert ".test/skills/research/scripts" in skill_md
    # Non-md ride through copy untouched — literal placeholder stays put.
    assert fixture == '{"placeholder": "{INSTRUCTION_FILE}"}'


def test_deploy_skills_excludes_upgrade_sidecar_and_pycache(tmp_path: Path) -> None:
    """Upgrade sidecars (``*.cataforge-new``) and bytecode caches
    (``__pycache__``) live in the project ``.cataforge/`` tree but must never
    ride the copy into the IDE skill tree — a real drift sidecar would land as
    dead weight and the bytecode cache would pollute the deployed surface."""
    adapter = _SubdirAgentAdapter()
    src = tmp_path / ".cataforge" / "skills"
    skill = src / "research"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: research\ndescription: test\n---\n\nbody",
        encoding="utf-8",
    )
    # A real user-modified scaffold file leaves a sidecar beside it on upgrade.
    (skill / "SKILL.md.cataforge-new").write_text("framework version", encoding="utf-8")
    # Skills can ship .py helpers; running them seeds a bytecode cache.
    pycache = skill / "scripts" / "__pycache__"
    pycache.mkdir(parents=True)
    (pycache / "helper.cpython-313.pyc").write_bytes(b"\x00bytecode")

    steps.deploy_skills(adapter, src, tmp_path)

    deployed = tmp_path / ".test" / "skills" / "research"
    assert (deployed / "SKILL.md").is_file()
    assert not (deployed / "SKILL.md.cataforge-new").exists()
    assert not (deployed / "scripts" / "__pycache__").exists()


# ---- deploy_instruction_files: PROJECT-STATE.md → CLAUDE.md/AGENTS.md ---


def test_deploy_instruction_files_renders_runtime_placeholders(tmp_path: Path) -> None:
    """PROJECT-STATE.md placeholders must resolve before landing as
    CLAUDE.md / AGENTS.md — the user's IDE auto-loads this file every
    session, so an unresolved token leaks straight into the prompt."""
    adapter = _SubdirAgentAdapter()
    project_state = tmp_path / ".cataforge" / "PROJECT-STATE.md"
    project_state.parent.mkdir(parents=True)
    project_state.write_text(
        "# Test\n\n运行时: {platform}\n\n参见 {INSTRUCTION_FILE} 和 {RULES_DIR}/COMMON-RULES.md\n",
        encoding="utf-8",
    )

    steps.deploy_instruction_files(adapter, project_state, tmp_path, platform_id="test-subdir")

    out = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert "{platform}" not in out
    assert "{INSTRUCTION_FILE}" not in out
    assert "{RULES_DIR}" not in out
    assert "运行时: test-subdir" in out
    assert "参见 AGENTS.md 和 .test/rules/COMMON-RULES.md" in out


@pytest.mark.parametrize("platform_id", ["claude-code", "cursor", "codex", "opencode"])
def test_deploy_stamps_and_advances_framework_version(
    platform_id: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``框架版本: {FRAMEWORK_VERSION}`` is stamped from the package version at
    deploy, and a re-deploy after a version bump advances it. Guards both
    halves of the fix: the placeholder is substituted (no ``{FRAMEWORK_VERSION}``
    leak), and the section-merge ``always_overwrite_fields`` policy force-writes
    the field instead of preserving the now-stale on-disk value.
    """
    import cataforge

    adapter = get_adapter(platform_id, _platforms_dir())
    target_rel = str(adapter.instruction_targets[0]["path"])
    project_state = tmp_path / ".cataforge" / "PROJECT-STATE.md"
    project_state.parent.mkdir(parents=True)
    project_state.write_text(
        "# CataForge\n\n## 项目信息\n\n- 运行时: {platform}\n- 框架版本: {FRAMEWORK_VERSION}\n",
        encoding="utf-8",
    )

    steps.deploy_instruction_files(adapter, project_state, tmp_path, platform_id=platform_id)
    out = (tmp_path / target_rel).read_text(encoding="utf-8")
    assert "{FRAMEWORK_VERSION}" not in out
    assert f"- 框架版本: {cataforge.__version__}" in out

    # Simulate an upgrade: bump the package version and re-deploy. section-merge
    # must advance the field (always_overwrite_fields), not preserve the stale value.
    monkeypatch.setattr(cataforge, "__version__", "9.9.9-test")
    steps.deploy_instruction_files(adapter, project_state, tmp_path, platform_id=platform_id)
    out2 = (tmp_path / target_rel).read_text(encoding="utf-8")
    assert "- 框架版本: 9.9.9-test" in out2


@pytest.mark.parametrize("platform_id", ["claude-code", "cursor", "codex", "opencode"])
def test_deploy_renders_and_overwrites_design_tool(platform_id: str, tmp_path: Path) -> None:
    """设计工具 is rendered from framework.json#project.design_tool and
    force-overwritten on every deploy (always_overwrite_fields: 全局约定:[设计工具]),
    so a stale value in a previously-deployed instruction file can't drift —
    making framework.json the single source of truth for the field.
    """
    adapter = get_adapter(platform_id, _platforms_dir())
    target_rel = str(adapter.instruction_targets[0]["path"])
    project_state = tmp_path / ".cataforge" / "PROJECT-STATE.md"
    project_state.parent.mkdir(parents=True)
    project_state.write_text(
        "# CataForge\n\n## 全局约定\n\n- 设计工具: {DESIGN_TOOL}\n",
        encoding="utf-8",
    )

    steps.deploy_instruction_files(
        adapter, project_state, tmp_path, platform_id=platform_id, design_tool="penpot"
    )
    out = (tmp_path / target_rel).read_text(encoding="utf-8")
    assert "{DESIGN_TOOL}" not in out
    assert "- 设计工具: penpot" in out

    # Re-deploy with framework.json back to none: force-overwrite must win over
    # the now-stale 'penpot' the previous deploy left in the instruction file.
    steps.deploy_instruction_files(
        adapter, project_state, tmp_path, platform_id=platform_id, design_tool="none"
    )
    out2 = (tmp_path / target_rel).read_text(encoding="utf-8")
    assert "- 设计工具: none" in out2
    assert "- 设计工具: penpot" not in out2


# ---- real adapter spot-check: claude-code renders to its own paths -----


@pytest.mark.parametrize("platform_id", ["claude-code", "cursor", "codex", "opencode"])
def test_real_adapter_renders_instruction_file_token(platform_id: str, tmp_path: Path) -> None:
    """Smoke-test every shipped adapter: deploying an agent body containing
    ``{INSTRUCTION_FILE}`` produces an artefact with the platform's own
    instruction file name baked in.
    """
    adapter = get_adapter(platform_id, _platforms_dir())
    src = tmp_path / ".cataforge" / "agents"
    _write_agent(src, "smoke", "ref to {INSTRUCTION_FILE}")
    steps.deploy_agents(adapter, src, tmp_path)

    # Scan for the deployed artefact (subdir or flat) — source under
    # ``.cataforge/`` must be excluded from this assertion because it
    # deliberately retains the unrendered placeholder.
    cataforge_dir = tmp_path / ".cataforge"
    rendered_bodies = []
    for p in tmp_path.rglob("*"):
        if not p.is_file() or p.suffix not in (".md", ".toml"):
            continue
        try:
            p.relative_to(cataforge_dir)
            continue  # source — skip
        except ValueError:
            pass
        if "smoke" not in p.name and "smoke" not in p.parent.name:
            continue
        text = p.read_text(encoding="utf-8")
        if "ref to" in text:
            rendered_bodies.append((p, text))
    assert rendered_bodies, f"no deployed body found for {platform_id} under {tmp_path}"
    for path, body in rendered_bodies:
        assert "{INSTRUCTION_FILE}" not in body, f"unrendered token in {path}"
