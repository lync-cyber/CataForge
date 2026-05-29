"""Tests for cataforge.interface.cli.ui — capability detection, rendering, prompts."""

from __future__ import annotations

import io

import pytest

from cataforge.interface.cli.ui import (
    UI,
    ChoiceOption,
    DiagPattern,
    NextStep,
    _detect_color,
    _detect_unicode,
    _visible_width,
)

# ---------------------------------------------------------------------------
# Capability detection
# ---------------------------------------------------------------------------


def test_no_color_env_disables_color(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.delenv("CLICOLOR_FORCE", raising=False)
    assert _detect_color() is False


def test_clicolor_force_enables_color(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("CLICOLOR_FORCE", "1")
    assert _detect_color() is True


def test_cataforge_no_color_disables_color(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("CLICOLOR_FORCE", raising=False)
    monkeypatch.setenv("CATAFORGE_NO_COLOR", "1")
    assert _detect_color() is False


def test_cataforge_no_unicode_disables_unicode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CATAFORGE_NO_UNICODE", "1")
    assert _detect_unicode() is False


# ---------------------------------------------------------------------------
# Rendering — colour ON/OFF, unicode ON/OFF
# ---------------------------------------------------------------------------


def _make_ui(**kwargs) -> tuple[UI, io.StringIO, io.StringIO]:
    out = io.StringIO()
    err = io.StringIO()
    return UI(stdout=out, stderr=err, **kwargs), out, err


class _BrokenStream:
    """StringIO-shaped stub that raises a configurable exception on
    every ``write`` call. Lets the ``_write`` exception split (C9) be
    exercised without depending on actual broken pipes."""

    def __init__(self, exc: BaseException) -> None:
        self._exc = exc
        self.flushed = False

    def write(self, *_a, **_kw) -> int:
        raise self._exc

    def flush(self) -> None:
        self.flushed = True


def test_write_silently_swallows_brokenpipe(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """``BrokenPipeError`` (e.g. ``cataforge ... | head``) must not
    bubble up and must not log — the canonical CLI shape is to go
    quiet when the pipe closes downstream."""
    import logging

    stdout = _BrokenStream(BrokenPipeError("simulated broken pipe"))
    ui = UI(stdout=stdout, stderr=io.StringIO(), color=False, unicode=False)

    caplog.set_level(logging.DEBUG, logger="cataforge.interface.cli.ui")
    # Must not raise.
    ui.ok("doesn't matter")

    # Pre-fix this would have logged nothing either, so checking
    # absence of log records pins the new behaviour: BrokenPipeError
    # specifically stays out of the log stream too.
    pipe_records = [r for r in caplog.records if "BrokenPipe" in r.getMessage()]
    assert pipe_records == [], (
        f"BrokenPipeError must not produce log noise; got {pipe_records!r}"
    )


def test_write_logs_valueerror_at_debug(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """``ValueError`` on stream write (typically "I/O operation on
    closed file" inside pytest CliRunner) must NOT be silently dropped
    the way it was pre-fix: that lumped it together with
    BrokenPipeError and made a real ValueError escaping from a future
    stream-shaped object completely invisible. Now it lands at
    DEBUG so users running with ``--verbose`` / tracing can see it."""
    import logging

    stdout = _BrokenStream(ValueError("I/O operation on closed file"))
    ui = UI(stdout=stdout, stderr=io.StringIO(), color=False, unicode=False)

    caplog.set_level(logging.DEBUG, logger="cataforge.interface.cli.ui")
    # Must not raise.
    ui.ok("doesn't matter")

    debug_records = [
        r for r in caplog.records if "ui write got ValueError" in r.getMessage()
    ]
    assert debug_records, (
        f"ValueError on write must be logged at DEBUG; got {caplog.records!r}"
    )
    assert debug_records[0].levelno == logging.DEBUG


def test_ok_emits_glyph_and_message() -> None:
    ui, out, _ = _make_ui(color=False, unicode=True)
    ui.ok("everything good")
    assert "✔" in out.getvalue()
    assert "everything good" in out.getvalue()


def test_fail_goes_to_stderr() -> None:
    ui, out, err = _make_ui(color=False, unicode=True)
    ui.fail("bad")
    assert "bad" in err.getvalue()
    assert "bad" not in out.getvalue()


def test_warn_goes_to_stderr() -> None:
    ui, out, err = _make_ui(color=False, unicode=True)
    ui.warn("careful")
    assert "careful" in err.getvalue()
    assert "careful" not in out.getvalue()


def test_color_off_strips_ansi() -> None:
    ui, out, _ = _make_ui(color=False, unicode=True)
    ui.ok("clean")
    assert "\x1b[" not in out.getvalue()


def test_color_on_emits_ansi() -> None:
    ui, out, _ = _make_ui(color=True, unicode=True)
    ui.ok("colored")
    assert "\x1b[" in out.getvalue()


def test_unicode_off_uses_ascii_fallback() -> None:
    ui, out, _ = _make_ui(color=False, unicode=False)
    ui.ok("ascii")
    ui.fail("nope")
    ui.warn("hmm")
    ui.info("note")
    combined = out.getvalue() + ""
    assert "[OK]" in combined
    assert "✔" not in combined
    # fail/warn go to stderr; verify via separate UI
    ui2, _, err2 = _make_ui(color=False, unicode=False)
    ui2.fail("nope")
    ui2.warn("hmm")
    assert "[FAIL]" in err2.getvalue()
    assert "[WARN]" in err2.getvalue()


# ---------------------------------------------------------------------------
# Header / section
# ---------------------------------------------------------------------------


def test_header_includes_title_and_subtitle() -> None:
    ui, out, _ = _make_ui(color=False, unicode=True)
    ui.header("Doctor", subtitle="Diagnose framework integrity")
    text = out.getvalue()
    assert "Doctor" in text
    assert "Diagnose framework integrity" in text


def test_section_uses_star_prefix() -> None:
    ui, out, _ = _make_ui(color=False, unicode=True)
    ui.section("Environment")
    assert "[*] Environment" in out.getvalue()


# ---------------------------------------------------------------------------
# Table
# ---------------------------------------------------------------------------


def test_table_aligns_columns() -> None:
    ui, out, _ = _make_ui(color=False, unicode=True)
    ui.table(
        headers=["tool", "status"],
        rows=[["ruff", "missing"], ["docker", "ok"]],
    )
    lines = [line for line in out.getvalue().splitlines() if line.strip()]
    # 1 header + 1 rule + 2 data rows
    assert len(lines) == 4
    # All data rows start at the same indent
    indents = {len(line) - len(line.lstrip()) for line in lines}
    assert len(indents) == 1


def test_table_handles_colored_cells_width() -> None:
    ui, out, _ = _make_ui(color=True, unicode=True)
    coloured_cell = "\x1b[31mfail\x1b[0m"
    ui.table(headers=["k", "v"], rows=[["x", coloured_cell], ["yy", "ok"]])
    # No assertion on exact width — just ensure no crash and output is non-empty
    assert out.getvalue().strip()


def test_table_empty_inputs_no_op() -> None:
    ui, out, _ = _make_ui(color=False, unicode=True)
    ui.table(headers=[], rows=[])
    assert out.getvalue() == ""


# ---------------------------------------------------------------------------
# KV / bullets / code
# ---------------------------------------------------------------------------


def test_kv_pairs_align_keys() -> None:
    ui, out, _ = _make_ui(color=False, unicode=True)
    ui.kv({"short": "a", "long-key": "b"})
    lines = out.getvalue().splitlines()
    # both keys padded to same width: "short   " and "long-key"
    assert all(":" not in line for line in lines)  # we use spaces, not colons
    assert "short" in lines[0]
    assert "long-key" in lines[1]


def test_bullets_render_items() -> None:
    ui, out, _ = _make_ui(color=False, unicode=True)
    ui.bullets(["one", "two", "three"])
    assert out.getvalue().count("•") == 3


def test_code_block_indents() -> None:
    ui, out, _ = _make_ui(color=False, unicode=True)
    ui.code("cataforge doctor\ncataforge deploy")
    for line in out.getvalue().splitlines():
        assert line.startswith("    ")


# ---------------------------------------------------------------------------
# Next steps & diagnose
# ---------------------------------------------------------------------------


def test_next_steps_renders_command_and_why() -> None:
    ui, out, _ = _make_ui(color=False, unicode=True)
    ui.next_steps([
        NextStep("cataforge doctor", "verify integrity"),
        NextStep("cataforge deploy"),
    ])
    text = out.getvalue()
    assert "下一步" in text
    assert "cataforge doctor" in text
    assert "verify integrity" in text
    assert "cataforge deploy" in text


def test_next_steps_accepts_plain_strings() -> None:
    ui, out, _ = _make_ui(color=False, unicode=True)
    ui.next_steps(["cataforge doctor"])
    assert "cataforge doctor" in out.getvalue()


def test_next_steps_empty_is_no_op() -> None:
    ui, out, _ = _make_ui(color=False, unicode=True)
    ui.next_steps([])
    assert out.getvalue() == ""


def test_diagnose_matches_substring_pattern() -> None:
    ui, out, _ = _make_ui(color=False, unicode=True)
    pattern = DiagPattern(
        needle="EADDRINUSE",
        diagnosis="port in use",
        fix_action="kill the process",
        fix_command="cataforge penpot stop",
    )
    matched = ui.diagnose("Error: listen EADDRINUSE :::4401", [pattern])
    text = out.getvalue()
    assert matched == [pattern]
    assert "port in use" in text
    assert "cataforge penpot stop" in text


def test_diagnose_matches_regex_pattern() -> None:
    import re

    ui, out, _ = _make_ui(color=False, unicode=True)
    pattern = DiagPattern(
        needle=re.compile(r"ERR_PNPM_IGNORED_BUILDS"),
        diagnosis="pnpm blocked",
        fix_action="set env var",
    )
    matched = ui.diagnose("ERR_PNPM_IGNORED_BUILDS triggered", [pattern])
    assert matched == [pattern]
    assert "pnpm blocked" in out.getvalue()


def test_diagnose_returns_empty_when_no_match() -> None:
    ui, out, _ = _make_ui(color=False, unicode=True)
    pattern = DiagPattern(needle="xyz", diagnosis="x", fix_action="x")
    assert ui.diagnose("nothing here", [pattern]) == []
    assert out.getvalue() == ""


# ---------------------------------------------------------------------------
# Interactive prompts
# ---------------------------------------------------------------------------


def test_prompt_choice_returns_selected_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("builtins.input", lambda _prompt="": "2")
    ui, _, _ = _make_ui(color=False, unicode=True)
    choice = ui.prompt_choice(
        "Pick one",
        [ChoiceOption("1", "Foo"), ChoiceOption("2", "Bar")],
    )
    assert choice == "2"


def test_prompt_choice_falls_back_to_default_on_eof(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _eof(_prompt: str = "") -> str:
        raise EOFError

    monkeypatch.setattr("builtins.input", _eof)
    ui, _, _ = _make_ui(color=False, unicode=True)
    choice = ui.prompt_choice(
        "Pick",
        [ChoiceOption("1", "A"), ChoiceOption("2", "B")],
        default="2",
    )
    assert choice == "2"


def test_prompt_choice_empty_input_uses_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("builtins.input", lambda _prompt="": "")
    ui, _, _ = _make_ui(color=False, unicode=True)
    choice = ui.prompt_choice(
        "Pick",
        [ChoiceOption("1", "A"), ChoiceOption("2", "B")],
    )
    assert choice == "1"


def test_prompt_choice_retries_on_invalid_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs = iter(["9", "z", "1"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))
    ui, _, _ = _make_ui(color=False, unicode=True)
    choice = ui.prompt_choice(
        "Pick",
        [ChoiceOption("1", "A"), ChoiceOption("2", "B")],
    )
    assert choice == "1"


def test_prompt_confirm_yes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("builtins.input", lambda _prompt="": "y")
    ui, _, _ = _make_ui(color=False, unicode=True)
    assert ui.prompt_confirm("ok?") is True


def test_prompt_confirm_no(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("builtins.input", lambda _prompt="": "n")
    ui, _, _ = _make_ui(color=False, unicode=True)
    assert ui.prompt_confirm("ok?") is False


def test_prompt_confirm_default_on_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("builtins.input", lambda _prompt="": "")
    ui, _, _ = _make_ui(color=False, unicode=True)
    assert ui.prompt_confirm("ok?", default=True) is True
    assert ui.prompt_confirm("ok?", default=False) is False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def test_visible_width_strips_ansi() -> None:
    assert _visible_width("hello") == 5
    assert _visible_width("\x1b[31mhello\x1b[0m") == 5
    assert _visible_width("\x1b[1m\x1b[31mhi\x1b[0m") == 2


# ---------------------------------------------------------------------------
# Step / hr
# ---------------------------------------------------------------------------


def test_step_renders_progress_marker() -> None:
    ui, out, _ = _make_ui(color=False, unicode=True)
    ui.step(2, 5, "deploy artefacts")
    assert "[2/5]" in out.getvalue()
    assert "deploy artefacts" in out.getvalue()


def test_hr_emits_horizontal_rule() -> None:
    ui, out, _ = _make_ui(color=False, unicode=True)
    ui.hr()
    assert "━" in out.getvalue()
