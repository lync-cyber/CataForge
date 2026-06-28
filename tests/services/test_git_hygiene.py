"""Tests for git hygiene service helpers."""

from __future__ import annotations

from pathlib import Path

from cataforge.application.services.git_hygiene import (
    DEFAULT_GITATTRIBUTES,
    ensure_gitattributes,
    inspect_gitattributes,
)


def test_gitattributes_default_contains_line_ending_rules() -> None:
    assert "* text=auto eol=lf" in DEFAULT_GITATTRIBUTES
    assert "*.bat text eol=crlf" in DEFAULT_GITATTRIBUTES
    assert "*.png binary" in DEFAULT_GITATTRIBUTES


def test_ensure_gitattributes_writes_default_when_missing(tmp_path: Path) -> None:
    status = ensure_gitattributes(tmp_path)

    assert status.wrote_file
    assert status.ok
    text = (tmp_path / ".gitattributes").read_text(encoding="utf-8")
    assert "* text=auto eol=lf" in text
    assert "*.cmd text eol=crlf" in text


def test_ensure_gitattributes_does_not_overwrite_existing(tmp_path: Path) -> None:
    path = tmp_path / ".gitattributes"
    original = "* text=auto eol=lf\n"
    path.write_text(original, encoding="utf-8")

    status = ensure_gitattributes(tmp_path)

    assert not status.wrote_file
    assert status.ok
    assert path.read_text(encoding="utf-8") == original


def test_inspect_gitattributes_reports_missing_eol_rule(tmp_path: Path) -> None:
    (tmp_path / ".gitattributes").write_text("* text=auto\n", encoding="utf-8")

    status = inspect_gitattributes(tmp_path)

    assert status.exists
    assert status.has_text_auto
    assert not status.has_eol_rule
    assert not status.ok
