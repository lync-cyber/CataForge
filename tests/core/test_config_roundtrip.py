"""Regression tests protecting framework.json from lossy rewrites.

Background
----------
Prior to the M1 fix, ``ConfigManager.set_runtime_platform`` went through a
``load() → mutate → _write()`` path where ``load()`` ran a Pydantic
round-trip (``model_validate(...).model_dump(...)``). The nested schemas
``FrameworkRuntime`` / ``FrameworkUpgradeSource`` / ``FrameworkUpgrade`` used
``extra='ignore'``, which silently dropped any key not declared in the
schema. Setting a platform therefore destroyed user-authored fields like
``upgrade.source.branch``, ``upgrade.source.token_env``, and the entire
``upgrade.state`` subtree.

These tests lock in that ``set_runtime_platform`` is a **true minimal
patch**: only ``runtime.platform`` may change; every other byte of the file
is preserved, including field order.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cataforge.core.config import ConfigManager


@pytest.fixture()
def rich_project(tmp_path: Path) -> Path:
    """A framework.json populated with every field real users customize."""
    cataforge_dir = tmp_path / ".cataforge"
    cataforge_dir.mkdir()

    # Deliberately use a field order different from Pydantic schema order so
    # any reordering shows up in the assertion.
    rich_config = {
        "version": "0.1.0",
        "runtime_api_version": "1.0",
        "runtime": {"platform": "claude-code"},
        "description": "User-authored description field (root-level extra).",
        "upgrade": {
            "source": {
                "type": "github",
                "repo": "user/fork",
                "branch": "develop",
                "token_env": "MY_CUSTOM_TOKEN_VAR",
            },
            "state": {
                "last_commit": "abc123",
                "last_version": "0.0.9",
                "last_upgrade_date": "2026-01-15",
            },
        },
        "constants": {"MAX_QUESTIONS_PER_BATCH": 7, "CUSTOM_USER_CONSTANT": "value"},
        "features": {"tdd-engine": {"min_version": "0.1.0", "auto_enable": True}},
        "migration_checks": [{"id": "mc-test", "description": "demo"}],
    }
    (cataforge_dir / "framework.json").write_text(
        json.dumps(rich_config, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return tmp_path


class TestSetRuntimePlatformPreservation:
    """``set_runtime_platform`` must touch exactly one field."""

    def test_upgrade_source_extras_preserved(self, rich_project: Path) -> None:
        cfg = ConfigManager(rich_project)
        cfg.set_runtime_platform("cursor")

        raw = json.loads(
            (rich_project / ".cataforge" / "framework.json").read_text(encoding="utf-8")
        )
        src = raw["upgrade"]["source"]
        assert src["type"] == "github"
        assert src["repo"] == "user/fork"
        assert src["branch"] == "develop"
        assert src["token_env"] == "MY_CUSTOM_TOKEN_VAR"

    def test_upgrade_state_preserved(self, rich_project: Path) -> None:
        cfg = ConfigManager(rich_project)
        cfg.set_runtime_platform("cursor")

        raw = json.loads(
            (rich_project / ".cataforge" / "framework.json").read_text(encoding="utf-8")
        )
        state = raw["upgrade"]["state"]
        assert state["last_commit"] == "abc123"
        assert state["last_version"] == "0.0.9"
        assert state["last_upgrade_date"] == "2026-01-15"

    def test_top_level_field_order_preserved(self, rich_project: Path) -> None:
        original = json.loads(
            (rich_project / ".cataforge" / "framework.json").read_text(encoding="utf-8")
        )
        original_keys = list(original.keys())

        cfg = ConfigManager(rich_project)
        cfg.set_runtime_platform("cursor")

        after = json.loads(
            (rich_project / ".cataforge" / "framework.json").read_text(encoding="utf-8")
        )
        assert list(after.keys()) == original_keys

    def test_only_runtime_platform_changes(self, rich_project: Path) -> None:
        original = json.loads(
            (rich_project / ".cataforge" / "framework.json").read_text(encoding="utf-8")
        )

        cfg = ConfigManager(rich_project)
        cfg.set_runtime_platform("codex")

        after = json.loads(
            (rich_project / ".cataforge" / "framework.json").read_text(encoding="utf-8")
        )

        # Mutate original's single expected change and assert full equality.
        original["runtime"]["platform"] = "codex"
        assert after == original

    def test_custom_constants_preserved(self, rich_project: Path) -> None:
        cfg = ConfigManager(rich_project)
        cfg.set_runtime_platform("opencode")

        raw = json.loads(
            (rich_project / ".cataforge" / "framework.json").read_text(encoding="utf-8")
        )
        assert raw["constants"]["MAX_QUESTIONS_PER_BATCH"] == 7
        assert raw["constants"]["CUSTOM_USER_CONSTANT"] == "value"

    def test_root_level_extra_keys_preserved(self, rich_project: Path) -> None:
        cfg = ConfigManager(rich_project)
        cfg.set_runtime_platform("cursor")

        raw = json.loads(
            (rich_project / ".cataforge" / "framework.json").read_text(encoding="utf-8")
        )
        assert raw["runtime_api_version"] == "1.0"
        assert "description" in raw

    def test_describe_platform_change_no_op(self, rich_project: Path) -> None:
        cfg = ConfigManager(rich_project)
        # Current platform is claude-code; asking for claude-code is a no-op.
        assert cfg.describe_platform_change("claude-code") is None

    def test_describe_platform_change_diff(self, rich_project: Path) -> None:
        cfg = ConfigManager(rich_project)
        diff = cfg.describe_platform_change("cursor")
        assert diff == {
            "field": "runtime.platform",
            "before": "claude-code",
            "after": "cursor",
        }

    def test_bundled_scaffold_roundtrip(self, tmp_path: Path) -> None:
        """The real bundled scaffold framework.json must also survive intact."""
        from cataforge.core.scaffold import copy_scaffold_to

        dest = tmp_path / ".cataforge"
        copy_scaffold_to(dest, force=False)

        before = json.loads((dest / "framework.json").read_text(encoding="utf-8"))

        cfg = ConfigManager(tmp_path)
        cfg.set_runtime_platform("cursor")

        after = json.loads((dest / "framework.json").read_text(encoding="utf-8"))

        # Every nested subtree identical except runtime.platform.
        before["runtime"]["platform"] = "cursor"
        assert after == before
        assert list(after.keys()) == list(before.keys())
