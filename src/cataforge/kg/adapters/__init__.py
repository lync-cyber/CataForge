"""KG adapter registry and built-in adapters.

A KG adapter is the contract between a SKILL / AGENT dispatch and the
knowledge graph (design §3). It does two things per invocation:

1. :meth:`KGAdapter.pre_dispatch_context` — read SPARQL queries declared
   in the skill's ``kg_adapter.config.pre_dispatch_queries`` block, run
   them, and return a dict the harness serialises into the LLM prompt.
2. :meth:`KGAdapter.write_back` — convert the agent's JSON output into
   triples (via the schema referenced by ``write_back_schema``) and
   append them to the store, scoped to the invocation's named graph.

Built-in adapters live in submodules of this package; the registry below
maps adapter ``name`` → class so frontmatter can refer to them by name.
Downstream extensions ship their own classes via the ``KGAdapterPlugin``
hook (design §2.6) and call :func:`register` on import.
"""

from __future__ import annotations

from cataforge.kg.adapters.base import (
    AdapterError,
    KGAdapter,
    SchemaDrivenAdapter,
    triples_from_schema,
)
from cataforge.kg.adapters.doc_read import DocReadAdapter
from cataforge.kg.adapters.feature_authoring import FeatureAuthoringAdapter
from cataforge.kg.adapters.module_implements import ModuleImplementsAdapter
from cataforge.kg.adapters.task_decompose import TaskDecomposeAdapter
from cataforge.kg.adapters.test_validates import TestValidatesAdapter
from cataforge.kg.adapters.ui_renders import UIRendersAdapter

_REGISTRY: dict[str, type[KGAdapter]] = {}


def register(adapter_cls: type[KGAdapter]) -> type[KGAdapter]:
    """Register an adapter class under its ``name`` attribute.

    Re-registration with the same name is rejected — the harness needs
    deterministic name → class resolution. Plugins that intentionally
    shadow a built-in should first call :func:`unregister`.
    """
    name = adapter_cls.name
    if not name:
        raise AdapterError(
            f"{adapter_cls.__name__} must declare a non-empty class attribute "
            "`name` before registration."
        )
    if name in _REGISTRY:
        existing = _REGISTRY[name].__name__
        raise AdapterError(
            f"adapter name {name!r} already registered to {existing}; "
            "call unregister() first to shadow it."
        )
    _REGISTRY[name] = adapter_cls
    return adapter_cls


def unregister(name: str) -> None:
    """Remove an adapter from the registry (used by plugin shadowing)."""
    _REGISTRY.pop(name, None)


def get(name: str) -> type[KGAdapter]:
    """Look up an adapter class by name; raise on miss."""
    try:
        return _REGISTRY[name]
    except KeyError as exc:
        raise AdapterError(
            f"no adapter registered under {name!r}; "
            f"known: {sorted(_REGISTRY)}"
        ) from exc


def names() -> list[str]:
    """Return all registered adapter names, sorted."""
    return sorted(_REGISTRY)


def builtin_classes() -> tuple[type[KGAdapter], ...]:
    """Tuple of ship-with-framework adapter classes (registration order)."""
    return _BUILTIN


_BUILTIN: tuple[type[KGAdapter], ...] = (
    FeatureAuthoringAdapter,
    ModuleImplementsAdapter,
    TaskDecomposeAdapter,
    TestValidatesAdapter,
    DocReadAdapter,
    UIRendersAdapter,
)


for _cls in _BUILTIN:
    register(_cls)


__all__ = [
    "AdapterError",
    "DocReadAdapter",
    "FeatureAuthoringAdapter",
    "KGAdapter",
    "ModuleImplementsAdapter",
    "SchemaDrivenAdapter",
    "TaskDecomposeAdapter",
    "TestValidatesAdapter",
    "UIRendersAdapter",
    "builtin_classes",
    "get",
    "names",
    "register",
    "triples_from_schema",
    "unregister",
]
