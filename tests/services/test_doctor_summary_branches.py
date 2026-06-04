"""Tests for doctor_summary fail/warn extraction branches."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from cataforge.application.services.doctor_summary import collect_doctor_summary


def _make_result(output: str, exit_code: int = 0):
    r = MagicMock()
    r.stdout = output
    r.stderr = ""
    r.returncode = exit_code
    return r


def _patch_runner(output: str, exit_code: int = 0):
    result = _make_result(output, exit_code)
    return patch(
        "cataforge.application.services.doctor_summary.run_proc",
        return_value=result,
    )


class TestDoctorSummaryBranches:
    def test_fails_populated_when_fail_present(self, tmp_path: Path) -> None:
        text = "Checking tools...\nFAIL docker not found\nAll done\n"
        with _patch_runner(text):
            out = collect_doctor_summary(tmp_path)

        assert len(out["fails"]) >= 1
        assert any("FAIL" in line for line in out["fails"])

    def test_fails_empty_when_no_fail(self, tmp_path: Path) -> None:
        text = "Checking tools...\nOK docker found\nAll done\n"
        with _patch_runner(text):
            out = collect_doctor_summary(tmp_path)

        assert out["fails"] == []

    def test_fails_contains_full_lines(self, tmp_path: Path) -> None:
        text = "FAIL docker not found\nFAIL git missing\nOK python ok\n"
        with _patch_runner(text):
            out = collect_doctor_summary(tmp_path)

        assert len(out["fails"]) == 2
        assert "FAIL docker not found" in out["fails"]
        assert "FAIL git missing" in out["fails"]

    def test_error_keyword_triggers_fail(self, tmp_path: Path) -> None:
        text = "ERROR unexpected condition\n"
        with _patch_runner(text):
            out = collect_doctor_summary(tmp_path)

        assert len(out["fails"]) == 1

    def test_missing_keyword_triggers_fail(self, tmp_path: Path) -> None:
        text = "missing: node not installed\n"
        with _patch_runner(text):
            out = collect_doctor_summary(tmp_path)

        assert len(out["fails"]) == 1

    def test_fail_keyword_in_middle_of_line_not_matched(self, tmp_path: Path) -> None:
        text = "all tests pass — no FAILures\n"
        with _patch_runner(text):
            out = collect_doctor_summary(tmp_path)

        assert out["fails"] == []

    def test_warns_extracted_independently(self, tmp_path: Path) -> None:
        text = "WARN deprecated flag used\nFAIL docker missing\n"
        with _patch_runner(text):
            out = collect_doctor_summary(tmp_path)

        assert len(out["warns"]) == 1
        assert "WARN deprecated flag used" in out["warns"]
        assert len(out["fails"]) == 1

    def test_empty_output_returns_empty_lists(self, tmp_path: Path) -> None:
        with _patch_runner(""):
            out = collect_doctor_summary(tmp_path)

        assert out["fails"] == []
        assert out["warns"] == []

    def test_exit_code_captured(self, tmp_path: Path) -> None:
        with _patch_runner("FAIL something\n", exit_code=1):
            out = collect_doctor_summary(tmp_path)

        assert out["exit_code"] == 1
