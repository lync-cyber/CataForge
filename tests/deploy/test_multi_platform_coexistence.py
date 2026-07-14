"""Multi-platform deploy coexistence contracts.

Covers the per-platform deploy state model
(``.cataforge/state/deploy/<platform>/{state,manifest}.json``):

* two platforms keep independent deploy records on one project
* redeploying one platform never mutates a sibling platform's artefacts
* a path co-owned by several platforms survives prune until its last owner
  deploys without it
* legacy single-slot ``.deploy-state`` / ``.deploy-manifest.json`` records
  migrate into the per-platform layout idempotently
* the project-level deploy lock rejects a concurrent holder fail-fast
* a shared instruction file (AGENTS.md) renders byte-identically regardless
  of platform deploy order, with the ``运行时:`` field showing the audience set
* a fresh secondary instruction file seeds its runtime sections from the
  default platform's primary instruction file
"""

from __future__ import annotations

import hashlib
import json
import shutil
import time
from pathlib import Path

import pytest
import yaml

from cataforge.adapter.platform.registry import clear_cache
from cataforge.core.config import ConfigManager
from cataforge.runtime.deploy.deployer import Deployer
from cataforge.utils.locks import LockHeldError

# ---------------------------------------------------------------------------
# Test fixtures
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
    "skill_definition": {
        "needs_deploy": True,
        "target_dir": ".claude/skills",
    },
    "command_definition": {
        "needs_deploy": True,
        "target_dir": ".claude/commands",
    },
}

# Cursor writes its own AGENTS.md + .cursor/ agents but shares the
# ``.claude/skills`` tree with claude-code (co-ownership scenario).
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
    "skill_definition": {
        "needs_deploy": True,
        "target_dir": ".claude/skills",
    },
    "command_definition": {
        "needs_deploy": False,
        "target_dir": None,
    },
}


def _shared_agents_md_profile(platform_id: str, display_name: str) -> dict:
    """Minimal profile whose only deploy surface is a shared AGENTS.md."""
    return {
        "platform_id": platform_id,
        "display_name": display_name,
        "tool_map": {"file_read": "read"},
        "extended_capabilities": {},
        "agent_definition": {"needs_deploy": False},
        "instruction_file": {
            "reads_claude_md": False,
            "targets": [{"type": "project_state_copy", "path": "AGENTS.md"}],
        },
        "dispatch": {"tool_name": None, "is_async": False},
        "hooks": {"config_format": None, "config_path": None},
        "skill_definition": {"needs_deploy": False},
        "command_definition": {"needs_deploy": False},
    }


# Codex target with the section-merge policy the real profile declares —
# exercises primary-instruction seeding of the runtime sections.
_CODEX_SECTION_MERGE_PROFILE: dict = {
    "platform_id": "codex",
    "display_name": "Codex CLI",
    "tool_map": {"file_read": "shell"},
    "extended_capabilities": {},
    "agent_definition": {"needs_deploy": False},
    "instruction_file": {
        "reads_claude_md": False,
        "targets": [
            {
                "type": "project_state_copy",
                "path": "AGENTS.md",
                "update_strategy": "section-merge",
                "section_policy": {
                    "framework": ["文档导航", "框架机制"],
                    "schema": ["项目信息", "全局约定"],
                    "runtime": ["项目状态", "执行环境"],
                    "user_extensible": True,
                    "always_overwrite_fields": {
                        "项目信息": ["运行时", "框架版本"],
                        "全局约定": ["设计工具"],
                    },
                },
            }
        ],
    },
    "dispatch": {"tool_name": None, "is_async": False},
    "hooks": {"config_format": None, "config_path": None},
    "skill_definition": {"needs_deploy": False},
    "command_definition": {"needs_deploy": False},
}


def _framework_v2(default_platform: str, targets: list[str]) -> dict:
    return {
        "version": "0.1.0",
        "schema_version": 2,
        "deployment": {"default_platform": default_platform, "targets": targets},
    }


