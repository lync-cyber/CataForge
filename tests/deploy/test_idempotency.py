"""End-to-end idempotency tests for `cataforge deploy`.

These tests pin the contract: a user can mutate ``.claude/`` or
``.cataforge/`` between deploys and the next ``cataforge deploy`` must
either preserve their changes (when user-authored) or restore the
canonical state (when scaffold content was deleted).

The bugs these tests document:

* **B1/B2 — deletion through symlink/junction destroys source**.
  On Windows non-Dev-Mode the per-skill ``.claude/skills/<name>`` is a
  junction; deleting a file inside removes the source under
  ``.cataforge/skills/<name>/``. The next deploy must restore the source
  from the bundled scaffold (P1 plan A).
* **B3a — user-authored slash command nuked**.
  ``deploy_commands`` prune historically deleted any ``*.md`` in
  ``.claude/commands/`` without a source counterpart, killing
  hand-authored wrappers like the dogfood ``framework-issue-resolve.md``.
* **B3b — user-authored skill subdir nuked**.
  ``deploy_skills`` prune historically deleted any subdir in
  ``.claude/skills/`` without a source counterpart, killing per-project
  user skills.

The fix lives across three pieces:
  - ``cataforge.runtime.deploy.manifest`` — records which paths a deploy claims
  - manifest-scoped prune in each ``deploy_*`` method
  - scaffold self-heal at deploy entry (``copy_scaffold_to(force=False)``)
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import yaml

from cataforge.adapter.platform.registry import clear_cache
from cataforge.core.config import ConfigManager
from cataforge.runtime.deploy.deployer import Deployer

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


def _init_project(tmp_path: Path) -> Path:
    """Build a minimal but realistic ``.cataforge/`` scaffold for claude-code.

    Mirrors the shape ``cataforge setup`` produces: framework.json,
    PROJECT-STATE.md, one agent, one skill (with a non-SKILL.md sibling
    file to test through-junction deletes), one command, hooks spec.
    """
    root = tmp_path
    cf = root / ".cataforge"
    cf.mkdir(exist_ok=True)
    (cf / "framework.json").write_text(
        json.dumps({"version": "0.1.0", "runtime": {"platform": "claude-code"}}),
        encoding="utf-8",
    )
    (cf / "PROJECT-STATE.md").write_text("platform: {platform}\n", encoding="utf-8")
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
    (cf / "skills" / "demo-skill" / "helper.md").write_text(
        "helper content\n", encoding="utf-8"
    )
    (cf / "commands").mkdir(exist_ok=True)
    (cf / "commands" / "bootstrap.md").write_text(
        "---\ndescription: bootstrap\n---\nbody\n", encoding="utf-8"
    )

    pdir = cf / "platforms" / "claude-code"
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "profile.yaml").write_text(yaml.safe_dump(_CLAUDE_PROFILE), encoding="utf-8")
    return root


def _snapshot(root: Path, rel_paths: list[str]) -> dict[str, object]:
    """Capture state for idempotency comparison.

    For files we record sha256(bytes); for links the readlink target; for
    dirs whether they exist. We deliberately ignore mtimes — the contract
    is "same logical state", not "same bytes-identical to the second".
    """
    import hashlib

    state: dict[str, object] = {}
    for rel in rel_paths:
        p = root / rel
        if not os.path.lexists(str(p)):
            state[rel] = "ABSENT"
            continue
        if p.is_symlink() or (hasattr(p, "is_junction") and p.is_junction()):
            try:
                state[rel] = f"LINK→{os.readlink(str(p))}"
            except OSError:
                state[rel] = "LINK→?"
        elif p.is_file():
            state[rel] = "FILE:" + hashlib.sha256(p.read_bytes()).hexdigest()
        elif p.is_dir():
            state[rel] = "DIR"
        else:
            state[rel] = "OTHER"
    return state


# ---------------------------------------------------------------------------
# Idempotency: two deploys produce the same state
# ---------------------------------------------------------------------------


def test_two_consecutive_deploys_produce_identical_state(tmp_path: Path) -> None:
    """The bedrock idempotency contract.

    Run deploy, snapshot. Run deploy again, snapshot. Assert identical.
    This catches any "second run does something the first didn't" drift —
    extra prune logs, duplicated MCP entries, lost orphan-detection, etc.
    """
    root = _init_project(tmp_path)
    clear_cache()
    Deployer(ConfigManager(root)).deploy("claude-code")

    rel_paths = [
        "CLAUDE.md",
        ".claude/agents/orchestrator.md",
        ".claude/commands/bootstrap.md",
        ".claude/skills/demo-skill",
        ".claude/rules",
    ]
    state_after_first = _snapshot(root, rel_paths)

    clear_cache()
    Deployer(ConfigManager(root)).deploy("claude-code")
    state_after_second = _snapshot(root, rel_paths)

    assert state_after_first == state_after_second, (
        "Second deploy mutated state that the first deploy already produced.\n"
        f"  first  : {state_after_first}\n"
        f"  second : {state_after_second}"
    )


# ---------------------------------------------------------------------------
# User-authored files must survive deploy (B3a, B3b, C1)
# ---------------------------------------------------------------------------


def test_user_authored_command_md_survives_deploy(tmp_path: Path) -> None:
    """``.claude/commands/<name>.md`` with no source counterpart must NOT
    be pruned.

    Catches the framework-issue-resolve dogfood case: the wrapper file
    is git-tracked (per ``.gitignore`` exception) and has no source
    under ``.cataforge/commands/``. Old behaviour: deploy nuked it on
    every run, because ``deploy_commands`` prune had no ownership check.
    """
    root = _init_project(tmp_path)
    clear_cache()
    Deployer(ConfigManager(root)).deploy("claude-code")

    wrapper = root / ".claude" / "commands" / "framework-issue-resolve.md"
    wrapper.write_text(
        "---\ndescription: dogfood wrapper\n---\nbody\n", encoding="utf-8"
    )

    clear_cache()
    Deployer(ConfigManager(root)).deploy("claude-code")

    assert wrapper.is_file(), (
        "User-authored .claude/commands/framework-issue-resolve.md was "
        "pruned by deploy — exactly the dogfood-killing bug we're fixing."
    )
    # And its content must be untouched.
    assert "dogfood wrapper" in wrapper.read_text(encoding="utf-8")


def test_user_authored_skill_subdir_survives_deploy(tmp_path: Path) -> None:
    """``.claude/skills/<user>/`` with no source counterpart must NOT
    be pruned.

    A user adding a per-project skill alongside CataForge skills must
    not have their work wiped on every deploy.
    """
    root = _init_project(tmp_path)
    clear_cache()
    Deployer(ConfigManager(root)).deploy("claude-code")

    user_skill = root / ".claude" / "skills" / "my-project-skill"
    user_skill.mkdir(parents=True)
    (user_skill / "SKILL.md").write_text(
        "---\nname: my-project-skill\n---\nuser skill\n", encoding="utf-8"
    )

    clear_cache()
    Deployer(ConfigManager(root)).deploy("claude-code")

    assert user_skill.is_dir(), (
        "User-authored .claude/skills/my-project-skill was pruned by deploy."
    )
    assert (user_skill / "SKILL.md").is_file()


# ---------------------------------------------------------------------------
# Orphan prune still works for things WE wrote previously
# ---------------------------------------------------------------------------


def test_orphan_from_prior_deploy_is_pruned_when_source_disappears(
    tmp_path: Path,
) -> None:
    """Regression: ownership-aware prune must still delete real orphans.

    Workflow:
      1. Deploy: source has ``cmd-a.md`` + ``cmd-b.md`` → both deployed.
      2. Remove ``cmd-b.md`` from source.
      3. Deploy: ``.claude/commands/cmd-b.md`` should be pruned (we wrote it).
    """
    root = _init_project(tmp_path)
    cmd_b = root / ".cataforge" / "commands" / "cmd-b.md"
    cmd_b.write_text("---\ndescription: cmd-b\n---\nbody\n", encoding="utf-8")

    clear_cache()
    Deployer(ConfigManager(root)).deploy("claude-code")
    assert (root / ".claude" / "commands" / "cmd-b.md").is_file()

    # Remove source — next deploy must clean up our prior write.
    cmd_b.unlink()

    clear_cache()
    Deployer(ConfigManager(root)).deploy("claude-code")
    assert not (root / ".claude" / "commands" / "cmd-b.md").exists(), (
        "Prune lost its teeth: a command we previously wrote is no longer "
        "in source but the deployed copy survived."
    )


def test_orphan_skill_from_prior_deploy_pruned_when_source_removed(
    tmp_path: Path,
) -> None:
    """Same orphan-prune regression check, for skills."""
    root = _init_project(tmp_path)
    extra_src = root / ".cataforge" / "skills" / "extra-skill"
    extra_src.mkdir()
    (extra_src / "SKILL.md").write_text(
        "---\nname: extra-skill\ndescription: x\n---\nbody\n", encoding="utf-8"
    )

    clear_cache()
    Deployer(ConfigManager(root)).deploy("claude-code")
    assert (root / ".claude" / "skills" / "extra-skill").exists()

    import shutil
    shutil.rmtree(extra_src)

    clear_cache()
    Deployer(ConfigManager(root)).deploy("claude-code")
    assert not os.path.lexists(
        str(root / ".claude" / "skills" / "extra-skill")
    ), "Skill we previously deployed lingered after its source disappeared."


# ---------------------------------------------------------------------------
# Single-file deployed artefacts get regenerated on user deletion
# ---------------------------------------------------------------------------


def test_deleted_agent_md_is_regenerated_on_redeploy(tmp_path: Path) -> None:
    """User deletes ``.claude/agents/orchestrator.md`` → next deploy restores."""
    root = _init_project(tmp_path)
    clear_cache()
    Deployer(ConfigManager(root)).deploy("claude-code")

    agent_md = root / ".claude" / "agents" / "orchestrator.md"
    assert agent_md.is_file()
    agent_md.unlink()

    clear_cache()
    Deployer(ConfigManager(root)).deploy("claude-code")
    assert agent_md.is_file(), "Deployed agent .md was not regenerated."


def test_deleted_command_md_is_regenerated_on_redeploy(tmp_path: Path) -> None:
    """User deletes ``.claude/commands/bootstrap.md`` → next deploy restores."""
    root = _init_project(tmp_path)
    clear_cache()
    Deployer(ConfigManager(root)).deploy("claude-code")

    cmd_md = root / ".claude" / "commands" / "bootstrap.md"
    assert cmd_md.is_file()
    cmd_md.unlink()

    clear_cache()
    Deployer(ConfigManager(root)).deploy("claude-code")
    assert cmd_md.is_file(), "Deployed command .md was not regenerated."


def test_deleted_claude_md_is_regenerated_on_redeploy(tmp_path: Path) -> None:
    """User deletes ``CLAUDE.md`` → next deploy restores."""
    root = _init_project(tmp_path)
    clear_cache()
    Deployer(ConfigManager(root)).deploy("claude-code")

    claude_md = root / "CLAUDE.md"
    assert claude_md.is_file()
    claude_md.unlink()

    clear_cache()
    Deployer(ConfigManager(root)).deploy("claude-code")
    assert claude_md.is_file(), "Deployed CLAUDE.md was not regenerated."


# ---------------------------------------------------------------------------
# Scaffold self-heal: deleted source files come back (P1 Plan A)
# ---------------------------------------------------------------------------


def _install_fake_scaffold(monkeypatch, contents: dict[str, bytes], tmp_path: Path) -> Path:
    """Monkeypatch ``_scaffold_root`` to return a controlled directory.

    Tests that exercise the scaffold-self-heal path need a deterministic
    source to restore from — the real wheel scaffold pulled in test would
    pollute the project with the entire bundled tree. Instead we build a
    minimal fake scaffold inside *tmp_path* and patch the resolver.
    """
    fake = tmp_path / "_fake_scaffold"
    fake.mkdir()
    for rel, body in contents.items():
        dst = fake / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(body)

    import cataforge.core.scaffold as scaffold_mod

    monkeypatch.setattr(scaffold_mod, "_scaffold_root", lambda: fake)
    return fake


def test_redeploy_restores_deleted_source_skill_file(
    tmp_path: Path, monkeypatch
) -> None:
    """The B1/B2 fix: when a file under ``.cataforge/`` goes missing
    (user delete, or junction-through-delete from ``.claude/skills/``),
    the next deploy restores it from the bundled scaffold.
    """
    root = _init_project(tmp_path)

    # Fake scaffold mirrors the same content the test fixture set up.
    _install_fake_scaffold(
        monkeypatch,
        {
            "skills/demo-skill/SKILL.md": (
                b"---\nname: demo-skill\ndescription: demo\n---\nbody\n"
            ),
            "skills/demo-skill/helper.md": b"helper content\n",
        },
        tmp_path,
    )

    clear_cache()
    Deployer(ConfigManager(root)).deploy("claude-code")

    helper = root / ".cataforge" / "skills" / "demo-skill" / "helper.md"
    assert helper.is_file()

    # Simulate what happens when the user navigates into the junction
    # and deletes the helper file — the source file dies.
    helper.unlink()
    assert not helper.exists()

    clear_cache()
    Deployer(ConfigManager(root)).deploy("claude-code")

    assert helper.is_file(), (
        "Source file deleted via junction-through-delete (or user delete) "
        "was NOT restored by deploy. P1 Plan A is supposed to make "
        "`cataforge deploy` self-heal by calling copy_scaffold_to(force=False)."
    )
    assert helper.read_text(encoding="utf-8") == "helper content\n"


def test_redeploy_does_not_overwrite_user_edits_to_source(
    tmp_path: Path, monkeypatch
) -> None:
    """Self-heal must NOT clobber user edits.

    ``copy_scaffold_to(force=False)`` only writes when target is absent,
    so user-edited source files survive. This test pins that contract.
    """
    root = _init_project(tmp_path)
    _install_fake_scaffold(
        monkeypatch,
        {
            "skills/demo-skill/SKILL.md": b"WHEEL CONTENT - should not appear\n",
        },
        tmp_path,
    )

    # User-edited content already on disk.
    user_skill = root / ".cataforge" / "skills" / "demo-skill" / "SKILL.md"
    user_skill.write_text("USER-EDITED CONTENT\n", encoding="utf-8")

    clear_cache()
    Deployer(ConfigManager(root)).deploy("claude-code")

    assert "USER-EDITED CONTENT" in user_skill.read_text(encoding="utf-8"), (
        "Scaffold self-heal incorrectly overwrote a user-edited source file."
    )


# ---------------------------------------------------------------------------
# Manifest persistence
# ---------------------------------------------------------------------------


def test_deploy_writes_manifest_file(tmp_path: Path) -> None:
    """Manifest must land at ``.cataforge/.deploy-manifest.json``."""
    root = _init_project(tmp_path)
    clear_cache()
    Deployer(ConfigManager(root)).deploy("claude-code")

    manifest = root / ".cataforge" / ".deploy-manifest.json"
    assert manifest.is_file(), "Deploy did not write the ownership manifest."
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data.get("platform") == "claude-code"
    owned = data.get("owned_paths") or []
    assert isinstance(owned, list)
    owned_set = set(owned)
    # Spot-check a few paths the deploy wrote.
    assert ".claude/agents/orchestrator.md" in owned_set
    assert ".claude/commands/bootstrap.md" in owned_set
    # Skill subdir or link — its rel path must be on the manifest.
    assert ".claude/skills/demo-skill" in owned_set
    assert "CLAUDE.md" in owned_set


def test_manifest_omits_user_authored_paths(tmp_path: Path) -> None:
    """The manifest must record only what *this* deploy wrote — not what
    happened to be on disk."""
    root = _init_project(tmp_path)
    # User-authored content pre-existing on disk.
    user_cmd = root / ".claude" / "commands" / "user-thing.md"
    user_cmd.parent.mkdir(parents=True, exist_ok=True)
    user_cmd.write_text("user\n", encoding="utf-8")

    clear_cache()
    Deployer(ConfigManager(root)).deploy("claude-code")

    manifest_path = root / ".cataforge" / ".deploy-manifest.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    owned_set = set(data.get("owned_paths") or [])
    assert ".claude/commands/user-thing.md" not in owned_set, (
        "Manifest erroneously claimed ownership of a user-authored file."
    )


# ---------------------------------------------------------------------------
# P2 --copy: materialise skills as independent copies
# ---------------------------------------------------------------------------


def test_force_copy_materialises_skills_as_independent_copies(
    tmp_path: Path,
) -> None:
    """With ``--copy`` (``force_copy=True``), a skill subdir is a real
    directory disconnected from the source. Deleting a file inside must
    NOT touch ``.cataforge/``.
    """
    root = _init_project(tmp_path)
    clear_cache()
    Deployer(ConfigManager(root)).deploy("claude-code", force_copy=True)

    skill_target = root / ".claude" / "skills" / "demo-skill"
    assert skill_target.is_dir()
    assert not skill_target.is_symlink()
    if hasattr(skill_target, "is_junction"):
        assert not skill_target.is_junction()

    # Delete from the copy.
    (skill_target / "helper.md").unlink()

    # Source survives — that's the whole point of --copy.
    src = root / ".cataforge" / "skills" / "demo-skill" / "helper.md"
    assert src.is_file(), (
        "Deleting through a --copy target wrongly propagated to source — "
        "the copy path is supposed to isolate IDE from source."
    )


def test_force_copy_redeploy_brings_back_deleted_file(tmp_path: Path) -> None:
    """Idempotency under ``--copy``: a file deleted from the copy is
    re-materialised on next deploy (because source is intact).
    """
    root = _init_project(tmp_path)
    clear_cache()
    Deployer(ConfigManager(root)).deploy("claude-code", force_copy=True)

    helper_copy = root / ".claude" / "skills" / "demo-skill" / "helper.md"
    assert helper_copy.is_file()
    helper_copy.unlink()

    clear_cache()
    Deployer(ConfigManager(root)).deploy("claude-code", force_copy=True)
    assert helper_copy.is_file(), (
        "Second --copy deploy did not restore the deleted file inside the copy."
    )


# ---------------------------------------------------------------------------
# P3 --rebuild: purge prior-owned paths first
# ---------------------------------------------------------------------------


def test_rebuild_purges_prior_owned_then_redeploys(tmp_path: Path) -> None:
    """``--rebuild`` removes everything the prior manifest claimed, then
    re-deploys. User-authored files outside the manifest survive.
    """
    root = _init_project(tmp_path)
    clear_cache()
    Deployer(ConfigManager(root)).deploy("claude-code")

    # User-authored file outside the manifest.
    user_cmd = root / ".claude" / "commands" / "user-wrapper.md"
    user_cmd.write_text("---\ndescription: user\n---\nbody\n", encoding="utf-8")

    # CataForge-owned artefact that exists after the first deploy.
    owned_agent = root / ".claude" / "agents" / "orchestrator.md"
    assert owned_agent.is_file()

    clear_cache()
    actions = Deployer(ConfigManager(root)).deploy("claude-code", rebuild=True)

    # The rebuild step itself surfaces a purge action.
    assert any("rebuild-purged" in a for a in actions), (
        f"--rebuild should have surfaced rebuild-purged actions; got: {actions}"
    )

    # The owned artefact was purged then re-rendered — present at end.
    assert owned_agent.is_file()
    # The user-authored file outside the manifest survived.
    assert user_cmd.is_file()


def test_rebuild_refuses_to_purge_prior_other_platform(tmp_path: Path) -> None:
    """``--rebuild`` must NOT purge paths whose ownership stake belongs
    to a different platform than the one being deployed.

    Concretely: if a user deployed Cursor previously (recording paths
    under ``.cursor/`` in the manifest) and then runs
    ``cataforge deploy --platform=claude-code --rebuild``, the prior
    manifest still names ``.cursor/...`` paths. Pre-fix the rebuild
    purge blasted those away regardless — silent data loss for any
    hand-edits the user made under ``.cursor/``. Post-fix the deployer
    refuses with a clear warning, leaving the user to clean the old
    platform's tree manually if they want a true switch.
    """
    from cataforge.runtime.deploy.manifest import _MANIFEST_REL

    root = _init_project(tmp_path)
    clear_cache()

    # Plant a manifest that records a previous cursor deploy with
    # paths that exist on disk (we use real touched files so the purge
    # would actually try to delete them if the platform check failed).
    cursor_owned_a = root / ".cursor" / "rules" / "owned-a.mdc"
    cursor_owned_b = root / ".cursor" / "commands" / "owned-b.md"
    for p in (cursor_owned_a, cursor_owned_b):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("cursor-era content", encoding="utf-8")

    manifest_path = root / _MANIFEST_REL
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "platform": "cursor",
                "owned_paths": [
                    str(cursor_owned_a.relative_to(root)).replace("\\", "/"),
                    str(cursor_owned_b.relative_to(root)).replace("\\", "/"),
                ],
            },
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )

    actions = Deployer(ConfigManager(root)).deploy("claude-code", rebuild=True)

    # Warning was surfaced and the prior platform's files survived.
    assert any(
        "rebuild-purge skipped" in a and "'cursor'" in a and "'claude-code'" in a
        for a in actions
    ), f"warning must explain the refusal; got: {actions}"
    assert cursor_owned_a.is_file(), (
        ".cursor/-owned file was purged despite the platform mismatch — "
        "this is the silent data-loss bug C3 fixes."
    )
    assert cursor_owned_b.is_file()
    # No purge action recorded.
    assert not any("rebuild-purged" in a for a in actions), actions


def test_rebuild_on_fresh_project_is_safe_noop(tmp_path: Path) -> None:
    """``--rebuild`` on a project that never deployed before must not
    error and must not delete anything (no manifest → nothing to purge)."""
    root = _init_project(tmp_path)
    clear_cache()
    actions = Deployer(ConfigManager(root)).deploy("claude-code", rebuild=True)

    assert any(
        "rebuild: no prior manifest" in a for a in actions
    ), f"--rebuild on fresh project should report no-op; got: {actions}"
    # Deploy still produces the canonical state.
    assert (root / ".claude" / "agents" / "orchestrator.md").is_file()
