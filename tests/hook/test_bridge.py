"""Tests for hook bridge."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

from cataforge.adapter.platform.registry import get_adapter
from cataforge.runtime.hook.bridge import generate_platform_hooks
from tests.profile_factory import typed_profile

_QUOTED_INTERP = f'"{Path(sys.executable).as_posix()}"'


@pytest.fixture()
def project_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create project with hooks.yaml and platform profiles.

    Chdirs into *tmp_path* so ``find_project_root`` sees the fixture's
    minimal hooks.yaml instead of walking up to the cataforge repo itself.
    """
    cataforge_dir = tmp_path / ".cataforge"
    cataforge_dir.mkdir()
    monkeypatch.chdir(tmp_path)

    (cataforge_dir / "framework.json").write_text(
        json.dumps({"version": "0.1.0", "runtime": {"platform": "claude-code"}}),
        encoding="utf-8",
    )

    hooks_dir = cataforge_dir / "hooks"
    hooks_dir.mkdir()
    hooks_spec = {
        "schema_version": 2,
        "hooks": {
            "PreToolUse": [
                {
                    "matcher_capability": "shell_exec",
                    "script": "guard_dangerous",
                    "type": "block",
                }
            ],
            "PostToolUse": [
                {
                    "matcher_capability": "file_edit",
                    "script": "lint_format",
                    "type": "observe",
                }
            ],
        },
    }
    with open(hooks_dir / "hooks.yaml", "w", encoding="utf-8") as f:
        yaml.dump(hooks_spec, f)

    for pid, profile in {
        "claude-code": {
            "platform_id": "claude-code",
            "tool_map": {"shell_exec": "Bash", "file_edit": "Edit", "file_write": "Write"},
            "hooks": {
                "config_format": "json",
                "config_path": ".claude/settings.json",
                "entry_type": "command",
                "event_map": {"PreToolUse": "PreToolUse", "PostToolUse": "PostToolUse"},
                "tool_overrides": {"file_edit": "Edit|Write"},
                "degradation": {"guard_dangerous": "native", "lint_format": "native"},
            },
        },
        "cursor": {
            "platform_id": "cursor",
            "tool_map": {"shell_exec": "Shell", "file_edit": "Write", "file_write": "Write"},
            "hooks": {
                "config_format": "json",
                "config_path": ".cursor/hooks.json",
                "entry_type": "command",
                "event_map": {"PreToolUse": "preToolUse", "PostToolUse": "postToolUse"},
                "tool_overrides": {},
                "degradation": {"guard_dangerous": "native", "lint_format": "native"},
            },
        },
        "codex": {
            "platform_id": "codex",
            "tool_map": {"shell_exec": "shell", "file_edit": "apply_patch"},
            "hooks": {
                "config_format": "json",
                "config_path": ".codex/hooks.json",
                "entry_type": "command",
                "event_map": {"PreToolUse": "PreToolUse", "PostToolUse": "PostToolUse"},
                "tool_overrides": {"shell_exec": "Bash"},
                "degradation": {"guard_dangerous": "native", "lint_format": "degraded"},
            },
        },
    }.items():
        p = cataforge_dir / "platforms" / pid
        p.mkdir(parents=True)
        with open(p / "profile.yaml", "w", encoding="utf-8") as f:
            yaml.dump(typed_profile(profile), f)

    return tmp_path