def _init_project(root: Path, *, framework: dict, profiles: dict[str, dict]) -> Path:
    """Build a minimal ``.cataforge/`` scaffold with the given platform profiles."""
    root.mkdir(parents=True, exist_ok=True)
    cf = root / ".cataforge"
    cf.mkdir(exist_ok=True)
    (cf / "framework.json").write_text(json.dumps(framework), encoding="utf-8")
    (cf / "rules").mkdir(exist_ok=True)
    (cf / "rules" / "COMMON-RULES.md").write_text("# common\n", encoding="utf-8")
    (cf / "agents").mkdir(exist_ok=True)
    (cf / "agents" / "orchestrator").mkdir(exist_ok=True)
    (cf / "agents" / "orchestrator" / "AGENT.md").write_text(
        "---\nname: orchestrator\ntools: file_read\n---\nbody\n",
        encoding="utf-8",
    )
    (cf / "hooks").mkdir(exist_ok=True)
    (cf / "hooks" / "hooks.yaml").write_text(
        "hooks: {}\ndegradation_templates: {}\n", encoding="utf-8"
    )
    (cf / "mcp").mkdir(exist_ok=True)
    (cf / "skills").mkdir(exist_ok=True)
    (cf / "skills" / "demo-skill").mkdir(exist_ok=True)
    (cf / "skills" / "demo-skill" / "SKILL.md").write_text(
        "---\nname: demo-skill\ndescription: demo\n---\nbody\n", encoding="utf-8"
    )
    (cf / "commands").mkdir(exist_ok=True)
    (cf / "commands" / "bootstrap.md").write_text(
        "---\ndescription: bootstrap\n---\nbody\n", encoding="utf-8"
    )
    for platform_id, profile in profiles.items():
        pdir = cf / "platforms" / platform_id
        pdir.mkdir(parents=True, exist_ok=True)
        (pdir / "profile.yaml").write_text(yaml.safe_dump(profile), encoding="utf-8")
    return root


def _deploy(root: Path, platform_id: str) -> list[str]:
    clear_cache()
    return Deployer(ConfigManager(root)).deploy(platform_id)


def _init_claude_cursor_project(root: Path) -> Path:
    return _init_project(
        root,
        framework=_framework_v2("claude-code", ["claude-code", "cursor"]),
        profiles={"claude-code": _CLAUDE_PROFILE, "cursor": _CURSOR_PROFILE},
    )


def _manifest_path(root: Path, platform_id: str) -> Path:
    return root / ".cataforge" / "state" / "deploy" / platform_id / "manifest.json"


def _state_path(root: Path, platform_id: str) -> Path:
    return root / ".cataforge" / "state" / "deploy" / platform_id / "state.json"


