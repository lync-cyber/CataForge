"""Tests for cataforge.core.io — locale-independent stdin decoding and the
centralized JSON/YAML file readers."""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

from cataforge.core.errors import ConfigError
from cataforge.core.io import read_json, read_stdin_utf8, read_yaml


class _FakeStdin:
    """Minimal stand-in for ``sys.stdin`` that exposes a ``buffer`` attr.

    The real bug only triggers when the text-mode wrapper's encoding
    differs from UTF-8, but ``read_stdin_utf8`` reads raw bytes from
    ``buffer`` and decodes them itself — so the simulation only needs
    to expose UTF-8 bytes through ``buffer.read()``.
    """

    def __init__(self, payload: bytes) -> None:
        self.buffer = io.BytesIO(payload)


def test_decodes_utf8(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = "进度 5/20 → 6/20".encode()
    monkeypatch.setattr(sys, "stdin", _FakeStdin(payload))
    assert read_stdin_utf8() == "进度 5/20 → 6/20"


def test_strict_raises_on_invalid_utf8(monkeypatch: pytest.MonkeyPatch) -> None:
    # 0xFF is never valid UTF-8 in any position.
    monkeypatch.setattr(sys, "stdin", _FakeStdin(b"\xff"))
    with pytest.raises(UnicodeDecodeError):
        read_stdin_utf8()


def test_replace_recovers_invalid_utf8(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hooks must keep running on broken payloads — errors='replace'
    substitutes U+FFFD instead of raising."""
    monkeypatch.setattr(sys, "stdin", _FakeStdin(b"ok\xff"))
    assert read_stdin_utf8(errors="replace") == "ok�"


def test_empty_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stdin", _FakeStdin(b""))
    assert read_stdin_utf8() == ""


# ---- read_json / read_yaml ------------------------------------------------


def test_read_json_parses_object(tmp_path: Path) -> None:
    p = tmp_path / "data.json"
    p.write_text('{"a": 1, "b": [2, 3]}', encoding="utf-8")
    assert read_json(p) == {"a": 1, "b": [2, 3]}


def test_read_json_missing_file_raises_config_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="nope.json"):
        read_json(tmp_path / "nope.json")


def test_read_json_malformed_raises_config_error(tmp_path: Path) -> None:
    p = tmp_path / "bad.json"
    p.write_text("{not json", encoding="utf-8")
    with pytest.raises(ConfigError, match="bad.json"):
        read_json(p)


def test_read_json_accepts_str_path(tmp_path: Path) -> None:
    p = tmp_path / "data.json"
    p.write_text('{"ok": true}', encoding="utf-8")
    assert read_json(str(p)) == {"ok": True}


def test_read_yaml_parses_mapping(tmp_path: Path) -> None:
    p = tmp_path / "data.yaml"
    p.write_text("a: 1\nb:\n  - 2\n  - 3\n", encoding="utf-8")
    assert read_yaml(p) == {"a": 1, "b": [2, 3]}


def test_read_yaml_empty_file_is_empty_mapping(tmp_path: Path) -> None:
    p = tmp_path / "empty.yaml"
    p.write_text("", encoding="utf-8")
    assert read_yaml(p) == {}


def test_read_yaml_missing_file_raises_config_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="nope.yaml"):
        read_yaml(tmp_path / "nope.yaml")


def test_read_yaml_malformed_raises_config_error(tmp_path: Path) -> None:
    p = tmp_path / "bad.yaml"
    p.write_text("a: [1, 2\n  - broken", encoding="utf-8")
    with pytest.raises(ConfigError, match="bad.yaml"):
        read_yaml(p)
