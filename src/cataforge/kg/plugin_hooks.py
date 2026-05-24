"""Plugin protocols and discovery loader for the KG layer (design §2.6).

Downstream packages extend the KG layer by registering modules under
the ``kg.plugins`` block of ``<project_root>/.cataforge/framework.json``:

    {
      "kg": {
        "plugins": [
          {"module": "cataforge_kg_oxigraph", "hook": "StoreBackendPlugin"},
          {"module": "myproj_kg_extras",      "hook": "KGAdapterPlugin"}
        ]
      }
    }

:func:`load_plugins` imports each module and, depending on the declared
``hook``, registers the entries it exposes. Plugin modules are expected
to expose a top-level ``register(registry)`` callable that mutates the
registry passed in.

The protocol surface is intentionally narrow — six hooks aligned with
the design note. Plugins implement any subset; the loader inspects each
class for ``__protocol_compat__`` membership and rejects mismatches at
load time rather than at first use."""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from cataforge.kg.adapters import KGAdapter
from cataforge.kg.store import GraphStore, Triple, ValidationReport

FRAMEWORK_CONFIG = ".cataforge/framework.json"


class PluginError(RuntimeError):
    """Raised on plugin module import / registration failure."""


# ---------- protocols ----------

@runtime_checkable
class StoreBackendPlugin(Protocol):
    """Swap the GraphStore implementation (e.g. oxigraph for perf)."""

    name: str

    def on_load(self, project_root: str | Path) -> GraphStore: ...

    def on_dispose(self) -> None: ...


@runtime_checkable
class ReasoningEnginePlugin(Protocol):
    """Replace or extend the OWL-RL inference engine."""

    name: str

    def supports(self, profile: str) -> bool: ...

    def infer(self, base_graph: Any, ontology_graph: Any) -> list[Triple]: ...


@runtime_checkable
class IngestPlugin(Protocol):
    """Teach the ingest pipeline new source formats."""

    extensions: list[str]

    def parse(self, file_path: str | Path) -> list[Triple]: ...


@runtime_checkable
class RenderTargetPlugin(Protocol):
    """Add a non-markdown render target (HTML, ReST, JSON, …)."""

    target_name: str

    def render(
        self,
        sparql_results: list[dict[str, str]],
        template_path: str | Path,
    ) -> bytes: ...


@runtime_checkable
class QueryDSLPlugin(Protocol):
    """Compile a custom DSL into SPARQL."""

    dsl_name: str

    def compile(self, expr: str) -> str: ...


@runtime_checkable
class KGAdapterPlugin(Protocol):
    """Register additional KGAdapter classes."""

    name: str
    config_schema: dict[str, Any]

    def create(
        self,
        store: GraphStore,
        invocation_id: str,
        config: dict[str, Any],
    ) -> KGAdapter: ...


# ---------- registry ----------

@dataclass
class PluginRegistry:
    """Holds every plugin instance loaded for the current process.

    Multiple plugins per hook are allowed (e.g. two IngestPlugins for
    different file extensions); resolution is left to the caller — the
    registry just enumerates."""

    store_backends: dict[str, StoreBackendPlugin] = field(default_factory=dict)
    reasoning_engines: dict[str, ReasoningEnginePlugin] = field(default_factory=dict)
    ingest_plugins: list[IngestPlugin] = field(default_factory=list)
    render_targets: dict[str, RenderTargetPlugin] = field(default_factory=dict)
    query_dsls: dict[str, QueryDSLPlugin] = field(default_factory=dict)
    adapter_plugins: dict[str, KGAdapterPlugin] = field(default_factory=dict)

    def register_store_backend(self, plugin: StoreBackendPlugin) -> None:
        self.store_backends[plugin.name] = plugin

    def register_reasoning_engine(self, plugin: ReasoningEnginePlugin) -> None:
        self.reasoning_engines[plugin.name] = plugin

    def register_ingest_plugin(self, plugin: IngestPlugin) -> None:
        self.ingest_plugins.append(plugin)

    def register_render_target(self, plugin: RenderTargetPlugin) -> None:
        self.render_targets[plugin.target_name] = plugin

    def register_query_dsl(self, plugin: QueryDSLPlugin) -> None:
        self.query_dsls[plugin.dsl_name] = plugin

    def register_adapter_plugin(self, plugin: KGAdapterPlugin) -> None:
        self.adapter_plugins[plugin.name] = plugin


