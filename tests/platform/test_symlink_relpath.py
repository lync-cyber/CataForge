"""Regression: symlink target must use POSIX separators.

Pre-fix bug: ``symlink_or_copy`` passed ``os.path.relpath(...)`` straight
to ``os.symlink``. On Windows, ``relpath`` returns backslash-separated
strings (``..\\..\\source``), which the kernel happily writes verbatim
into the reparse point. The link then breaks the moment the project
directory is cloned, copied, or accessed from a POSIX environment
(WSL, network mount, sibling Linux CI runner).

Post-fix: the path is normalised to ``/`` before ``os.symlink`` is
called, so the stored target is portable across platforms.
"""

from __future__ import annotations

import contextlib
import os
import platform as platform_mod
from pathlib import Path

import pytest

from cataforge.platform.helpers import reset_junction_warning_state, symlink_or_copy


@pytest.fixture(autouse=True)
def _reset_junction_warn_flag():
    reset_junction_warning_state()
    yield
    reset_junction_warning_state()


def _make_source(tmp_path: Path) -> Path:
    src = tmp_path / "src-skill"
    src.mkdir()
    (src / "SKILL.md").write_text("---\nname: x\n---\n", encoding="utf-8")
    return src


def test_symlink_target_string_uses_posix_separators(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The exact string handed to ``os.symlink`` must be backslash-free.

    Forces ``os.path.relpath`` to return a Windows-flavoured path even on
    POSIX runners, so the test catches the bug on every platform rather
    than only flagging it on a Windows CI matrix entry.
    """
    src = _make_source(tmp_path)
    target = tmp_path / "out" / "x"

    captured: list[str] = []
    real_symlink = os.symlink

    def _capturing_symlink(source_arg, target_arg, **kw):
        captured.append(str(source_arg))
        return real_symlink(source_arg, target_arg, **kw)

    def _fake_relpath(*_a, **_kw):
        return r"..\..\src-skill"

    monkeypatch.setattr(os.path, "relpath", _fake_relpath)
    monkeypatch.setattr(os, "symlink", _capturing_symlink)

    # Privilege denied (e.g. Windows non-Dev-Mode) is fine — the captured
    # argument still reflects what was offered to the kernel, and that is
    # what we assert on.
    with contextlib.suppress(OSError, NotImplementedError):
        symlink_or_copy(src, target)

    assert captured, "os.symlink was not invoked at all"
    assert "\\" not in captured[0], (
        f"symlink target must use forward slashes; got {captured[0]!r}"
    )


def test_symlink_target_resolves_to_source_after_normalisation(
    tmp_path: Path,
) -> None:
    """End-to-end: after the link is created, the stored target must
    resolve back to the source from the link's parent — i.e. the POSIX
    normalisation does not break the relative-path arithmetic.

    Unix runners exercise this directly. Windows runners require
    Developer Mode / elevation; skip otherwise (the unit-level capture
    test above covers the bug regardless).
    """
    if platform_mod.system() == "Windows":
        # Probe whether this process can create symlinks at all.
        probe_src = tmp_path / "_probe_src"
        probe_src.mkdir()
        probe = tmp_path / "_probe_link"
        try:
            os.symlink(str(probe_src), str(probe), target_is_directory=True)
        except (OSError, NotImplementedError):
            pytest.skip(
                "symlinks unavailable (no Developer Mode and not elevated)"
            )
        finally:
            if os.path.lexists(str(probe)):
                os.unlink(str(probe))

    src = _make_source(tmp_path)
    target = tmp_path / "out" / "x"
    symlink_or_copy(src, target)

    assert target.is_symlink()
    stored = os.readlink(str(target))
    assert "\\" not in stored, (
        f"stored link target must not contain backslashes; got {stored!r}"
    )
    resolved = (target.parent / stored).resolve()
    assert resolved == src.resolve()
