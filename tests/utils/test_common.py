"""Tests for cataforge.utils.common — focused on load_dotenv path boundary."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from cataforge.utils.common import load_dotenv


class TestLoadDotenv:
    def test_loads_key_value_pairs(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        env_file = tmp_path / ".env"
        env_file.write_text("FOO=bar\nBAZ=qux\n", encoding="utf-8")
        result = load_dotenv(env_file)
        assert result == {"FOO": "bar", "BAZ": "qux"}

    def test_skips_comments_and_blank_lines(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        env_file = tmp_path / ".env"
        env_file.write_text("# comment\n\nFOO=bar\n", encoding="utf-8")
        result = load_dotenv(env_file)
        assert result == {"FOO": "bar"}

    def test_returns_empty_for_missing_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        result = load_dotenv(tmp_path / "nonexistent.env")
        assert result == {}

    def test_path_traversal_rejected(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        outside = tmp_path.parent / "outside.env"
        with pytest.raises(ValueError, match="outside the working directory"):
            load_dotenv(outside)

    def test_dotdot_path_rejected(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        subdir = tmp_path / "sub"
        subdir.mkdir()
        monkeypatch.chdir(subdir)
        with pytest.raises(ValueError, match="outside the working directory"):
            load_dotenv(subdir / ".." / ".." / "etc" / "passwd")

    def test_default_path_uses_cwd_dotenv(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".env").write_text("KEY=val\n", encoding="utf-8")
        result = load_dotenv()
        assert result["KEY"] == "val"

    def test_set_env_populates_os_environ(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        env_file = tmp_path / ".env"
        env_file.write_text("MY_TEST_VAR=hello\n", encoding="utf-8")
        monkeypatch.delenv("MY_TEST_VAR", raising=False)
        load_dotenv(env_file, set_env=True)
        assert os.environ.get("MY_TEST_VAR") == "hello"
