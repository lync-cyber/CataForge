"""Portable-link semantics for ``symlink_or_copy``.

Pinned bug: on Windows, ``deploy`` materialised ``.claude/skills/*`` via
``mklink /J``, which always stores an *absolute* path in the NTFS reparse
point. Moving / renaming the project directory then broke every link
silently. Unix already used a relative symlink — fine — but Windows
needed an equivalent escape hatch.

Post-fix contract:

* Unix: relative symlink as before.
* Windows: relative symlink first (works when Developer Mode is on or
  the process is elevated), junction as a fallback, copy as last resort.
* Action log distinguishes the three so ``cataforge deploy`` output and
  ``doctor`` provenance can tell users what they got.
"""

from __future__ import annotations

import os
import platform as platform_mod
from pathlib import Path

import pytest

from cataforge.adapter.platform.helpers import reset_junction_warning_state, symlink_or_copy


@pytest.fixture(autouse=True)
def _reset_junction_warn_flag():
    """Make the one-shot junction WARN deterministic across test order.

    ``_JUNCTION_WARNING_EMITTED`` is a process-global so the deploy CLI
    only prints one WARN even when 30 skills get linked. That global
    persists across tests in the same process — meaning the
    ``test_windows_falls_back_to_junction_then_copy`` assertion (which
    inspects the WARN string) goes silent when an earlier test in the
    file already burned the flag. Reset before AND after each test so
    neither this test nor any other becomes the victim of side-effect.
    """
    reset_junction_warning_state()
    yield
    reset_junction_warning_state()


def _make_source(tmp_path: Path) -> Path:
    src = tmp_path / "src-skill"
    src.mkdir()
    (src / "SKILL.md").write_text("---\nname: x\n---\n", encoding="utf-8")
    return src


def test_unix_link_target_is_relative_path(tmp_path: Path) -> None:
    """Unix: ``readlink`` of the deployed link must not be absolute."""
    if platform_mod.system() == "Windows":
        pytest.skip("Unix-only contract")

    src = _make_source(tmp_path)
    target = tmp_path / "out" / "x"

    actions = symlink_or_copy(src, target)

    assert target.is_symlink(), actions
    stored = os.readlink(str(target))
    assert not os.path.isabs(stored), (
        f"Unix branch must store a relative path; got absolute {stored!r}."
    )
    # Resolving it from the link's parent still lands on the source.
    resolved = (target.parent / stored).resolve()
    assert resolved == src.resolve()


@pytest.mark.skipif(os.name != "nt", reason="Windows-only contract")
def test_windows_attempts_symlink_before_junction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pre-fix bug: Windows branch jumped straight to ``mklink /J``,
    which stores absolute paths and breaks on project rename. Post-fix:
    ``os.symlink`` must be attempted first (so users who enable
    Developer Mode get portable, relative links).

    We probe via a spy on ``os.symlink``: regardless of whether the
    process actually has the privilege, ``symlink_or_copy`` must call
    it before falling back to a junction.
    """
    src = _make_source(tmp_path)
    target = tmp_path / "out" / "x"

    real_symlink = os.symlink
    calls: list[tuple[str, str]] = []

    def _spy(source_arg, target_arg, **kw):
        calls.append((str(source_arg), str(target_arg)))
        return real_symlink(source_arg, target_arg, **kw)

    monkeypatch.setattr(os, "symlink", _spy)
    symlink_or_copy(src, target)

    assert calls, (
        "symlink_or_copy did not attempt os.symlink on Windows — junctions "
        "store absolute paths and break when the project is moved/renamed."
    )


@pytest.mark.skipif(os.name != "nt", reason="Windows-only contract")
def test_windows_when_symlink_succeeds_stores_relative_path(
    tmp_path: Path,
) -> None:
    """When Developer Mode is on (or the process is elevated), the link
    must be a relative symlink — not a junction with an absolute target.

    Skipped on machines without symlink privilege; the spy-based
    :func:`test_windows_attempts_symlink_before_junction` covers the
    attempt itself for those environments.
    """
    src = _make_source(tmp_path)
    probe = tmp_path / "_symlink_probe"
    try:
        os.symlink(str(src), str(probe), target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable (no Developer Mode and not elevated)")
    finally:
        if os.path.lexists(str(probe)):
            os.unlink(str(probe))

    target = tmp_path / "out" / "x"
    actions = symlink_or_copy(src, target)

    assert target.is_symlink(), actions
    stored = os.readlink(str(target))
    assert not os.path.isabs(stored), (
        f"Windows symlink should be relative; got absolute {stored!r}."
    )
    assert any("symlink" in a for a in actions), actions
    assert not any("junction" in a for a in actions), actions


@pytest.mark.skipif(os.name != "nt", reason="Windows-only behaviour")
def test_windows_falls_back_to_junction_then_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When ``os.symlink`` raises ``OSError`` (no privilege), fall back to
    ``mklink /J``. Action log labels the link ``junction`` so the
    deployer can warn that the link is not portable.
    """
    src = _make_source(tmp_path)
    target = tmp_path / "out" / "x"

    def _denied(*_a, **_kw):
        raise OSError(1314, "A required privilege is not held by the client.")

    monkeypatch.setattr(os, "symlink", _denied)
    actions = symlink_or_copy(src, target)

    assert target.exists(), actions
    # Junction or copy — either is acceptable as a fallback. What matters
    # is that the action log makes the choice explicit (NOT silently
    # claiming symlink) so the doctor / deploy-output can warn.
    assert any(
        "junction" in a or "copy" in a for a in actions
    ), f"fallback type must be labelled; actions={actions}"
    assert not any(
        "symlink" in a and "would" not in a for a in actions
    ), f"must NOT claim symlink after fallback; actions={actions}"
