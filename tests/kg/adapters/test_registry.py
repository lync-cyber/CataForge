"""Registry contract — name uniqueness, lookup, builtins all wired."""

from __future__ import annotations

from typing import Any

import pytest

from cataforge.kg import adapters
from cataforge.kg.adapters import (
    AdapterError,
    KGAdapter,
    builtin_classes,
    get,
    names,
    register,
    unregister,
)
from cataforge.kg.store import Triple


def test_six_builtins_registered() -> None:
    expected = {
        "feature_authoring",
        "module_implements",
        "task_decompose",
        "test_validates",
        "doc_read",
        "ui_renders",
    }
    assert expected.issubset(set(names()))


def test_get_returns_class() -> None:
    cls = get("feature_authoring")
    assert cls is adapters.FeatureAuthoringAdapter


def test_get_unknown_raises() -> None:
    with pytest.raises(AdapterError) as exc:
        get("does-not-exist")
    assert "no adapter registered" in str(exc.value)


def test_register_rejects_duplicate() -> None:
    class _Dup(KGAdapter):
        name = "feature_authoring"

        def pre_dispatch_context(self, params: dict[str, Any]) -> dict[str, Any]:
            return {}

        def write_back(self, agent_output: dict[str, Any]) -> list[Triple]:
            return []

    with pytest.raises(AdapterError) as exc:
        register(_Dup)
    assert "already registered" in str(exc.value)


def test_register_requires_name() -> None:
    class _Nameless(KGAdapter):
        name = ""

        def pre_dispatch_context(self, params: dict[str, Any]) -> dict[str, Any]:
            return {}

        def write_back(self, agent_output: dict[str, Any]) -> list[Triple]:
            return []

    with pytest.raises(AdapterError) as exc:
        register(_Nameless)
    assert "must declare" in str(exc.value)


def test_unregister_then_reregister() -> None:
    """Plugin-shadow flow: pop builtin, register replacement, restore."""

    class _Replacement(KGAdapter):
        name = "ui_renders"

        def pre_dispatch_context(self, params: dict[str, Any]) -> dict[str, Any]:
            return {"replacement": True}

        def write_back(self, agent_output: dict[str, Any]) -> list[Triple]:
            return []

    original = get("ui_renders")
    try:
        unregister("ui_renders")
        register(_Replacement)
        assert get("ui_renders") is _Replacement
    finally:
        unregister("ui_renders")
        register(original)
    assert get("ui_renders") is original


def test_builtin_classes_is_tuple() -> None:
    classes = builtin_classes()
    assert isinstance(classes, tuple)
    assert len(classes) == 6
