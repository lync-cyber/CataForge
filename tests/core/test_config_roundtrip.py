"""Regression tests protecting framework.json from lossy rewrites.

``set_default_platform`` is a **minimal patch**: it may only write the
``deployment`` block and pop the legacy ``runtime.platform`` key; every
other byte of the file is preserved, including field order and
user-authored extras at any nesting level (``upgrade.source.branch``,
``upgrade.state``, custom constants, root-level extra keys).
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


def _read(root: Path) -> dict:
    return json.loads((root / ".cataforge" / "framework.json").read_text(encoding="utf-8"))


class TestSetDefaultPlatformPreservation:
    """``set_default_platform`` must touch only the deployment/runtime keys."""

    def test_upgrade_source_extras_preserved(self, rich_project: Path) -> None:
        ConfigManager(rich_project).set_default_platform("cursor")
        src = _read(rich_project)["upgrade"]["source"]
        assert src["type"] == "github"
        assert src["repo"] == "user/fork"
        assert src["branch"] == "develop"
        assert src["token_env"] == "MY_CUSTOM_TOKEN_VAR"

    def test_upgrade_state_preserved(self, rich_project: Path) -> None:
        ConfigManager(rich_project).set_default_platform("cursor")
        state = _read(rich_project)["upgrade"]["state"]
        assert state["last_commit"] == "abc123"
        assert state["last_version"] == "0.0.9"
        assert state["last_upgrade_date"] == "2026-01-15"

    def test_top_level_field_order_preserved(self, rich_project: Path) -> None:
        original_keys = list(_read(rich_project).keys())
        ConfigManager(rich_project).set_default_platform("cursor")
        after_keys = list(_read(rich_project).keys())
        # runtime is popped (its only key was platform); deployment appended.
        expected = [k for k in original_keys if k != "runtime"] + ["deployment"]
        assert after_keys == expected

    def test_only_platform_fields_change(self, rich_project: Path) -> None:
        original = _read(rich_project)
        ConfigManager(rich_project).set_default_platform("codex")
        after = _read(rich_project)

        # Mutate original's expected changes and assert full equality.
        del original["runtime"]
        original["deployment"] = {"default_platform": "codex", "targets": ["codex"]}
        assert after == original

    def test_custom_constants_preserved(self, rich_project: Path) -> None:
        ConfigManager(rich_project).set_default_platform("opencode")
        raw = _read(rich_project)
        assert raw["constants"]["MAX_QUESTIONS_PER_BATCH"] == 7
        assert raw["constants"]["CUSTOM_USER_CONSTANT"] == "value"

    def test_root_level_extra_keys_preserved(self, rich_project: Path) -> None:
        ConfigManager(rich_project).set_default_platform("cursor")
        raw = _read(rich_project)
        assert raw["runtime_api_version"] == "1.0"
        assert "description" in raw

    def test_describe_platform_change_legacy_normalizes(self, rich_project: Path) -> None:
        # v1 file: even the same platform id reports a change (legacy key
        # normalizes into the deployment block on the next set).
        cfg = ConfigManager(rich_project)
        diff = cfg.describe_platform_change("claude-code")
        assert diff is not None
        assert diff["field"] == "deployment.default_platform"

    def test_describe_platform_change_v2_no_op(self, tmp_path: Path) -> None:
        cataforge_dir = tmp_path / ".cataforge"
        cataforge_dir.mkdir()
        (cataforge_dir / "framework.json").write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "deployment": {"default_platform": "cursor", "targets": ["cursor"]},
                }
            ),
            encoding="utf-8",
        )
        assert ConfigManager(tmp_path).describe_platform_change("cursor") is None

    def test_describe_platform_change_diff(self, rich_project: Path) -> None:
        diff = ConfigManager(rich_project).describe_platform_change("cursor")
        assert diff == {
            "field": "deployment.default_platform",
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
        cfg.set_default_platform("cursor")

        after = json.loads((dest / "framework.json").read_text(encoding="utf-8"))

        # Every nested subtree identical except the deployment patch: default
        # switches, cursor unions into targets, nothing else moves.
        before.pop("runtime", None)
        deployment = dict(before.get("deployment") or {})
        deployment["default_platform"] = "cursor"
        targets = [str(t) for t in deployment.get("targets") or []]
        if "cursor" not in targets:
            targets.append("cursor")
        deployment["targets"] = targets
        before["deployment"] = deployment
        assert after == before
        assert list(after.keys()) == list(before.keys())
