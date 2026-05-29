"""Tests for the unified ``deploy_overrides_rules`` flow.

Pins the per-platform wrapping behaviour introduced by Phase C-1: every
adapter scans ``.cataforge/platforms/{platform_id}/overrides/rules/*.md``
through the same base method, but the ``_wrap_rule_for_platform`` hook
decides where each rule lands (and in what format).

The four platforms split into three behaviours:

* **cursor** wraps as ``.cursor/rules/<name>.mdc`` with ``alwaysApply: true``
* **claude-code / codex** copy verbatim to ``<platform>/rules/<name>.md``
  (target taken from ``rules_distribution.target`` in profile.yaml)
* **opencode** returns ``None`` from the hook — override rules are
  registered in-place via ``opencode.json#instructions``, not copied
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cataforge.adapter.platform.registry import get_adapter


@pytest.fixture()
def with_override_rule(tmp_path: Path) -> Path:
    """Create a tmp project with one fake override rule for each platform."""
    cataforge_dir = tmp_path / ".cataforge"
    for pid in ("cursor", "codex", "claude-code", "opencode"):
        rules_dir = cataforge_dir / "platforms" / pid / "overrides" / "rules"
        rules_dir.mkdir(parents=True, exist_ok=True)
        (rules_dir / "sample-fallback.md").write_text(
            "# Sample Fallback Rule\n\nbody-content\n", encoding="utf-8"
        )
    return tmp_path


def _platforms_dir(repo_root: Path) -> Path:
    """Return the real repo's platforms dir so adapters load production profiles."""
    return repo_root / ".cataforge" / "platforms"


def test_cursor_wraps_override_rule_as_mdc(with_override_rule: Path) -> None:
    """Cursor's hook produces .cursor/rules/<name>.mdc with alwaysApply."""
    adapter = get_adapter("cursor", _platforms_dir(Path.cwd()))
    actions = adapter.deploy_overrides_rules(with_override_rule, dry_run=False)

    out = with_override_rule / ".cursor" / "rules" / "sample-fallback.mdc"
    assert out.is_file(), actions
    body = out.read_text(encoding="utf-8")
    assert "alwaysApply: true" in body
    assert "body-content" in body
    assert any("→ .cursor/rules/sample-fallback.mdc" in a for a in actions)


def test_codex_copies_override_rule_as_markdown(with_override_rule: Path) -> None:
    """Codex uses the base default — copies verbatim to .codex/rules/.

    Closes the silent-loss path that PR #168 left open: prompt_instruction /
    prompt_checklist files now actually land in the platform's declared
    rule directory instead of orbiting unused under overrides/rules/.
    """
    adapter = get_adapter("codex", _platforms_dir(Path.cwd()))
    actions = adapter.deploy_overrides_rules(with_override_rule, dry_run=False)

    out = with_override_rule / ".codex" / "rules" / "sample-fallback.md"
    assert out.is_file(), actions
    assert out.read_text(encoding="utf-8") == "# Sample Fallback Rule\n\nbody-content\n"


def test_claude_code_copies_override_rule_as_markdown(with_override_rule: Path) -> None:
    """Claude Code uses base default — copies to .claude/rules/."""
    adapter = get_adapter("claude-code", _platforms_dir(Path.cwd()))
    actions = adapter.deploy_overrides_rules(with_override_rule, dry_run=False)

    out = with_override_rule / ".claude" / "rules" / "sample-fallback.md"
    assert out.is_file(), actions


def test_opencode_skips_file_write(with_override_rule: Path) -> None:
    """OpenCode's hook returns None — no per-file write happens.

    Override rules are registered in-place via opencode.json#instructions
    glob (declared in profile.yaml#rules_distribution.files); copying to a
    platform-native directory would duplicate the source.
    """
    adapter = get_adapter("opencode", _platforms_dir(Path.cwd()))
    actions = adapter.deploy_overrides_rules(with_override_rule, dry_run=False)

    # No new file under any plausible target
    assert not (with_override_rule / ".opencode" / "rules").exists()
    assert not (with_override_rule / "opencode.json").exists()
    # But the SKIP line is surfaced so the deploy log explains the no-op
    assert any("SKIP" in a and "sample-fallback" in a for a in actions), actions


def test_missing_overrides_dir_returns_empty_actions(tmp_path: Path) -> None:
    """No directory → no work, no error."""
    adapter = get_adapter("cursor", _platforms_dir(Path.cwd()))
    actions = adapter.deploy_overrides_rules(tmp_path, dry_run=False)
    assert actions == []


def test_dry_run_writes_no_files(with_override_rule: Path) -> None:
    """dry_run keeps deploy previewable."""
    adapter = get_adapter("cursor", _platforms_dir(Path.cwd()))
    actions = adapter.deploy_overrides_rules(with_override_rule, dry_run=True)
    assert not (with_override_rule / ".cursor" / "rules").exists()
    assert any("would deploy" in a for a in actions)


def test_opencode_profile_declares_overrides_glob() -> None:
    """OpenCode's instructions glob must cover the overrides/rules tree
    so the in-place registration story holds end-to-end.

    Guards against someone splitting the rules_distribution.files list and
    accidentally orphaning override rules.
    """
    import yaml

    profile = yaml.safe_load(
        (Path.cwd() / ".cataforge" / "platforms" / "opencode" / "profile.yaml").read_text(
            encoding="utf-8"
        )
    )
    files = profile["context_injection"]["rules_distribution"]["files"]
    assert ".cataforge/platforms/opencode/overrides/rules/*.md" in files