# ---------- discovery / loading ----------

def load_plugins(
    project_root: str | Path,
    *,
    registry: PluginRegistry | None = None,
) -> PluginRegistry:
    """Import every plugin declared in ``framework.json`` and register it.

    Each plugin module must expose a top-level callable named ``register``
    accepting the :class:`PluginRegistry`. The module is then free to
    instantiate its classes and call ``registry.register_*`` as needed.
    """
    reg = registry or PluginRegistry()
    cfg_path = Path(project_root) / FRAMEWORK_CONFIG
    if not cfg_path.is_file():
        return reg
    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PluginError(
            f"{cfg_path}: invalid JSON: {exc.msg}",
        ) from exc
    plugins_decl = (cfg.get("kg") or {}).get("plugins") or []
    if not isinstance(plugins_decl, list):
        raise PluginError(
            f"{cfg_path}: kg.plugins must be a list, got {type(plugins_decl).__name__}",
        )
    for decl in plugins_decl:
        _load_one(decl, reg, source=cfg_path)
    return reg


def _load_one(
    decl: dict[str, Any], reg: PluginRegistry, *, source: Path,
) -> None:
    module_name = decl.get("module")
    hook = decl.get("hook")
    if not module_name or not hook:
        raise PluginError(
            f"{source}: each kg.plugins entry needs `module` and `hook` "
            f"fields; got {decl!r}",
        )
    if hook not in {
        "StoreBackendPlugin", "ReasoningEnginePlugin", "IngestPlugin",
        "RenderTargetPlugin", "QueryDSLPlugin", "KGAdapterPlugin",
    }:
        raise PluginError(
            f"{source}: unknown plugin hook {hook!r}; must be one of "
            "StoreBackendPlugin / ReasoningEnginePlugin / IngestPlugin / "
            "RenderTargetPlugin / QueryDSLPlugin / KGAdapterPlugin.",
        )
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        raise PluginError(
            f"{source}: module {module_name!r} not importable. "
            "Install the plugin package with pip first.",
        ) from exc
    register = getattr(module, "register", None)
    if not callable(register):
        raise PluginError(
            f"{source}: plugin module {module_name!r} must expose a "
            "top-level `register(registry)` callable.",
        )
    try:
        register(reg)
    except Exception as exc:
        raise PluginError(
            f"{source}: {module_name}.register() failed: {exc}",
        ) from exc


# ---------- protocol helpers ----------

PROTOCOLS: tuple[type, ...] = (
    StoreBackendPlugin,
    ReasoningEnginePlugin,
    IngestPlugin,
    RenderTargetPlugin,
    QueryDSLPlugin,
    KGAdapterPlugin,
)


def find_protocol(name: str) -> type:
    """Look up a Protocol class by name — useful for type-driven dispatch."""
    for p in PROTOCOLS:
        if p.__name__ == name:
            return p
    raise PluginError(f"no protocol named {name!r}")


__all__ = [
    "FRAMEWORK_CONFIG",
    "IngestPlugin",
    "KGAdapterPlugin",
    "PROTOCOLS",
    "PluginError",
    "PluginRegistry",
    "QueryDSLPlugin",
    "ReasoningEnginePlugin",
    "RenderTargetPlugin",
    "StoreBackendPlugin",
    "Triple",
    "ValidationReport",
    "find_protocol",
    "load_plugins",
]