def _tree_digest(base: Path) -> dict[str, str]:
    """Map every file under *base* (recursive) to its sha256."""
    digest: dict[str, str] = {}
    if not base.exists():
        return digest
    for p in sorted(base.rglob("*")):
        if p.is_file():
            rel = str(p.relative_to(base)).replace("\\", "/")
            digest[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    return digest


def _file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# 1. Per-platform deploy records coexist
# ---------------------------------------------------------------------------


def test_two_platform_deploy_records_coexist(tmp_path: Path) -> None:
    """Deploying cursor after claude-code keeps both per-platform manifests,
    and claude-code's ownership record is untouched by the cursor deploy."""
    root = _init_claude_cursor_project(tmp_path)

    _deploy(root, "claude-code")
    claude_manifest = _manifest_path(root, "claude-code")
    assert claude_manifest.is_file()
    claude_before = json.loads(claude_manifest.read_text(encoding="utf-8"))

    _deploy(root, "cursor")

    cursor_manifest = _manifest_path(root, "cursor")
    assert claude_manifest.is_file(), "claude-code manifest vanished after cursor deploy"
    assert cursor_manifest.is_file(), "cursor deploy wrote no per-platform manifest"

    claude_after = json.loads(claude_manifest.read_text(encoding="utf-8"))
    cursor_data = json.loads(cursor_manifest.read_text(encoding="utf-8"))
    assert claude_after["platform"] == "claude-code"
    assert cursor_data["platform"] == "cursor"

    owned_before = set(claude_before.get("owned_paths") or [])
    owned_after = set(claude_after.get("owned_paths") or [])
    assert owned_before, "precondition: claude-code deploy recorded ownership"
    assert owned_after == owned_before, (
        "cursor deploy mutated claude-code's owned_paths.\n"
        f"  lost : {sorted(owned_before - owned_after)}\n"
        f"  extra: {sorted(owned_after - owned_before)}"
    )
    assert ".claude/skills/demo-skill" in owned_after
    assert "CLAUDE.md" in owned_after
    # Co-ownership premise for the cross-platform prune protection contract.
    assert ".claude/skills/demo-skill" in set(cursor_data.get("owned_paths") or [])
    assert "AGENTS.md" in set(cursor_data.get("owned_paths") or [])


# ---------------------------------------------------------------------------
# 2. Redeploying one platform leaves the other's artefacts unchanged
# ---------------------------------------------------------------------------


def test_redeploy_one_platform_keeps_other_platform_bytes_intact(tmp_path: Path) -> None:
    """A claude-code redeploy must not rewrite any cursor-exclusive artefact
    (``.cursor/`` tree, AGENTS.md) nor cursor's deploy record."""
    root = _init_claude_cursor_project(tmp_path)
    _deploy(root, "claude-code")
    _deploy(root, "cursor")

    cursor_tree_before = _tree_digest(root / ".cursor")
    assert cursor_tree_before, "precondition: cursor deploy produced .cursor/ artefacts"
    agents_md_before = _file_digest(root / "AGENTS.md")
    manifest_before = _file_digest(_manifest_path(root, "cursor"))
    state_before = _file_digest(_state_path(root, "cursor"))

    _deploy(root, "claude-code")

    assert _tree_digest(root / ".cursor") == cursor_tree_before, (
        "claude-code redeploy mutated files under .cursor/"
    )
    assert _file_digest(root / "AGENTS.md") == agents_md_before, (
        "claude-code redeploy rewrote cursor's AGENTS.md"
    )
    assert _file_digest(_manifest_path(root, "cursor")) == manifest_before, (
        "claude-code redeploy rewrote cursor's manifest.json"
    )
    assert _file_digest(_state_path(root, "cursor")) == state_before, (
        "claude-code redeploy rewrote cursor's state.json"
    )


# ---------------------------------------------------------------------------
# 3. Shared path survives prune until its last owner deploys
# ---------------------------------------------------------------------------


def test_shared_skill_pruned_only_by_last_owning_platform(tmp_path: Path) -> None:
    """A skill co-owned by claude-code and cursor under ``.claude/skills``
    survives a cursor deploy after source removal (claude-code still claims
    it) and is pruned by the subsequent claude-code deploy."""
    root = _init_claude_cursor_project(tmp_path)
    _deploy(root, "claude-code")
    _deploy(root, "cursor")

    shared = root / ".claude" / "skills" / "demo-skill"
    assert shared.is_dir(), "precondition: both platforms deployed the shared skill"

    shutil.rmtree(root / ".cataforge" / "skills" / "demo-skill")

    _deploy(root, "cursor")
    assert shared.is_dir(), (
        "cursor deploy pruned .claude/skills/demo-skill while claude-code's "
        "manifest still declares it — cross-platform prune protection failed"
    )

    _deploy(root, "claude-code")
    assert not shared.exists(), (
        "claude-code deploy (last remaining owner, source gone, cursor's "
        "manifest no longer claims it) failed to prune the shared skill"
    )


# ---------------------------------------------------------------------------
# 4. Legacy single-slot records migrate idempotently
# ---------------------------------------------------------------------------


def test_legacy_single_slot_records_migrate_idempotently(tmp_path: Path) -> None:
    """A deploy removes the legacy ``.deploy-state`` / ``.deploy-manifest.json``
    pair, materialises the per-platform records, and a second deploy is a
    no-op on that migration."""
    root = _init_project(
        tmp_path,
        framework=_framework_v2("claude-code", ["claude-code"]),
        profiles={"claude-code": _CLAUDE_PROFILE},
    )
    legacy_state = root / ".cataforge" / ".deploy-state"
    legacy_manifest = root / ".cataforge" / ".deploy-manifest.json"
    legacy_state.write_text(json.dumps({"platform": "claude-code"}), encoding="utf-8")
    legacy_manifest.write_text(
        json.dumps(
            {
                "manifest_version": 1,
                "platform": "claude-code",
                "owned_paths": [
                    ".claude/agents/orchestrator.md",
                    ".claude/commands/bootstrap.md",
                ],
            }
        ),
        encoding="utf-8",
    )

    _deploy(root, "claude-code")

    assert not legacy_state.exists(), "legacy .deploy-state survived migration"
    assert not legacy_manifest.exists(), "legacy .deploy-manifest.json survived migration"
    manifest_file = _manifest_path(root, "claude-code")
    state_file = _state_path(root, "claude-code")
    assert manifest_file.is_file() and state_file.is_file()
    manifest_run1 = json.loads(manifest_file.read_text(encoding="utf-8"))
    state_run1 = json.loads(state_file.read_text(encoding="utf-8"))
    assert manifest_run1["platform"] == "claude-code"
    assert state_run1["platform"] == "claude-code"

    _deploy(root, "claude-code")

    assert not legacy_state.exists() and not legacy_manifest.exists()
    manifest_run2 = json.loads(manifest_file.read_text(encoding="utf-8"))
    state_run2 = json.loads(state_file.read_text(encoding="utf-8"))
    assert manifest_run2 == manifest_run1, (
        "second deploy after migration changed the per-platform manifest"
    )
    assert state_run2 == state_run1


# ---------------------------------------------------------------------------
# 5. Deploy lock rejects a live concurrent holder
# ---------------------------------------------------------------------------


def test_deploy_lock_rejects_fresh_holder_then_reacquires(tmp_path: Path) -> None:
    """A fresh foreign lock payload makes ``Deployer.deploy_lock`` fail fast
    with LockHeldError; removing the lock lets the next acquisition succeed."""
    (tmp_path / ".cataforge").mkdir()
    cfg = ConfigManager(tmp_path)
    lock_path = tmp_path / ".cataforge" / "state" / "locks" / "deploy.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(
        json.dumps({"owner": "other-deploy", "pid": 424242, "created_at": time.time()}),
        encoding="utf-8",
    )

    with pytest.raises(LockHeldError), Deployer.deploy_lock(cfg):
        pass

    lock_path.unlink()

    with Deployer.deploy_lock(cfg):
        assert lock_path.is_file(), "acquired lock did not materialise its payload file"
    assert not lock_path.exists(), "lock file lingered after release"


