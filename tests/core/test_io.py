"""Tests for cataforge.core.io — locale-independent stdin decoding."""

from __future__ import annotations

import io
import sys

import pytest

from cataforge.core.io import read_stdin_utf8


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
    payload = "进度 5/20 → 6/20".encode("utf-8")
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