class TestHookBridge:
    def test_real_codex_detect_correction_is_native_post_tool_use(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import cataforge.runtime.hook.bridge as bridge

        repo_root = Path(__file__).resolve().parents[2]
        hooks_yaml = repo_root / ".cataforge" / "hooks" / "hooks.yaml"
        monkeypatch.setattr(
            bridge,
            "load_hooks_spec",
            lambda _p=None: bridge.yaml.safe_load(hooks_yaml.read_text(encoding="utf-8")),
        )
        adapter = get_adapter("codex", repo_root / ".cataforge" / "platforms")

        hooks, warnings = generate_platform_hooks(adapter)

        correction = [
            group for group in hooks["PostToolUse"] if group["matcher"] == "request_user_input"
        ]
        assert len(correction) == 1
        assert not any("detect_correction" in warning for warning in warnings)

    def test_claude_code_hooks(self, project_dir: Path) -> None:
        platforms_dir = project_dir / ".cataforge" / "platforms"
        adapter = get_adapter("claude-code", platforms_dir)

        hooks, _warnings = generate_platform_hooks(adapter)

        assert "PreToolUse" in hooks
        pre = hooks["PreToolUse"]
        assert len(pre) == 1
        assert pre[0]["matcher"] == "Bash"
        cmd = pre[0]["hooks"][0]["command"]
        assert cmd.startswith(f"{_QUOTED_INTERP} ")
        assert "-m cataforge.runtime.hook.scripts.guard_dangerous" in cmd

    def test_claude_code_lint_format_matches_edit_and_write(self, project_dir: Path) -> None:
        """The file_edit hook must fire after both Edit and Write — a TDD GREEN
        sub-agent's primary output is a freshly `Write`-created file, which a
        bare `Edit` matcher would skip, so lint/format is deferred to the gate."""
        platforms_dir = project_dir / ".cataforge" / "platforms"
        adapter = get_adapter("claude-code", platforms_dir)

        hooks, _warnings = generate_platform_hooks(adapter)

        post = hooks["PostToolUse"]
        assert post[0]["matcher"] == "Edit|Write"

    def test_real_claude_code_profile_declares_both_edit_matchers(self) -> None:
        """Guard the shipped typed binding, not just the bridge mechanism."""
        repo_root = Path(__file__).resolve().parents[2]
        adapter = get_adapter("claude-code", repo_root / ".cataforge" / "platforms")

        binding = adapter.get_capability_binding("file_edit")
        assert binding is not None
        assert binding.hook_matchers == ["Edit", "Write"]

    def test_cursor_hooks_use_module_invocation(self, project_dir: Path) -> None:
        """Hooks run the deploying interpreter with -m cataforge.runtime.hook.scripts.<module>."""
        platforms_dir = project_dir / ".cataforge" / "platforms"
        adapter = get_adapter("cursor", platforms_dir)

        hooks, _warnings = generate_platform_hooks(adapter)

        assert "preToolUse" in hooks
        pre = hooks["preToolUse"]
        cmd = pre[0]["hooks"][0]["command"]
        assert cmd.startswith(f"{_QUOTED_INTERP} ")
        assert "-m cataforge.runtime.hook.scripts.guard_dangerous" in cmd

    def test_cursor_uses_platform_tool_names(self, project_dir: Path) -> None:
        platforms_dir = project_dir / ".cataforge" / "platforms"
        adapter = get_adapter("cursor", platforms_dir)

        hooks, _warnings = generate_platform_hooks(adapter)

        pre = hooks["preToolUse"]
        assert pre[0]["matcher"] == "Shell"  # not "Bash"

        post = hooks["postToolUse"]
        assert post[0]["matcher"] == "Write"  # not "Edit"

    def test_codex_binding_hook_matcher_used(self, project_dir: Path) -> None:
        """Binding hook matchers are independent from model-facing tool names."""
        platforms_dir = project_dir / ".cataforge" / "platforms"
        adapter = get_adapter("codex", platforms_dir)

        hooks, _warnings = generate_platform_hooks(adapter)

        # shell_exec tool="shell" but hook_matchers=["Bash"]
        pre = hooks["PreToolUse"]
        assert pre[0]["matcher"] == "Bash"

    def test_claude_code_hook_entry_type_is_command(self, project_dir: Path) -> None:
        """Claude Code's hook schema only accepts type: command.

        Regression guard: internal CataForge semantics (block / observe) must
        not leak into .claude/settings.json — if they did, Claude Code would
        silently ignore the hook and none of CataForge's guard/observer
        scripts would fire.
        """
        platforms_dir = project_dir / ".cataforge" / "platforms"
        adapter = get_adapter("claude-code", platforms_dir)

        hooks, _warnings = generate_platform_hooks(adapter)

        for event in ("PreToolUse", "PostToolUse"):
            for group in hooks.get(event, []):
                for entry in group["hooks"]:
                    assert entry["type"] == "command", (
                        f"{event} hook emitted invalid type {entry['type']!r}; "
                        "Claude Code only recognises 'command'."
                    )

    def test_cursor_and_codex_hook_entry_type_is_command(self, project_dir: Path) -> None:
        """Cursor / Codex JSON hook schemas also require type: command."""
        platforms_dir = project_dir / ".cataforge" / "platforms"
        for platform_id in ("cursor", "codex"):
            adapter = get_adapter(platform_id, platforms_dir)
            hooks, _warnings = generate_platform_hooks(adapter)
            for event_groups in hooks.values():
                for group in event_groups:
                    for entry in group["hooks"]:
                        assert entry["type"] == "command", (
                            f"{platform_id} emitted invalid type {entry['type']!r}"
                        )


class TestHookBridgeWarnings:
    """The bridge returns `(hooks, warnings)` so deploy/doctor can surface
    silent feature loss instead of swallowing it in a debug log."""

    def test_codex_degraded_hook_emits_warning(self, project_dir: Path) -> None:
        """Codex declares `lint_format: degraded` — the bridge must warn."""
        platforms_dir = project_dir / ".cataforge" / "platforms"
        adapter = get_adapter("codex", platforms_dir)

        _hooks, warnings = generate_platform_hooks(adapter)

        assert any("lint_format" in w and "degraded" in w for w in warnings), (
            f"expected a degradation warning for lint_format, got: {warnings}"
        )

    def test_native_hook_produces_no_warning(self, project_dir: Path) -> None:
        """Claude Code maps every canonical event natively — no warnings."""
        platforms_dir = project_dir / ".cataforge" / "platforms"
        adapter = get_adapter("claude-code", platforms_dir)

        _hooks, warnings = generate_platform_hooks(adapter)

        assert warnings == []

    def test_schema_version_newer_than_release_warns(
        self, project_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import cataforge.runtime.hook.bridge as bridge

        spec = {"schema_version": 999, "hooks": {}}
        monkeypatch.setattr(bridge, "load_hooks_spec", lambda _p=None: spec)

        platforms_dir = project_dir / ".cataforge" / "platforms"
        adapter = get_adapter("claude-code", platforms_dir)
        _hooks, warnings = generate_platform_hooks(adapter)

        assert any("schema_version=999" in w for w in warnings)
