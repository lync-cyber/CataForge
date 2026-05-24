"""Tests for notify_util escape correctness across platforms."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from cataforge.hook.scripts.notify_util import (
    _notify_linux,
    _notify_macos,
    _notify_windows,
)

EVIL_TITLE = "Test 'apostrophe' and \"quote\""
EVIL_MESSAGE = "line1\nline2 with $env:PATH"


@pytest.fixture()
def mock_subprocess_run() -> MagicMock:
    with patch("cataforge.hook.scripts.notify_util.subprocess.run") as m:
        yield m


class TestWindowsToastEscape:
    def test_apostrophe_in_title_does_not_break_ps_string(
        self, mock_subprocess_run: MagicMock
    ) -> None:
        _notify_windows(EVIL_TITLE, EVIL_MESSAGE)

        assert mock_subprocess_run.called
        ps_script = mock_subprocess_run.call_args[0][0][-1]
        # html.escape encodes ' -> &#x27; so single-quoted PS string stays safe
        assert "&#x27;" in ps_script
        load_xml_line = next(
            line for line in ps_script.splitlines() if "LoadXml" in line
        )
        inner = load_xml_line.split("LoadXml('", 1)[1].rsplit("')", 1)[0]
        assert "'" not in inner

    def test_double_quote_in_message_is_html_escaped(
        self, mock_subprocess_run: MagicMock
    ) -> None:
        _notify_windows("Title", 'msg with "quotes"')

        ps_script = mock_subprocess_run.call_args[0][0][-1]
        assert "&quot;" in ps_script

    def test_subprocess_called_with_powershell_argv(
        self, mock_subprocess_run: MagicMock
    ) -> None:
        _notify_windows("Hello", "World")

        mock_subprocess_run.assert_called_once()
        cmd = mock_subprocess_run.call_args[0][0]
        assert cmd[:3] == ["powershell", "-NoProfile", "-Command"]


class TestMacOsOsascriptEscape:
    def test_double_quote_in_title_is_escaped(
        self, mock_subprocess_run: MagicMock
    ) -> None:
        _notify_macos(EVIL_TITLE, "normal message")

        mock_subprocess_run.assert_called_once()
        cmd = mock_subprocess_run.call_args[0][0]
        assert cmd[:2] == ["osascript", "-e"]
        script = cmd[2]
        expected_safe_title = EVIL_TITLE.replace('"', '\\"')
        assert expected_safe_title in script

    def test_double_quote_in_message_is_escaped(
        self, mock_subprocess_run: MagicMock
    ) -> None:
        _notify_macos("Normal title", 'message with "quotes"')

        cmd = mock_subprocess_run.call_args[0][0]
        script = cmd[2]
        assert '\\"' in script

    def test_evil_title_and_message_together(
        self, mock_subprocess_run: MagicMock
    ) -> None:
        _notify_macos(EVIL_TITLE, EVIL_MESSAGE)

        cmd = mock_subprocess_run.call_args[0][0]
        script = cmd[2]
        expected_safe_title = EVIL_TITLE.replace('"', '\\"')
        expected_safe_msg = EVIL_MESSAGE.replace('"', '\\"')
        assert expected_safe_title in script
        assert expected_safe_msg in script

    def test_unescaped_quote_not_present_in_title_slot(
        self, mock_subprocess_run: MagicMock
    ) -> None:
        _notify_macos('break "this"', "ok")

        script = mock_subprocess_run.call_args[0][0][2]
        marker = 'with title "'
        title_start = script.index(marker) + len(marker)
        # Content after the marker up to (but not including) the closing "
        # must not contain a bare (unescaped) double-quote
        remainder = script[title_start:]
        i = 0
        while i < len(remainder):
            if remainder[i] == "\\" and i + 1 < len(remainder) and remainder[i + 1] == '"':
                i += 2
                continue
            if remainder[i] == '"':
                # This is the closing quote — must be the last char
                assert i == len(remainder) - 1
                break
            i += 1


class TestLinuxNotifySend:
    def test_argv_list_no_shell_injection(
        self, mock_subprocess_run: MagicMock
    ) -> None:
        _notify_linux(EVIL_TITLE, EVIL_MESSAGE)

        mock_subprocess_run.assert_called_once()
        call_kwargs = mock_subprocess_run.call_args[1]
        assert call_kwargs.get("shell", False) is False
        cmd = mock_subprocess_run.call_args[0][0]
        assert cmd[0] == "notify-send"
        assert EVIL_TITLE in cmd
        assert EVIL_MESSAGE in cmd

    def test_urgency_flag_included(self, mock_subprocess_run: MagicMock) -> None:
        _notify_linux("t", "m", urgency=True)

        cmd = mock_subprocess_run.call_args[0][0]
        assert "--urgency=critical" in cmd

    def test_no_urgency_flag_when_false(self, mock_subprocess_run: MagicMock) -> None:
        _notify_linux("t", "m", urgency=False)

        cmd = mock_subprocess_run.call_args[0][0]
        assert "--urgency=critical" not in cmd
