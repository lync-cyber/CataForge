"""Regression tests for ``symlink_or_copy`` cleanup of pre-existing targets.

Original failure (v0.3.0, Windows + Python 3.11):

    FileExistsError: '...\\.claude\\rules'

Cleanup chain in ``helpers.py:symlink_or_copy`` had three branches but
none fired for a pre-existing junction on Python 3.11:

* ``Path.is_symlink()`` → False (junctions are not symlinks pre-3.12)
* ``Path.is_junction()`` → AttributeError (added in 3.12)
* ``Path.is_dir()`` was True but ``shutil.rmtree`` on a junction in
  that combo could recurse into the source tree

Result: target survived cleanup, mklink failed, copytree fell over with
``FileExistsError``. These tests pin the post-fix behaviour: every
target shape — real dir, symlink, junction, dangling — gets removed
without touching the source.
"""

from __future__ import annotations

import os
import platform as platform_mod
import shutil
import subprocess
from pathlib import Path

import pytest

from cataforge.platform.helpers import _remove_target, symlink_or_copy


def _make_source(tmp_path: Path) -> Path:
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.md").write_text("alpha", encoding="utf-8")
    (src / "sub").mkdir()
    (src / "sub" / "b.md").write_text("beta", encoding="utf-8")
    return src


def _make_junction(target: Path, source: Path) -> bool:
    """Best-effort junction creation; returns False if the OS refuses."""
    if os.name != "nt":
        return False
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(target), str(source)],
        capture_output=True,
    )
    return result.returncode == 0


def test_dry_run_returns_message_without_touching_filesystem(tmp_path: Path) -> None:
    src = _make_source(tmp_path)
    target = tmp_path / "out" / "rules"

    actions = symlink_or_copy(src, target, dry_run=True)

    assert any("would link" in a for a in actions)
    assert not target.parent.exists()


def test_creates_target_when_parent_missing(tmp_path: Path) -> None:
    src = _make_source(tmp_path)
    target = tmp_path / "deeply" / "nested" / "out"

    symlink_or_copy(src, target)

    assert target.exists()
    assert (target / "a.md").read_text(encoding="utf-8") == "alpha"


def test_replaces_existing_real_directory(tmp_path: Path) -> None:
    src = _make_source(tmp_path)
    target = tmp_path / "out"
    target.mkdir()
    (target / "stale.md").write_text("stale", encoding="utf-8")

    symlink_or_copy(src, target)

    assert not (target / "stale.md").exists(), "stale content survived cleanup"
    assert (target / "a.md").exists()


@pytest.mark.skipif(platform_mod.system() == "Windows", reason="Unix symlink path")
def test_replaces_existing_symlink_unix(tmp_path: Path) -> None:
    src = _make_source(tmp_path)
    other = tmp_path / "other"
    other.mkdir()
    target = tmp_path / "out"
    target.symlink_to(other)

    symlink_or_copy(src, target)

    assert target.is_symlink()
    assert (target / "a.md").exists()
    # source of the *prior* symlink must be untouched
    assert other.exists() and list(other.iterdir()) == []


@pytest.mark.skipif(os.name != "nt", reason="Windows junction path")
def test_replaces_existing_junction_windows(tmp_path: Path) -> None:
    """The v0.3.0 regression scenario: target is already a junction."""
    src = _make_source(tmp_path)
    prior_target = tmp_path / "prior"
    prior_target.mkdir()
    (prior_target / "must-survive.md").write_text("keep me", encoding="utf-8")

    target = tmp_path / "out"
    if not _make_junction(target, prior_target):
        pytest.skip("mklink /J unavailable in this environment")

    symlink_or_copy(src, target)

    # The new junction/copy must point to src content
    assert (target / "a.md").exists()
    assert (target / "a.md").read_text(encoding="utf-8") == "alpha"
    # The prior junction's source must NOT have been recursed into and wiped
    assert (prior_target / "must-survive.md").exists(), (
        "shutil.rmtree recursed through the junction and deleted source content "
        "— the exact bug _remove_target() exists to prevent."
    )


@pytest.mark.skipif(os.name != "nt", reason="Windows junction cleanup")
def test_remove_target_handles_junction_directly(tmp_path: Path) -> None:
    """Direct unit test for _remove_target on a junction — no symlink_or_copy wrapper."""
    src = _make_source(tmp_path)
    target = tmp_path / "j"
    if not _make_junction(target, src):
        pytest.skip("mklink /J unavailable in this environment")

    _remove_target(target)

    assert not target.exists() and not os.path.lexists(str(target))
    # Source must be intact
    assert (src / "a.md").exists()


def test_remove_target_handles_dangling_symlink(tmp_path: Path) -> None:
    """A symlink whose source was deleted should still be cleanable."""
    if os.name == "nt":
        # Use junction; mklink may need admin for symlinks on Windows
        ghost = tmp_path / "ghost"
        ghost.mkdir()
        target = tmp_path / "dangler"
        if not _make_junction(target, ghost):
            pytest.skip("mklink /J unavailable")
        shutil.rmtree(ghost)
    else:
        target = tmp_path / "dangler"
        target.symlink_to(tmp_path / "does-not-exist")

    assert os.path.lexists(str(target))
    assert not target.exists()  # broken: exists() resolves the link

    _remove_target(target)

    assert not os.path.lexists(str(target))


def test_remove_target_noop_when_missing(tmp_path: Path) -> None:
    target = tmp_path / "never-existed"
    _remove_target(target)  # must not raise


def test_idempotent_redeploy(tmp_path: Path) -> None:
    """Calling symlink_or_copy twice in a row is the upgrade-then-deploy pattern."""
    src = _make_source(tmp_path)
    target = tmp_path / "out"

    symlink_or_copy(src, target)
    # Second call simulates `cataforge bootstrap` re-running deploy after upgrade
    symlink_or_copy(src, target)

    assert (target / "a.md").exists()
    assert (target / "sub" / "b.md").exists()
