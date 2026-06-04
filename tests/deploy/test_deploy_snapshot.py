"""Characterization snapshot tests for deploy steps and manifest behaviour.

Locks observable invariants so that TASK-11/12/13 refactors (moving
_deploy_mixins to runtime/deploy/steps/, pipeline rewrite, adapter
as config-carrier) cannot silently regress functional correctness.

Invariants captured:
- dry-run action lists contain the expected action categories per platform
- deployed artefact layout maps to the platform-native directory structure
- manifest owned-set covers key artefact categories after a real deploy
- consecutive deploys are idempotent (no unexpected new/deleted owned paths)
- ownership-scoped prune never deletes user-authored files absent from the manifest
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from cataforge.adapter.platform.registry import clear_cache
from cataforge.core.config import ConfigManager
from cataforge.core.paths import DEPLOY_MANIFEST_REL
from cataforge.runtime.deploy.deployer import Deployer
from cataforge.runtime.deploy.manifest import load_prior_manifest

# ---------------------------------------------------------------------------
# Platform profiles used across multiple tests
# ---------------------------------------------------------------------------

_CLAUDE_PROFILE: dict = {
    "platform_id": "claude-code",
    "display_name": "Claude Code",
    "tool_map": {"file_read": "Read", "file_edit": "Write"},
    "extended_capabilities": {},
    "agent_definition": {
        "format": "yaml-frontmatter",
        "scan_dirs": [".claude/agents"],
        "needs_deploy": True,
    },
    "instruction_file": {
        "reads_claude_md": True,
        "targets": [{"type": "project_state_copy", "path": "CLAUDE.md"}],
    },
    "dispatch": {"tool_name": "Agent", "is_async": False},
    "hooks": {
        "config_format": None,
        "config_path": None,
        "event_map": {},
        "degradation": {},
    },
    "skill_definition": {"needs_deploy": True, "target_dir": ".claude/skills"},
    "command_definition": {"needs_deploy": True, "target_dir": ".claude/commands"},
}

_CURSOR_PROFILE: dict = {
    "platform_id": "cursor",
    "display_name": "Cursor",
    "tool_map": {"file_read": "Read", "file_edit": "Write"},
    "extended_capabilities": {},
    "agent_definition": {
        "format": "yaml-frontmatter",
        "scan_dirs": [".cursor/agents"],
        "needs_deploy": True,
    },
    "instruction_file": {
        "reads_claude_md": False,
        "targets": [{"type": "project_state_copy", "path": "AGENTS.md"}],
    },
    "dispatch": {"tool_name": "Task", "is_async": False},
    "hooks": {
        "config_format": None,
        "config_path": None,
        "event_map": {},
        "degradation": {},
    },
    "skill_definition": {"needs_deploy": True, "target_dir": ".claude/skills"},
    "command_definition": {"needs_deploy": True, "target_dir": ".cursor/commands"},
}

_CODEX_PROFILE: dict = {
    "platform_id": "codex",
    "display_name": "Codex CLI",
    "tool_map": {"file_read": "shell", "file_edit": "apply_patch"},
    "extended_capabilities": {},
    "agent_definition": {
        "format": "toml",
        "scan_dirs": [".codex/agents"],
        "needs_deploy": True,
    },
    "instruction_file": {
        "reads_claude_md": False,
        "targets": [{"type": "project_state_copy", "path": "AGENTS.md"}],
    },
    "dispatch": {"tool_name": "spawn_agent", "is_async": True},
    "hooks": {
        "config_format": None,
        "config_path": None,
        "event_map": {},
        "degradation": {},
    },
    "skill_definition": {"needs_deploy": False},
    "command_definition": {"needs_deploy": False},
}

_OPENCODE_PROFILE: dict = {
    "platform_id": "opencode",
    "display_name": "OpenCode",
    "tool_map": {"file_read": "read", "file_edit": "edit"},
    "extended_capabilities": {},
    "agent_definition": {
        "format": "yaml-frontmatter",
        "scan_dirs": [".opencode/agents", ".claude/agents"],
        "needs_deploy": True,
    },
    "instruction_file": {
        "reads_claude_md": False,
        "targets": [{"type": "project_state_copy", "path": "AGENTS.md"}],
    },
    "dispatch": {"tool_name": "task", "is_async": False},
    "hooks": {
        "config_format": None,
        "config_path": None,
        "event_map": {},
        "degradation": {},
    },
    "skill_definition": {"needs_deploy": False},
    "command_definition": {"needs_deploy": False},
}


# ---------------------------------------------------------------------------
# Shared project scaffold helper
# ---------------------------------------------------------------------------


def _init_project(tmp_path: Path, platform_id: str, profile: dict) -> Path:
    """Build a minimal .cataforge/ scaffold wired to the given platform."""
    root = tmp_path
    cf = root / ".cataforge"
    cf.mkdir(exist_ok=True)
    (cf / "framework.json").write_text(
        json.dumps({"version": "0.1.0", "runtime": {"platform": platform_id}}),
        encoding="utf-8",
    )
    (cf / "PROJECT-STATE.md").write_text("platform: {platform}\n", encoding="utf-8")
    (cf / "rules").mkdir(exist_ok=True)
    (cf / "rules" / "COMMON-RULES.md").write_text("# common\n", encoding="utf-8")
    agents_dir = cf / "agents" / "orchestrator"
    agents_dir.mkdir(parents=True, exist_ok=True)
    (agents_dir / "AGENT.md").write_text(
        "---\nname: orchestrator\ntools: file_read\n---\nbody\n",
        encoding="utf-8",
    )
    (cf / "hooks").mkdir(exist_ok=True)
    (cf / "hooks" / "hooks.yaml").write_text(
        "hooks: {}\ndegradation_templates: {}\n", encoding="utf-8"
    )
    (cf / "mcp").mkdir(exist_ok=True)
    skills_dir = cf / "skills" / "demo-skill"
    skills_dir.mkdir(parents=True, exist_ok=True)
    (skills_dir / "SKILL.md").write_text(
        "---\nname: demo-skill\ndescription: demo\n---\nbody\n", encoding="utf-8"
    )
    (cf / "commands").mkdir(exist_ok=True)
    (cf / "commands" / "bootstrap.md").write_text(
        "---\ndescription: bootstrap\n---\nbody\n", encoding="utf-8"
    )
    pdir = cf / "platforms" / platform_id
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "profile.yaml").write_text(yaml.safe_dump(profile), encoding="utf-8")
    return root


def _deploy(root: Path, platform_id: str, **kwargs) -> list[str]:
    clear_cache()
    return Deployer(ConfigManager(root)).deploy(platform_id, **kwargs)


# ---------------------------------------------------------------------------
# §1  Dry-run structural snapshot — four platforms
# ---------------------------------------------------------------------------

# Each entry: (platform_id, profile_dict, expected action fragments, absent fragments)
_PLATFORM_DRY_RUN_CASES = [
    pytest.param(
        "claude-code",
        _CLAUDE_PROFILE,
        # Actions that must appear in a dry-run:
        ["would deploy", "CLAUDE.md", "would write deploy state"],
        # Fragments that must NOT appear (cursor/codex/opencode artifacts):
        [".cursor/", ".codex/", "opencode.json"],
        id="claude-code",
    ),
    pytest.param(
        "cursor",
        _CURSOR_PROFILE,
        ["would deploy", "AGENTS.md", "would write deploy state"],
        ["CLAUDE.md", ".codex/", "opencode.json"],
        id="cursor",
    ),
    pytest.param(
        "codex",
        _CODEX_PROFILE,
        ["would deploy", "AGENTS.md", "would write deploy state"],
        ["CLAUDE.md", ".cursor/", "opencode.json"],
        id="codex",
    ),
    pytest.param(
        "opencode",
        _OPENCODE_PROFILE,
        ["would deploy", "AGENTS.md", "would write deploy state"],
        ["CLAUDE.md", ".cursor/", ".codex/"],
        id="opencode",
    ),
]


@pytest.mark.parametrize(
    "platform_id,profile,must_contain,must_not_contain", _PLATFORM_DRY_RUN_CASES
)
def test_dry_run_action_categories(
    tmp_path: Path,
    platform_id: str,
    profile: dict,
    must_contain: list[str],
    must_not_contain: list[str],
) -> None:
    """Dry-run actions include expected categories and exclude other-platform artifacts."""
    root = _init_project(tmp_path, platform_id, profile)
    actions = _deploy(root, platform_id, dry_run=True)

    assert actions, f"dry-run for {platform_id} returned empty action list"
    joined = "\n".join(actions)

    for fragment in must_contain:
        assert fragment in joined, (
            f"platform={platform_id}: expected {fragment!r} in dry-run actions; got:\n{joined}"
        )

    for fragment in must_not_contain:
        assert fragment not in joined, (
            f"platform={platform_id}: unexpected cross-platform artifact {fragment!r} "
            f"appeared in dry-run actions; got:\n{joined}"
        )


def test_dry_run_produces_no_files(tmp_path: Path) -> None:
    """A dry-run must not write any files to the project root."""
    root = _init_project(tmp_path, "claude-code", _CLAUDE_PROFILE)
    files_before = {p.relative_to(root) for p in root.rglob("*") if p.is_file()}

    _deploy(root, "claude-code", dry_run=True)

    files_after = {p.relative_to(root) for p in root.rglob("*") if p.is_file()}
    new_files = files_after - files_before
    assert not new_files, f"dry-run wrote unexpected files: {new_files}"


# ---------------------------------------------------------------------------
# §2  Real-deploy layout snapshot — platform-native directory structure
# ---------------------------------------------------------------------------


def test_claude_code_deploy_layout(tmp_path: Path) -> None:
    """Claude Code deploy places artefacts under .claude/ and CLAUDE.md at root."""
    root = _init_project(tmp_path, "claude-code", _CLAUDE_PROFILE)
    _deploy(root, "claude-code")

    assert (root / "CLAUDE.md").is_file(), "CLAUDE.md must be written at project root"
    assert (root / ".claude" / "agents" / "orchestrator.md").is_file(), (
        ".claude/agents/orchestrator.md must be deployed"
    )
    assert (root / ".claude" / "commands" / "bootstrap.md").is_file(), (
        ".claude/commands/bootstrap.md must be deployed"
    )
    skill_target = root / ".claude" / "skills" / "demo-skill"
    assert skill_target.exists(), ".claude/skills/demo-skill must be deployed"

    # No cursor/codex/opencode artifacts should appear
    assert not (root / "AGENTS.md").exists(), "claude-code deploy must not write AGENTS.md"
    assert not (root / ".cursor").exists(), "claude-code deploy must not touch .cursor/"
    assert not (root / ".codex").exists(), "claude-code deploy must not touch .codex/"


def test_cursor_deploy_layout(tmp_path: Path) -> None:
    """Cursor deploy places agents under .cursor/agents/ and writes AGENTS.md."""
    root = _init_project(tmp_path, "cursor", _CURSOR_PROFILE)
    _deploy(root, "cursor")

    assert (root / "AGENTS.md").is_file(), "AGENTS.md must be written at project root"
    # Cursor agents land as a subdirectory containing AGENT.md
    cursor_agents = root / ".cursor" / "agents"
    assert cursor_agents.is_dir(), ".cursor/agents/ must be created by cursor deploy"
    assert any(cursor_agents.rglob("AGENT.md")), (
        ".cursor/agents/ must contain at least one AGENT.md"
    )
    # Commands go to .cursor/commands/ for cursor
    assert (root / ".cursor" / "commands" / "bootstrap.md").is_file(), (
        ".cursor/commands/bootstrap.md must be deployed"
    )
    assert not (root / "CLAUDE.md").exists(), "cursor deploy must not write CLAUDE.md"


def test_codex_deploy_layout(tmp_path: Path) -> None:
    """Codex deploy writes AGENTS.md and agents to .codex/agents/ in TOML format."""
    root = _init_project(tmp_path, "codex", _CODEX_PROFILE)
    _deploy(root, "codex")

    assert (root / "AGENTS.md").is_file(), "AGENTS.md must be written at project root"
    codex_agent = root / ".codex" / "agents" / "orchestrator.toml"
    assert codex_agent.is_file(), ".codex/agents/orchestrator.toml must be deployed for codex"
    assert not (root / "CLAUDE.md").exists(), "codex deploy must not write CLAUDE.md"
    assert not (root / ".claude" / "agents").exists(), (
        "codex deploy must not write to .claude/agents/"
    )


def test_opencode_deploy_layout(tmp_path: Path) -> None:
    """OpenCode deploy writes AGENTS.md and agents to .opencode/agents/."""
    root = _init_project(tmp_path, "opencode", _OPENCODE_PROFILE)
    _deploy(root, "opencode")

    assert (root / "AGENTS.md").is_file(), "AGENTS.md must be written at project root"
    opencode_agent = root / ".opencode" / "agents" / "orchestrator.md"
    assert opencode_agent.is_file(), ".opencode/agents/orchestrator.md must be deployed"
    assert not (root / "CLAUDE.md").exists(), "opencode deploy must not write CLAUDE.md"


# ---------------------------------------------------------------------------
# §3  Manifest owned-set coverage
# ---------------------------------------------------------------------------


def test_manifest_owned_covers_key_artefact_categories(tmp_path: Path) -> None:
    """After a real deploy the manifest must record agents, commands, and the instruction file."""
    root = _init_project(tmp_path, "claude-code", _CLAUDE_PROFILE)
    _deploy(root, "claude-code")

    owned = load_prior_manifest(root)
    assert owned, "manifest must not be empty after deploy"

    # Instruction file
    assert any(p.endswith("CLAUDE.md") or p == "CLAUDE.md" for p in owned), (
        "manifest must own the instruction file (CLAUDE.md)"
    )
    # Agent artefact
    assert any("agents" in p and p.endswith(".md") for p in owned), (
        "manifest must own at least one agent .md file"
    )
    # Command artefact
    assert any("commands" in p and p.endswith(".md") for p in owned), (
        "manifest must own at least one command .md file"
    )
    # Skill artefact (directory or files inside)
    assert any("skills" in p for p in owned), "manifest must own at least one skill path"


def test_manifest_platform_field_matches_deploy_target(tmp_path: Path) -> None:
    """The manifest platform field must match the platform that was deployed."""
    root = _init_project(tmp_path, "cursor", _CURSOR_PROFILE)
    _deploy(root, "cursor")

    manifest_path = root / DEPLOY_MANIFEST_REL
    assert manifest_path.is_file()
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert data.get("platform") == "cursor", (
        f"manifest platform must be 'cursor', got {data.get('platform')!r}"
    )


def test_manifest_owned_paths_are_posix_style(tmp_path: Path) -> None:
    """All owned paths in the manifest must use forward slashes (portable POSIX format)."""
    root = _init_project(tmp_path, "claude-code", _CLAUDE_PROFILE)
    _deploy(root, "claude-code")

    owned = load_prior_manifest(root)
    for path in owned:
        assert "\\" not in path, (
            f"manifest path {path!r} contains backslashes — must be POSIX style"
        )


# ---------------------------------------------------------------------------
# §4  Idempotency: consecutive deploys produce stable owned-set
# ---------------------------------------------------------------------------


def test_consecutive_deploys_produce_stable_owned_set(tmp_path: Path) -> None:
    """Two consecutive deploys must produce the same manifest owned-set."""
    root = _init_project(tmp_path, "claude-code", _CLAUDE_PROFILE)
    _deploy(root, "claude-code")
    owned_first = load_prior_manifest(root)

    _deploy(root, "claude-code")
    owned_second = load_prior_manifest(root)

    added = owned_second - owned_first
    removed = owned_first - owned_second
    assert not added and not removed, (
        f"Second deploy changed the manifest owned-set unexpectedly.\n"
        f"  added  : {sorted(added)}\n"
        f"  removed: {sorted(removed)}"
    )


def test_consecutive_deploys_no_unexpected_new_artefacts(tmp_path: Path) -> None:
    """The second deploy must not write new file-system artefacts not present after the first."""
    root = _init_project(tmp_path, "claude-code", _CLAUDE_PROFILE)
    _deploy(root, "claude-code")

    def _collect_files(base: Path) -> set[str]:
        return {
            str(p.relative_to(base)).replace("\\", "/")
            for p in base.rglob("*")
            if p.is_file() and ".cataforge/.deploy-manifest.json" not in str(p)
        }

    files_after_first = _collect_files(root)
    _deploy(root, "claude-code")
    files_after_second = _collect_files(root)

    new_files = files_after_second - files_after_first
    assert not new_files, f"Second deploy created unexpected new artefacts: {sorted(new_files)}"


# ---------------------------------------------------------------------------
# §5  Prune safety: user-authored files survive deploy
# ---------------------------------------------------------------------------


def test_prune_does_not_delete_user_command_outside_manifest(tmp_path: Path) -> None:
    """A user-authored command file with no source counterpart must survive redeploy."""
    root = _init_project(tmp_path, "claude-code", _CLAUDE_PROFILE)
    _deploy(root, "claude-code")

    user_cmd = root / ".claude" / "commands" / "user_foo.md"
    user_cmd.write_text("---\ndescription: user custom\n---\nbody\n", encoding="utf-8")

    _deploy(root, "claude-code")

    assert user_cmd.is_file(), (
        "user_foo.md was pruned by the second deploy — "
        "ownership-scoped prune must not touch files absent from the manifest"
    )
    assert "user custom" in user_cmd.read_text(encoding="utf-8"), (
        "user_foo.md content was modified by deploy"
    )


def test_prune_does_not_delete_user_skill_outside_manifest(tmp_path: Path) -> None:
    """A user-created skill directory with no source counterpart must survive redeploy."""
    root = _init_project(tmp_path, "claude-code", _CLAUDE_PROFILE)
    _deploy(root, "claude-code")

    user_skill = root / ".claude" / "skills" / "my-project-skill"
    user_skill.mkdir(parents=True)
    (user_skill / "SKILL.md").write_text(
        "---\nname: my-project-skill\n---\nuser skill\n", encoding="utf-8"
    )

    _deploy(root, "claude-code")

    assert user_skill.is_dir(), (
        "my-project-skill directory was pruned — "
        "ownership-scoped prune must not touch directories absent from the manifest"
    )


def test_prune_does_not_delete_user_agent_outside_manifest(tmp_path: Path) -> None:
    """A user-authored agent file with no source counterpart must survive redeploy."""
    root = _init_project(tmp_path, "claude-code", _CLAUDE_PROFILE)
    _deploy(root, "claude-code")

    user_agent = root / ".claude" / "agents" / "my-custom-agent.md"
    user_agent.write_text(
        "---\nname: my-custom-agent\ntools: file_read\n---\nmy custom body\n",
        encoding="utf-8",
    )

    _deploy(root, "claude-code")

    assert user_agent.is_file(), (
        "my-custom-agent.md was pruned — "
        "ownership-scoped prune must not touch agent files absent from the manifest"
    )
