"""Error-path tests for the Deployer."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from cataforge.adapter.platform.registry import clear_cache
from cataforge.core.config import ConfigManager
from cataforge.runtime.deploy.deployer import Deployer
from tests.profile_factory import typed_profile

# ---------------------------------------------------------------------------
# Shared helpers (mirrors test_deployer.py style)
# ---------------------------------------------------------------------------


def _write_profile(base: Path, platform_id: str, profile: dict) -> None:
    p = base / ".cataforge" / "platforms" / platform_id
    p.mkdir(parents=True, exist_ok=True)
    (p / "profile.yaml").write_text(yaml.safe_dump(typed_profile(profile)), encoding="utf-8")


def _init_project(tmp_path: Path) -> Path:
    root = tmp_path
    cf = root / ".cataforge"
    cf.mkdir(exist_ok=True)
    (cf / "framework.json").write_text(
        json.dumps({"version": "0.1.0", "runtime": {"platform": "cursor"}}),
        encoding="utf-8",
    )
    (cf / "PROJECT-STATE.md").write_text("运行时: {platform}\n", encoding="utf-8")
    (cf / "rules").mkdir(exist_ok=True)
    (cf / "rules" / "COMMON-RULES.md").write_text("# common\n", encoding="utf-8")
    (cf / "agents").mkdir(exist_ok=True)
    (cf / "agents" / "orchestrator").mkdir(exist_ok=True)
    (cf / "agents" / "orchestrator" / "AGENT.md").write_text(
        "---\nname: orchestrator\ntools: file_read\n---\ntext\n",
        encoding="utf-8",
    )
    (cf / "hooks").mkdir(exist_ok=True)
    (cf / "hooks" / "hooks.yaml").write_text("schema_version: 2\nhooks: {}\n", encoding="utf-8")
    (cf / "mcp").mkdir(exist_ok=True)
    return root


def _minimal_profile(platform_id: str, path: str = "CLAUDE.md") -> dict:
    return {
        "platform_id": platform_id,
        "display_name": platform_id.capitalize(),
        "tool_map": {"file_read": "Read"},
        "agent_definition": {
            "format": "yaml-frontmatter",
            "scan_dirs": [".claude/agents"],
            "needs_deploy": False,
        },
        "instruction_file": {
            "reads_claude_md": False,
            "targets": [{"type": "project_state_copy", "path": path}],
        },
        "dispatch": {"tool_name": "Agent", "is_async": False},
        "hooks": {
            "config_format": None,
            "config_path": None,
            "event_map": {},
            "degradation": {},
        },
    }


# ---------------------------------------------------------------------------
# (a) Unsupported instruction_file type → action contains "SKIP"
# ---------------------------------------------------------------------------


def test_unknown_instruction_type_emits_skip_action(tmp_path: Path) -> None:
    root = _init_project(tmp_path)
    profile = _minimal_profile("claude-code")
    profile["instruction_file"]["targets"] = [{"type": "magic_unknown_type", "path": "CLAUDE.md"}]
    _write_profile(root, "claude-code", profile)

    clear_cache()
    deployer = Deployer(ConfigManager(root))
    actions = deployer.deploy("claude-code")

    skip_actions = [a for a in actions if "SKIP" in a and "magic_unknown_type" in a]
    assert skip_actions, f"expected a SKIP action mentioning 'magic_unknown_type', got: {actions}"


# ---------------------------------------------------------------------------
# (b) Invalid on_conflict value → action contains "SKIP" with field name
# ---------------------------------------------------------------------------


def test_invalid_on_conflict_emits_skip_with_field_name(tmp_path: Path) -> None:
    root = _init_project(tmp_path)
    profile = _minimal_profile("claude-code")
    profile["instruction_file"]["targets"] = [
        {
            "type": "project_state_copy",
            "path": "CLAUDE.md",
            "on_conflict": "not_a_valid_value",
        }
    ]
    _write_profile(root, "claude-code", profile)

    clear_cache()
    deployer = Deployer(ConfigManager(root))
    actions = deployer.deploy("claude-code")

    skip_actions = [a for a in actions if "SKIP" in a and "on_conflict" in a]
    assert skip_actions, f"expected a SKIP action mentioning 'on_conflict', got: {actions}"


# ---------------------------------------------------------------------------
# (c) MCP yaml format error → spec is silently skipped (registry logs warning,
#     deploy still completes without raising, problematic spec absent from output)
# ---------------------------------------------------------------------------


def test_malformed_mcp_yaml_does_not_raise(tmp_path: Path) -> None:
    root = _init_project(tmp_path)
    profile = _minimal_profile("claude-code")
    _write_profile(root, "claude-code", profile)

    mcp_dir = root / ".cataforge" / "mcp"
    mcp_dir.mkdir(exist_ok=True)
    (mcp_dir / "bad.yaml").write_text(": invalid: yaml: : \n", encoding="utf-8")

    clear_cache()
    deployer = Deployer(ConfigManager(root))
    # Must not raise even when MCP spec is malformed
    actions = deployer.deploy("claude-code")
    assert isinstance(actions, list)


# ---------------------------------------------------------------------------
# (d) File write failure → PermissionError propagates (no silent swallow)
# ---------------------------------------------------------------------------


def test_hook_generation_failure_logs_traceback_and_continues(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """When ``generate_platform_hooks`` raises, the action log must:

    1. Surface a terse one-line message including the exception class.
    2. Persist the FULL traceback to the logger so CI / doctor pick it up.
    3. Not abort the rest of the deploy.

    Pre-fix the deployer logged at WARN with only ``str(e)``; missing
    plugin dependencies and AttributeErrors from version drift looked
    identical to "config missing" failures, leaving the user with
    nothing actionable. Post-fix the ``logger.exception`` call records
    the traceback at ERROR.
    """
    import logging

    root = _init_project(tmp_path)
    profile = _minimal_profile("claude-code")
    # Override the hooks block so _deploy_hooks actually runs (the
    # minimal profile sets config_format=None which short-circuits the
    # entire hook deploy branch before generate_platform_hooks is ever
    # called).
    profile["hooks"] = {
        "config_format": "json",
        "config_path": ".claude/settings.json",
        "event_map": {},
        "degradation": {},
    }
    _write_profile(root, "claude-code", profile)

    clear_cache()
    deployer = Deployer(ConfigManager(root))

    def _exploding_generate(_adapter):
        # AttributeError exercises the (ImportError, AttributeError)
        # branch and its plugin-specific hint.
        raise AttributeError("simulated plugin method removed in upstream")

    caplog.set_level(logging.ERROR, logger="cataforge.runtime.deploy.deployer")
    with patch(
        "cataforge.runtime.hook.bridge.generate_platform_hooks",
        side_effect=_exploding_generate,
    ):
        actions = deployer.deploy("claude-code")

    # Action log carries the terse one-liner.
    assert any(
        "hooks: generation failed" in a
        and "AttributeError" in a
        and "simulated plugin method removed" in a
        for a in actions
    ), f"action log missing diagnostic; got {actions!r}"

    # Logger captured the full traceback.
    hook_records = [r for r in caplog.records if "hook generation failed" in r.getMessage().lower()]
    assert hook_records, f"logger.exception must record the failure; got {caplog.records!r}"
    assert hook_records[0].exc_info is not None, (
        "exc_info must be attached so the traceback is preserved"
    )


def test_write_failure_propagates(tmp_path: Path) -> None:
    root = _init_project(tmp_path)
    profile = _minimal_profile("claude-code")
    _write_profile(root, "claude-code", profile)

    clear_cache()
    deployer = Deployer(ConfigManager(root))

    # The instruction-file write routes through ``atomic_write_text`` (LF +
    # atomic), so a failure there must still propagate out of deploy. Patch
    # the helper in the instructions step namespace rather than ``Path.write_text``.
    from cataforge.runtime.deploy.steps import instructions as instr_mod

    real_atomic = instr_mod.atomic_write_text

    def failing_write(path: Path, data: str, **kwargs):
        if path.name == "CLAUDE.md":
            raise PermissionError(f"no write permission: {path}")
        return real_atomic(path, data, **kwargs)

    with (
        patch.object(instr_mod, "atomic_write_text", failing_write),
        pytest.raises(PermissionError),
    ):
        deployer.deploy("claude-code")


# ---------------------------------------------------------------------------
# (e) Missing PROJECT-STATE.md → P1 self-heal restores or SKIP otherwise
# ---------------------------------------------------------------------------


def test_missing_project_state_md_yields_skip_when_self_heal_absent(
    tmp_path: Path, monkeypatch
) -> None:
    """Deploy must not crash when PROJECT-STATE.md is missing AND the
    bundled scaffold cannot supply a replacement.

    Two behaviours are valid:
    * **Self-heal succeeds** (production: wheel ships PROJECT-STATE.md) →
      deploy writes CLAUDE.md normally, no SKIP. Verified in
      ``test_idempotency.py``.
    * **Self-heal can't help** (this test: scaffold faked empty) →
      deploy emits a SKIP action for the missing instruction source
      instead of falling over.
    """
    root = _init_project(tmp_path)
    # Remove the PROJECT-STATE.md that _init_project created
    (root / ".cataforge" / "PROJECT-STATE.md").unlink()

    # Point ``_scaffold_root`` at an empty dir so the P1 self-heal has
    # nothing to restore from — that puts deploy on the SKIP branch.
    fake_scaffold = tmp_path / "_empty_scaffold"
    fake_scaffold.mkdir()
    import cataforge.core.scaffold as scaffold_mod

    monkeypatch.setattr(scaffold_mod, "_scaffold_root", lambda: fake_scaffold)

    profile = _minimal_profile("claude-code")
    _write_profile(root, "claude-code", profile)

    clear_cache()
    deployer = Deployer(ConfigManager(root))
    actions = deployer.deploy("claude-code")

    skip_actions = [a for a in actions if "SKIP" in a and "PROJECT-STATE" in a]
    assert skip_actions, f"expected a SKIP action for missing PROJECT-STATE.md, got: {actions}"
