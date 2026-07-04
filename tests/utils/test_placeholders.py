"""Unresolved-placeholder counting — the shared doc-gate rule."""

from __future__ import annotations

from cataforge.utils.placeholders import count_unresolved_placeholders


def test_counts_each_marker() -> None:
    assert count_unresolved_placeholders("TODO here\nTBD there\nFIXME last") == 3


def test_multiple_markers_on_one_line_all_count() -> None:
    assert count_unresolved_placeholders("TODO and TBD and FIXME") == 3


def test_assumption_line_is_exempt() -> None:
    # A marker is cleared only when its own line carries [ASSUMPTION].
    assert count_unresolved_placeholders("TODO resolve later [ASSUMPTION] default 30") == 0


def test_exemption_is_per_line_not_global() -> None:
    # An [ASSUMPTION] on one line must not cancel a bare TODO on another.
    text = "line1 [ASSUMPTION] ok\nline2 TODO still open"
    assert count_unresolved_placeholders(text) == 1


def test_clean_text_is_zero() -> None:
    assert count_unresolved_placeholders("all acceptance criteria are concrete") == 0
