"""Plugin discovery + registration contract."""

from __future__ import annotations

import json
import sys
import textwrap
import types
from pathlib import Path

import pytest

from cataforge.kg.plugin_hooks import (
    PluginError,
    PluginRegistry,
    find_protocol,
    load_plugins,
)


def _write_framework_cfg(root: Path, decl: list[dict[str, str]]) -> None:
    (root / ".cataforge").mkdir(parents=True, exist_ok=True)
    (root / ".cataforge" / "framework.json").write_text(
        json.dumps({"kg": {"plugins": decl}}, indent=2),
        encoding="utf-8",
    )


def _install_synthetic_plugin(
    name: str, body: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Materialise a fake plugin module under sys.modules for the test."""
    mod = types.ModuleType(name)
    exec(textwrap.dedent(body), mod.__dict__)
    monkeypatch.setitem(sys.modules, name, mod)


# ---------- happy path ----------

def test_load_plugins_imports_and_calls_register(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_synthetic_plugin(
        "syn_kg_plugin",
        """
        class StubBackend:
            name = "stub"
            def on_load(self, project_root):
                return None
            def on_dispose(self):
                pass

        def register(registry):
            registry.register_store_backend(StubBackend())
        """,
        monkeypatch,
    )
    _write_framework_cfg(tmp_path, [
        {"module": "syn_kg_plugin", "hook": "StoreBackendPlugin"},
    ])
    reg = load_plugins(tmp_path)
    assert "stub" in reg.store_backends


# ---------- missing config ----------

def test_load_plugins_no_config_returns_empty(tmp_path: Path) -> None:
    reg = load_plugins(tmp_path)
    assert isinstance(reg, PluginRegistry)
    assert reg.store_backends == {}
    assert reg.adapter_plugins == {}


# ---------- error paths ----------

def test_unknown_hook_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_synthetic_plugin(
        "syn_bad_hook",
        "def register(r): pass\n",
        monkeypatch,
    )
    _write_framework_cfg(tmp_path, [
        {"module": "syn_bad_hook", "hook": "TotallyMadeUpPlugin"},
    ])
    with pytest.raises(PluginError) as exc:
        load_plugins(tmp_path)
    assert "unknown plugin hook" in str(exc.value)


def test_missing_module_field_rejected(tmp_path: Path) -> None:
    _write_framework_cfg(tmp_path, [{"hook": "StoreBackendPlugin"}])
    with pytest.raises(PluginError) as exc:
        load_plugins(tmp_path)
    assert "module" in str(exc.value)


def test_module_not_importable_rejected(tmp_path: Path) -> None:
    _write_framework_cfg(tmp_path, [{
        "module": "no_such_package_xyz_42",
        "hook": "StoreBackendPlugin",
    }])
    with pytest.raises(PluginError) as exc:
        load_plugins(tmp_path)
    assert "not importable" in str(exc.value)


def test_module_without_register_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_synthetic_plugin(
        "syn_no_register",
        "# empty\n",
        monkeypatch,
    )
    _write_framework_cfg(tmp_path, [{
        "module": "syn_no_register",
        "hook": "StoreBackendPlugin",
    }])
    with pytest.raises(PluginError) as exc:
        load_plugins(tmp_path)
    assert "register(registry)" in str(exc.value)


def test_register_failure_wrapped_in_plugin_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_synthetic_plugin(
        "syn_boom",
        "def register(r): raise RuntimeError('boom')\n",
        monkeypatch,
    )
    _write_framework_cfg(tmp_path, [{
        "module": "syn_boom",
        "hook": "StoreBackendPlugin",
    }])
    with pytest.raises(PluginError) as exc:
        load_plugins(tmp_path)
    assert "boom" in str(exc.value)


# ---------- protocol lookup ----------

def test_find_protocol_returns_class() -> None:
    cls = find_protocol("StoreBackendPlugin")
    assert cls.__name__ == "StoreBackendPlugin"


def test_find_protocol_unknown_raises() -> None:
    with pytest.raises(PluginError):
        find_protocol("Nonexistent")


# ---------- existing registry merge ----------

def test_existing_registry_is_extended(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Passing an existing registry merges, doesn't replace."""

    class _Prior:
        name = "prior"

        def on_load(self, root):  # type: ignore[no-untyped-def]
            return None

        def on_dispose(self) -> None:
            pass

    reg = PluginRegistry()
    reg.register_store_backend(_Prior())

    _install_synthetic_plugin(
        "syn_secondary",
        """
        class Backend:
            name = "secondary"
            def on_load(self, root): return None
            def on_dispose(self): pass

        def register(registry):
            registry.register_store_backend(Backend())
        """,
        monkeypatch,
    )
    _write_framework_cfg(tmp_path, [
        {"module": "syn_secondary", "hook": "StoreBackendPlugin"},
    ])
    out = load_plugins(tmp_path, registry=reg)
    assert "prior" in out.store_backends
    assert "secondary" in out.store_backends
