"""Regression: ``_remove_target`` runs at most once across the whole
symlink → junction → copy fallback chain.

Pre-fix, the chain had three independent ``_remove_target`` call sites
(one before each strategy attempt). When the first attempt failed mid-
write — leaving a half-created directory shell, or when a stat raced
with another process — the subsequent calls repeated the destructive
``shutil.rmtree`` / ``os.rmdir`` work on whatever was at *target* now.
In the worst case (junction whose source path briefly resolved during
the gap) this recursed into the source tree.

Post-fix: a shared ``removed`` cell is threaded through the chain so
only the first strategy actually attempts a removal; the rest become
no-ops.
"""

from __future__ import annotations

import contextlib
import os
import subprocess
from pathlib import Path

import pytest

from cataforge.platform import helpers as helpers_mod
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


class _RemoveTargetSpy:
    """Wrap the module-level ``_remove_target`` and count its invocations
    while still delegating to the real removal logic."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.calls: list[Path] = []
        self._real = helpers_mod._remove_target
        monkeypatch.setattr(helpers_mod, "_remove_target", self)

    def __call__(self, target: Path) -> None:
        self.calls.append(target)
        self._real(target)


class TestRemoveTargetIdempotency:
    """Across every failure path, ``_remove_target`` is called at most
    once per ``symlink_or_copy`` invocation."""

    def test_symlink_success_path_removes_once(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Happy path: symlink succeeds first try. Removal happens once
        (so a pre-existing target is cleared), then never again."""
        src = _make_source(tmp_path)
        target = tmp_path / "out" / "x"
        # Plant a pre-existing target so removal has something to do.
        target.parent.mkdir(parents=True)
        (target).mkdir()

        spy = _RemoveTargetSpy(monkeypatch)
        # Privilege denied on Windows non-Dev-Mode is acceptable; the
        # assertion below still holds because the chain falls through.
        with contextlib.suppress(OSError, NotImplementedError):
            symlink_or_copy(src, target)

        assert len(spy.calls) == 1, (
            f"removal must run exactly once on a fresh chain; got {len(spy.calls)} "
            f"call(s): {spy.calls!r}"
        )

    def test_symlink_failure_then_junction_or_copy_removes_once(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Force ``os.symlink`` to raise the Windows privilege error,
        then assert the chain falls through to junction (Windows) or
        copy (POSIX) and still only removed once total."""
        src = _make_source(tmp_path)
        target = tmp_path / "out" / "x"
        target.parent.mkdir(parents=True)
        (target).mkdir()  # plant existing target

        def _denied(*_a, **_kw):
            raise OSError(1314, "A required privilege is not held by the client.")

        monkeypatch.setattr(os, "symlink", _denied)
        spy = _RemoveTargetSpy(monkeypatch)

        actions = symlink_or_copy(src, target)

        # Action log must indicate the actual strategy that landed.
        assert any("junction" in a or "copy" in a for a in actions), actions
        assert len(spy.calls) == 1, (
            f"removal must run exactly once even after a fallback; got "
            f"{len(spy.calls)} call(s): {spy.calls!r}"
        )

    def test_symlink_and_junction_failure_then_copy_removes_once(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Force BOTH symlink and mklink to fail, then assert the copy
        terminal strategy lands and removal still ran only once."""
        src = _make_source(tmp_path)
        target = tmp_path / "out" / "x"
        target.parent.mkdir(parents=True)
        (target).mkdir()  # plant existing target

        def _denied_symlink(*_a, **_kw):
            raise OSError(1314, "privilege not held")

        def _denied_mklink(args, *a, **kw):
            # The junction strategy now goes through
            # cataforge.utils.run_subprocess.run, which never raises
            # CalledProcessError — it returns a CompletedProcess and
            # helpers._try_junction inspects ``.returncode``. Mirror that
            # contract: return rc=1 to simulate "mklink denied".
            return subprocess.CompletedProcess(
                args=args, returncode=1, stdout="", stderr="mklink denied"
            )

        monkeypatch.setattr(os, "symlink", _denied_symlink)
        # Patch where helpers.py imports `run_proc` (the lazy local import
        # inside _try_junction). monkeypatching the wrapper module itself
        # would miss the binding because the import happens at call time.
        monkeypatch.setattr(
            "cataforge.utils.run_subprocess.run", _denied_mklink
        )
        spy = _RemoveTargetSpy(monkeypatch)

        actions = symlink_or_copy(src, target)

        # Terminal copy ran.
        assert (target / "SKILL.md").is_file(), actions
        assert any("(copy)" in a for a in actions), actions
        assert len(spy.calls) == 1, (
            f"removal must run exactly once even when both link strategies "
            f"fail; got {len(spy.calls)} call(s): {spy.calls!r}"
        )

    def test_no_preexisting_target_removes_zero_or_one_times(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Fresh target: ``_remove_target`` may be invoked once (early
        guard against stale lexists state) but never more than once."""
        src = _make_source(tmp_path)
        target = tmp_path / "out" / "x"

        spy = _RemoveTargetSpy(monkeypatch)
        with contextlib.suppress(OSError, NotImplementedError):
            symlink_or_copy(src, target)

        assert len(spy.calls) <= 1, (
            f"removal must not run more than once; got {len(spy.calls)} "
            f"call(s): {spy.calls!r}"
        )

    def test_force_copy_removes_once_and_skips_link_attempts(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``force_copy=True`` skips the link chain entirely; removal
        still must not exceed one call."""
        src = _make_source(tmp_path)
        target = tmp_path / "out" / "x"
        target.parent.mkdir(parents=True)
        (target).mkdir()  # plant existing target

        symlink_attempts: list[None] = []
        original_symlink = os.symlink

        def _track(*a, **kw):
            symlink_attempts.append(None)
            return original_symlink(*a, **kw)

        monkeypatch.setattr(os, "symlink", _track)
        spy = _RemoveTargetSpy(monkeypatch)

        actions = symlink_or_copy(src, target, force_copy=True)

        assert symlink_attempts == [], (
            "force_copy=True must not even try os.symlink"
        )
        assert any("forced" in a for a in actions), actions
        assert len(spy.calls) == 1, (
            f"force_copy removal must run exactly once; got {len(spy.calls)} "
            f"call(s): {spy.calls!r}"
        )