# ---------------------------------------------------------------------------
# 6 + 7. Shared AGENTS.md renders from the declared audience set
# ---------------------------------------------------------------------------


def _init_shared_agents_project(root: Path) -> Path:
    return _init_project(
        root,
        framework=_framework_v2("codex", ["codex", "cursor"]),
        profiles={
            "codex": _shared_agents_md_profile("codex", "Codex CLI"),
            "cursor": _shared_agents_md_profile("cursor", "Cursor"),
        },
    )


def test_shared_agents_md_bytes_stable_across_deploy_order(tmp_path: Path) -> None:
    """Two projects declaring targets [codex, cursor] end with byte-identical
    AGENTS.md whether deployed cursor→codex or codex→cursor."""
    project_a = _init_shared_agents_project(tmp_path / "proj_a")
    project_b = _init_shared_agents_project(tmp_path / "proj_b")

    _deploy(project_a, "cursor")
    _deploy(project_a, "codex")

    _deploy(project_b, "codex")
    _deploy(project_b, "cursor")

    bytes_a = (project_a / "AGENTS.md").read_bytes()
    bytes_b = (project_b / "AGENTS.md").read_bytes()
    assert bytes_a == bytes_b, (
        "AGENTS.md bytes depend on platform deploy order — audience rendering "
        "is not stable across the declared target set"
    )


def test_runtime_field_lists_declared_audience_platforms(tmp_path: Path) -> None:
    """The shared AGENTS.md ``运行时:`` field carries the full audience set
    (codex + cursor) and no undeclared platform."""
    root = _init_shared_agents_project(tmp_path / "proj")
    _deploy(root, "cursor")
    _deploy(root, "codex")

    text = (root / "AGENTS.md").read_text(encoding="utf-8")
    runtime_lines = [line for line in text.splitlines() if line.strip().startswith("- 运行时:")]
    assert runtime_lines, f"AGENTS.md carries no 运行时 field:\n{text[:500]}"
    line = runtime_lines[0]
    assert "codex" in line, line
    assert "cursor" in line, line
    assert "claude-code" not in line, line


# ---------------------------------------------------------------------------
# 8. Fresh secondary instruction file seeds runtime state from the primary
# ---------------------------------------------------------------------------


def test_fresh_agents_md_seeds_project_state_from_primary(tmp_path: Path) -> None:
    """First codex deploy on a project whose CLAUDE.md (default platform's
    primary) carries live §项目状态 content seeds that content into the new
    AGENTS.md via section-merge instead of template placeholders."""
    root = _init_project(
        tmp_path,
        framework=_framework_v2("claude-code", ["claude-code", "codex"]),
        profiles={
            "claude-code": _CLAUDE_PROFILE,
            "codex": _CODEX_SECTION_MERGE_PROFILE,
        },
    )
    _deploy(root, "claude-code")

    claude_md = root / "CLAUDE.md"
    marker = "MARKER-PROJECTION-SEED-4711"
    lines = claude_md.read_text(encoding="utf-8").splitlines(keepends=True)
    idx = next((i for i, line in enumerate(lines) if line.startswith("## 项目状态")), None)
    assert idx is not None, "rendered CLAUDE.md lacks a ## 项目状态 section"
    lines.insert(idx + 1, f"\n- 独特标记: {marker}\n")
    claude_md.write_text("".join(lines), encoding="utf-8")

    _deploy(root, "codex")

    agents_md = root / "AGENTS.md"
    assert agents_md.is_file(), "codex deploy did not create AGENTS.md"
    text = agents_md.read_text(encoding="utf-8")
    assert "## 项目状态" in text
    state_section = text.split("## 项目状态", 1)[1].split("\n## ", 1)[0]
    assert marker in state_section, (
        "AGENTS.md §项目状态 was not seeded from the primary CLAUDE.md — "
        "the marker written into the primary's runtime section is missing"
    )
