"""Tests for ``cataforge.utils.atomic_write.atomic_write_text``.

Three properties must hold:

1. Normal writes land on disk with the requested content + encoding.
2. A failure mid-write does not damage the prior file content.
3. Temp files do not leak under either success or failure.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from cataforge.utils.atomic_write import atomic_write_text


def _temp_artifacts(dir_: Path, stem: str) -> list[Path]:
    """Return any ``.{stem}.<random>.tmp`` siblings left in *dir_*."""
    return [p for p in dir_.iterdir() if p.name.startswith(f".{stem}.") and p.name.endswith(".tmp")]


class TestAtomicWriteText:
    def test_creates_new_file_with_content(self, tmp_path: Path) -> None:
        path = tmp_path / "framework.json"
        atomic_write_text(path, '{"version": "0.0.0"}\n')
        assert path.read_text(encoding="utf-8") == '{"version": "0.0.0"}\n'

    def test_overwrites_existing_file_atomically(self, tmp_path: Path) -> None:
        path = tmp_path / "framework.json"
        path.write_text("OLD", encoding="utf-8")
        atomic_write_text(path, "NEW")
        assert path.read_text(encoding="utf-8") == "NEW"

    def test_creates_parent_directory_if_missing(self, tmp_path: Path) -> None:
        path = tmp_path / "nested" / "deep" / "file.txt"
        atomic_write_text(path, "hello")
        assert path.read_text(encoding="utf-8") == "hello"

    def test_respects_custom_encoding(self, tmp_path: Path) -> None:
        path = tmp_path / "out.txt"
        atomic_write_text(path, "café", encoding="utf-16")
        assert path.read_text(encoding="utf-16") == "café"

    def test_failure_preserves_prior_content(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        path = tmp_path / "framework.json"
        path.write_text("PRIOR", encoding="utf-8")

        real_replace = os.replace

        def _explode(*_a, **_kw):
            raise OSError("simulated rename failure")

        monkeypatch.setattr(os, "replace", _explode)

        with pytest.raises(OSError, match="simulated rename failure"):
            atomic_write_text(path, "NEW")

        # Prior content untouched — readers never see half-written data.
        assert path.read_text(encoding="utf-8") == "PRIOR"
        # And no temp file leaked.
        assert _temp_artifacts(tmp_path, "framework.json") == []

        # Sanity: real os.replace would have made the write succeed.
        monkeypatch.setattr(os, "replace", real_replace)
        atomic_write_text(path, "NEW")
        assert path.read_text(encoding="utf-8") == "NEW"

    def test_no_temp_files_leak_on_success(self, tmp_path: Path) -> None:
        path = tmp_path / "framework.json"
        for _ in range(5):
            atomic_write_text(path, "x")
        assert _temp_artifacts(tmp_path, "framework.json") == []
