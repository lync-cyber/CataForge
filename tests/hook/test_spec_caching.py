"""_spec_entry_for_script caches load_hooks_spec across repeated calls."""

from __future__ import annotations

import pytest

import cataforge.runtime.hook.bridge as bridge
from cataforge.runtime.hook.base import _spec_entry_for_script, matches_script_filters


@pytest.fixture(autouse=True)
def _clear_spec_cache() -> None:
    _spec_entry_for_script.cache_clear()


def _make_spec(script_name: str = "lint_format") -> dict:
    return {
        "schema_version": 2,
        "hooks": {
            "PostToolUse": [
                {
                    "script": script_name,
                    "type": "observe",
                    "matcher_capability": "file_edit",
                },
            ]
        },
    }


class TestSpecCaching:
    def test_load_hooks_spec_called_once_for_same_script(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        call_count = 0
        spec = _make_spec("lint_format")

        def counting_load(_p=None) -> dict:
            nonlocal call_count
            call_count += 1
            return spec

        monkeypatch.setattr(bridge, "load_hooks_spec", counting_load)

        data = {"tool_input": {"file_path": "foo.py"}}
        matches_script_filters(data, "lint_format")
        matches_script_filters(data, "lint_format")
        matches_script_filters(data, "lint_format")

        assert call_count == 1, (
            f"load_hooks_spec called {call_count} times; expected 1 (cached)"
        )

    def test_different_script_names_each_call_once(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        call_count = 0
        spec = _make_spec("lint_format")

        def counting_load(_p=None) -> dict:
            nonlocal call_count
            call_count += 1
            return spec

        monkeypatch.setattr(bridge, "load_hooks_spec", counting_load)

        data = {"tool_input": {"file_path": "foo.py"}}
        matches_script_filters(data, "lint_format")
        matches_script_filters(data, "lint_format")
        matches_script_filters(data, "other_script")
        matches_script_filters(data, "other_script")

        assert call_count == 2, (
            f"load_hooks_spec called {call_count} times; expected 2 (one per unique script name)"
        )

    def test_cache_clear_reloads_spec(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        call_count = 0
        spec = _make_spec("lint_format")

        def counting_load(_p=None) -> dict:
            nonlocal call_count
            call_count += 1
            return spec

        monkeypatch.setattr(bridge, "load_hooks_spec", counting_load)

        data = {"tool_input": {"file_path": "foo.py"}}
        matches_script_filters(data, "lint_format")
        _spec_entry_for_script.cache_clear()
        matches_script_filters(data, "lint_format")

        assert call_count == 2
