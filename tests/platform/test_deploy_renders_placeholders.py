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
from typing import Any

import pytest

from cataforge.adapter.platform.adapter import PlatformAdapter
from cataforge.adapter.platform.registry import get_adapter


def _platforms_dir() -> Path:
    return Path.cwd() / ".cataforge" / "platforms"


# ---- deploy_agents: AGENT.md body + sibling *.md ----------------------


class _SubdirAgentAdapter(PlatformAdapter):
    """Minimal adapter exercising the subdir agent deploy + sibling path."""

    def __init__(self) -> None:
        super().__init__(
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

    @property
    def platform_id(self) -> str:
        return "test-subdir"

    @property
    def display_name(self) -> str:
        return "TestSubdir"

    def get_project_root_env_var(self) -> str | None:
        return None

    def get_agent_scan_dirs(self) -> list[str]:
        return list(self._profile["agent_definition"]["scan_dirs"])

    def get_agent_format(self) -> str:
        return "yaml-frontmatter"

    def inject_mcp_config(
        self,
        server_id: str,
        server_config: dict[str, Any],
        project_root: Path,
        *,
        dry_run: bool = False,
    ) -> list[str]:
        del server_id, server_config, project_root, dry_run
        return []


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
    adapter.deploy_agents(src, tmp_path)
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

    adapter.deploy_agents(src, tmp_path)

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
    adapter.deploy_agents(src, tmp_path, manifest=manifest)
    prior = set(manifest.owned)
    assert ".test/agents/orchestrator/STALE-PROTOCOL.md" in prior

    # Second deploy: source dropped the sibling
    (src / "orchestrator" / "STALE-PROTOCOL.md").unlink()
    adapter.deploy_agents(src, tmp_path, prior_manifest=prior)

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

    adapter.deploy_rules(src, tmp_path)

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

    adapter.deploy_skills(src, tmp_path)

    skill_md = (tmp_path / ".test" / "skills" / "research" / "SKILL.md").read_text(encoding="utf-8")
    fixture = (tmp_path / ".test" / "skills" / "research" / "fixture.json").read_text(
        encoding="utf-8"
    )
    assert "{INSTRUCTION_FILE}" not in skill_md
    assert ".test/skills/research/scripts" in skill_md
    # Non-md ride through copy untouched — literal placeholder stays put.
    assert fixture == '{"placeholder": "{INSTRUCTION_FILE}"}'


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

    adapter.deploy_instruction_files(project_state, tmp_path, platform_id="test-subdir")

    out = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert "{platform}" not in out
    assert "{INSTRUCTION_FILE}" not in out
    assert "{RULES_DIR}" not in out
    assert "运行时: test-subdir" in out
    assert "参见 AGENTS.md 和 .test/rules/COMMON-RULES.md" in out


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
    adapter.deploy_agents(src, tmp_path)

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
