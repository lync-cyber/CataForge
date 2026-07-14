"""升级合并的字段级所有权：user 块保留补新、framework 块覆盖、未知键保留。"""

from __future__ import annotations

import json
from pathlib import Path

from cataforge.core.scaffold import _merge_framework_json

SCAFFOLD = {
    "schema_version": 2,
    "version": "0.0.0-template",
    "runtime_api_version": "1.0",
    "deployment": {"default_platform": "claude-code", "targets": ["claude-code"]},
    "upgrade": {"source": {"repo": "", "branch": "main"}},
    "feedback": {"gh": {"labels": {"bug": ["framework-bug"]}}},
    "claude_md_limits": {"max_bytes": 30000, "max_state_section_lines": 80},
    "constants": {"NEW_CONSTANT": 42},
    "features": {"new-feature": {"auto_enable": True}},
    "workflow": {"modes": {"standard": ["planning"]}},
    "dispatcher_skills": ["context"],
    "migration_checks": [{"id": "mc-new"}],
}


def _merge(existing: dict, scaffold: dict | None = None, tmp_path: Path | None = None) -> dict:
    target = tmp_path / "framework.json"
    target.write_text(json.dumps(existing), encoding="utf-8")
    new_bytes = json.dumps(scaffold or SCAFFOLD).encode("utf-8")
    return json.loads(_merge_framework_json(new_bytes, target).decode("utf-8"))


class TestUserOwnedBlocksPreserved:
    def test_feedback_user_values_win(self, tmp_path: Path) -> None:
        merged = _merge({"feedback": {"gh": {"labels": {"bug": ["my-label"]}}}}, tmp_path=tmp_path)
        assert merged["feedback"]["gh"] == {"labels": {"bug": ["my-label"]}}

    def test_git_block_preserved(self, tmp_path: Path) -> None:
        merged = _merge({"git": {"session_sync": {"enabled": False}}}, tmp_path=tmp_path)
        assert merged["git"]["session_sync"] == {"enabled": False}

    def test_claude_md_limits_user_tuning_wins_new_keys_introduced(self, tmp_path: Path) -> None:
        merged = _merge({"claude_md_limits": {"max_bytes": 99999}}, tmp_path=tmp_path)
        assert merged["claude_md_limits"]["max_bytes"] == 99999
        assert merged["claude_md_limits"]["max_state_section_lines"] == 80

    def test_upgrade_source_user_values_win(self, tmp_path: Path) -> None:
        merged = _merge(
            {"upgrade": {"source": {"repo": "acme/fork", "token_env": "TK"}}},
            tmp_path=tmp_path,
        )
        assert merged["upgrade"]["source"]["repo"] == "acme/fork"
        assert merged["upgrade"]["source"]["token_env"] == "TK"
        assert merged["upgrade"]["source"]["branch"] == "main"

    def test_upgrade_state_carried_until_migration(self, tmp_path: Path) -> None:
        merged = _merge(
            {"upgrade": {"state": {"event_log_validate_since": "w"}}}, tmp_path=tmp_path
        )
        assert merged["upgrade"]["state"] == {"event_log_validate_since": "w"}

    def test_deployment_preserved(self, tmp_path: Path) -> None:
        merged = _merge(
            {
                "deployment": {
                    "default_platform": "codex",
                    "targets": ["codex", "cursor"],
                }
            },
            tmp_path=tmp_path,
        )
        assert merged["deployment"]["default_platform"] == "codex"
        assert merged["deployment"]["targets"] == ["codex", "cursor"]

    def test_unknown_top_level_key_preserved(self, tmp_path: Path) -> None:
        merged = _merge({"x-my-plugin": {"opt": 1}}, tmp_path=tmp_path)
        assert merged["x-my-plugin"] == {"opt": 1}

    def test_legacy_runtime_block_preserved_for_migration(self, tmp_path: Path) -> None:
        merged = _merge({"runtime": {"platform": "cursor"}}, tmp_path=tmp_path)
        assert merged["runtime"] == {"platform": "cursor"}


class TestFrameworkOwnedBlocksOverwritten:
    def test_constants_overwritten(self, tmp_path: Path) -> None:
        merged = _merge({"constants": {"OLD": 1}}, tmp_path=tmp_path)
        assert merged["constants"] == {"NEW_CONSTANT": 42}

    def test_features_overwritten(self, tmp_path: Path) -> None:
        merged = _merge({"features": {"old": {"auto_enable": False}}}, tmp_path=tmp_path)
        assert merged["features"] == {"new-feature": {"auto_enable": True}}

    def test_migration_checks_overwritten(self, tmp_path: Path) -> None:
        merged = _merge({"migration_checks": [{"id": "mc-old"}]}, tmp_path=tmp_path)
        assert merged["migration_checks"] == [{"id": "mc-new"}]

    def test_workflow_overwritten(self, tmp_path: Path) -> None:
        merged = _merge({"workflow": {"modes": {"old": []}}}, tmp_path=tmp_path)
        assert merged["workflow"] == {"modes": {"standard": ["planning"]}}

    def test_dispatcher_skills_overwritten(self, tmp_path: Path) -> None:
        merged = _merge({"dispatcher_skills": ["old"]}, tmp_path=tmp_path)
        assert merged["dispatcher_skills"] == ["context"]

    def test_schema_version_stamped_from_scaffold(self, tmp_path: Path) -> None:
        merged = _merge({"version": "0.1.0"}, tmp_path=tmp_path)
        assert merged["schema_version"] == 2
