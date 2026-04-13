"""check_migration_artifacts 数据驱动迁移检查测试 (P1-3)"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".claude", "scripts"))
from _upgrade_verify import check_migration_artifacts  # noqa: E402


def _write_matrix(tmp_path, checks):
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    matrix = {"features": {}, "migration_checks": checks}
    (claude_dir / "framework.json").write_text(
        json.dumps(matrix, ensure_ascii=False), encoding="utf-8"
    )


class TestMigrationArtifacts:
    def test_empty_checks_pass(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_matrix(tmp_path, [])
        assert check_migration_artifacts() == []

    def test_no_matrix_file_pass(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert check_migration_artifacts() == []

    def test_file_must_exist_pass(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        target = tmp_path / "TARGET.md"
        target.write_text("hello")
        _write_matrix(
            tmp_path,
            [{"id": "c1", "type": "file_must_exist", "path": str(target)}],
        )
        assert check_migration_artifacts() == []

    def test_file_must_exist_fail(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_matrix(
            tmp_path,
            [{"id": "c1", "type": "file_must_exist", "path": "missing.md"}],
        )
        issues = check_migration_artifacts()
        assert len(issues) == 1
        assert "c1" in issues[0]

    def test_file_must_contain_pass(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        target = tmp_path / "RULES.md"
        target.write_text("FOO\nBAR\nBAZ\n")
        _write_matrix(
            tmp_path,
            [
                {
                    "id": "c2",
                    "type": "file_must_contain",
                    "path": str(target),
                    "patterns": ["FOO", "BAR"],
                }
            ],
        )
        assert check_migration_artifacts() == []

    def test_file_must_contain_fail(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        target = tmp_path / "RULES.md"
        target.write_text("FOO\n")
        _write_matrix(
            tmp_path,
            [
                {
                    "id": "c2",
                    "type": "file_must_contain",
                    "path": str(target),
                    "patterns": ["FOO", "BAR"],
                }
            ],
        )
        issues = check_migration_artifacts()
        assert len(issues) == 1
        assert "BAR" in issues[0]

    def test_file_must_not_contain(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        target = tmp_path / "RULES.md"
        target.write_text("DEPRECATED_CONSTANT\n")
        _write_matrix(
            tmp_path,
            [
                {
                    "id": "c3",
                    "type": "file_must_not_contain",
                    "path": str(target),
                    "patterns": ["DEPRECATED_CONSTANT"],
                }
            ],
        )
        issues = check_migration_artifacts()
        assert len(issues) == 1
        assert "DEPRECATED_CONSTANT" in issues[0]

    def test_dir_must_contain_files(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        d = tmp_path / "templates"
        d.mkdir()
        (d / "a.md").write_text("")
        # b.md 缺失
        _write_matrix(
            tmp_path,
            [
                {
                    "id": "c4",
                    "type": "dir_must_contain_files",
                    "path": str(d),
                    "patterns": ["a.md", "b.md"],
                }
            ],
        )
        issues = check_migration_artifacts()
        assert len(issues) == 1
        assert "b.md" in issues[0]

    def test_unknown_type_reported(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_matrix(
            tmp_path,
            [{"id": "c5", "type": "wat", "path": "any.md"}],
        )
        issues = check_migration_artifacts()
        assert len(issues) == 1
        assert "wat" in issues[0]

    def test_incomplete_declaration_reported(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_matrix(tmp_path, [{"id": "c6"}])  # missing path + type
        issues = check_migration_artifacts()
        assert len(issues) == 1
        assert "c6" in issues[0]


class TestCompatMatrixMigrationChecksCurrent:
    """对当前仓库的 framework.json 做一次真实执行，确保声明与仓库一致。"""

    def test_live_matrix_passes(self, project_root):
        cwd_backup = os.getcwd()
        try:
            os.chdir(project_root)
            issues = check_migration_artifacts()
            # 每个 migration check 都必须通过，否则暴露了仓库回归
            assert issues == [], "仓库 compat-matrix 迁移检查未通过:\n" + "\n".join(
                issues
            )
        finally:
            os.chdir(cwd_backup)
