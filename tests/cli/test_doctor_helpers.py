"""Tests for ``cataforge.cli.doctor._helpers``.

After D6, ``check_import`` returns an ``int`` (0/1) like its sibling
helpers ``check_file`` / ``check_dir``. The ``doctor_cmd`` exit code
adds these return values into ``failed_count``, so a regression in
the integer contract would silently make ``doctor`` exit zero even
when a required import is missing — exactly the situation the gate
exists to catch.
"""

from __future__ import annotations

import builtins

import pytest

from cataforge.cli.doctor._helpers import check_dir, check_file, check_import


class TestCheckImportContract:
    def test_present_module_returns_zero(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert check_import("yaml", "PyYAML") == 0
        out = capsys.readouterr().out
        assert "PyYAML: OK" in out

    def test_missing_optional_returns_zero(
        self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Without ``required=True`` a missing import is informational
        only — preserves the historic optional-deps tone and zero exit
        so existing call sites that ignored the return value stay sane."""
        real_import = builtins.__import__

        def _refuse(name, *a, **kw):
            if name == "definitely_not_a_real_module":
                raise ImportError("simulated absent")
            return real_import(name, *a, **kw)

        monkeypatch.setattr(builtins, "__import__", _refuse)
        assert check_import("definitely_not_a_real_module", "FakeDep") == 0
        out = capsys.readouterr().out
        assert "FakeDep: MISSING" in out
        assert "FAIL" not in out

    def test_missing_required_returns_one(
        self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``required=True`` flips the return to 1 so doctor can fold
        it into ``failed_count`` and exit non-zero."""
        real_import = builtins.__import__

        def _refuse(name, *a, **kw):
            if name == "definitely_not_a_real_module":
                raise ImportError("simulated absent")
            return real_import(name, *a, **kw)

        monkeypatch.setattr(builtins, "__import__", _refuse)
        assert check_import("definitely_not_a_real_module", "FakeDep", required=True) == 1
        out = capsys.readouterr().out
        assert "FakeDep: FAIL" in out
        assert "required import" in out


class TestCheckHelperInterfaceConsistency:
    """All three ``check_*`` helpers must share the same integer
    contract so the ``doctor_cmd`` ``failed_count`` arithmetic is
    type-safe across the lot of them."""

    def test_check_file_returns_int(self, tmp_path) -> None:
        present = tmp_path / "x.txt"
        present.write_text("hi", encoding="utf-8")
        assert isinstance(check_file("present", present), int)
        assert isinstance(
            check_file("missing", tmp_path / "missing.txt", required=True), int
        )

    def test_check_dir_returns_int(self, tmp_path) -> None:
        assert isinstance(check_dir("present", tmp_path), int)
        assert isinstance(
            check_dir("missing", tmp_path / "missing", required=True), int
        )

    def test_check_import_returns_int(self) -> None:
        """Pre-D6 this returned None — adding it into a sum() blew up
        with ``TypeError: unsupported operand type(s) for +``. The
        ``int`` annotation must hold so the doctor exit-code math is
        sound."""
        result = check_import("sys", "stdlib sys")
        assert isinstance(result, int)
        assert result == 0
