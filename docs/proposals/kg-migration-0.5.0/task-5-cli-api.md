# Task 5 — CLI and Python API Design

> KG Migration 0.5.0 · Agent-T5 produced · grounded in Task 3 (`task-3-domain-ontology.md`) and Task 2 (`task-2-toolstack.md` §2.4).

Anchors:
- Store backends: `Oxigraph` (RocksDB embedded) and `memory` (testing only). No remote-SPARQL endpoint.
- Coverage mode default: `strict` (cross-ref form `doc_id#§N.ITEM`). `mentions` is opt-in.
- All write operations serialize through `async with kg.transaction() as txn:`.
- Async pattern: sync read + `asyncio.to_thread`-wrapped async read + pure async write with `asyncio.Lock`.
- Backward-compat shim layer covers ≥5 business-doc call points from Task 1 §1.3.

Companion artifacts required by this task:
- `src/cataforge/kg/_models_core.py` — Pydantic v2 auto-generated from `schemas/core.yaml`
- `src/cataforge/kg/shapes/extra.shacl.ttl` — 3 hand-written SHACL invariants (see §3.2.4)
- `src/cataforge/kg/_shim.py` — backward-compat shim layer (§5.5)

---

## §5.1 CLI Command Set

All subcommands are under the `cataforge kg` group. Global options apply to every subcommand.

### Global options

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--db-path PATH` | path | `.cataforge/kg/store` | Path to the Oxigraph RocksDB directory |
| `--backend [oxigraph\|memory]` | enum | `oxigraph` | Storage backend |
| `--project-id URI` | string | auto-detect from `.cataforge/project.yaml` | Project root URI |
| `--timeout INT` | seconds | `30` | SPARQL query timeout |
| `--governance` | flag | off | Load the governance sub-ontology |
| `--output [table\|json\|turtle\|csv]` | enum | `table` | Output format |
| `--quiet` | flag | off | Suppress progress bars and INFO logs |
| `--verbose` | flag | off | Debug logging |

### Exit codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General runtime error |
| 2 | CLI usage / argument error |
| 3 | Validation / SHACL failure |
| 4 | Store not initialized (run `kg init` first) |
| 5 | Conflict detected (optimistic lock) |
| 6 | Query timeout |

---

### `cataforge kg init`

Initialize a new KG store for the current project.

```
cataforge kg init [OPTIONS]
```

| Argument / Flag | Type | Default | Description |
|----------------|------|---------|-------------|
| `--force` | flag | off | Overwrite an existing store |
| `--governance` | flag | off | Also initialize governance sub-ontology |
| `--seed PATH` | file | none | Seed the graph from a Turtle or JSON-LD file on creation |

**Output:** Prints the initialized store path, triple count, and schema version.

**Exit codes:** 0 on success; 1 if the path is not writable; 2 if `--force` not given and store already exists.

**Typical use:** First command after `cataforge deploy`; idempotent when `--force` is omitted and store already consistent.

---

### `cataforge kg import`

Ingest entities from Markdown documentation, JSON, or RDF.

```
cataforge kg import [OPTIONS] SOURCE [SOURCE ...]
```

| Argument / Flag | Type | Default | Description |
|----------------|------|---------|-------------|
| `SOURCE` | path(s) | required | Files or directories to import |
| `--format [markdown\|json\|turtle\|json-ld\|ntriples]` | enum | auto-detect | Source format |
| `--doc-type STR` | string | auto-detect | Override `doc_type` (e.g. `prd`, `arch`, `dev-plan`) |
| `--dry-run` | flag | off | Parse and validate without writing |
| `--coverage-mode [strict\|mentions]` | enum | `strict` | Cross-reference resolution mode |
| `--on-conflict [skip\|overwrite\|error]` | enum | `error` | Entity conflict strategy |
| `--batch-size INT` | int | `500` | Triples per transaction |

**Output (table):**

```
Imported  347 entities (1 204 triples) in 2.1 s
Warnings    2 (run with --verbose to list)
Errors      0
```

**Exit codes:** 0 on success; 3 if SHACL validation fails and `--on-conflict=error`; 1 on IO error.

**Typical use:**
```bash
# Import entire docs/ tree; strict cross-refs only
cataforge kg import docs/ --format markdown --coverage-mode strict

# Dry-run import of a single PRD to check for SHACL errors before committing
cataforge kg import docs/prd/prd-v2.md --dry-run
```

---

### `cataforge kg export`

Export KG entities back to Markdown (invokes the Task 4 pipeline).

```
cataforge kg export [OPTIONS] [ENTITY_IDS ...]
```

| Argument / Flag | Type | Default | Description |
|----------------|------|---------|-------------|
| `ENTITY_IDS` | positional | all | Specific entity IDs to export (e.g. `F-001 M-014`) |
| `--out-dir PATH` | path | `docs/` | Output directory root |
| `--format [markdown\|json\|turtle]` | enum | `markdown` | Output format |
| `--sort-by [sort_key\|entity_id\|updated_at]` | enum | `sort_key` | Export order (Q6 query) |
| `--dry-run` | flag | off | Show diff without writing files |
| `--overwrite` | flag | off | Overwrite existing Markdown sections |

**Output:** One line per exported file with entity count and path.

**Exit codes:** 0; 3 if sort_key invariant fails; 1 on write error.

**Typical use:**
```bash
# Full idempotent round-trip export
cataforge kg export --sort-by sort_key --overwrite

# Preview export diff for a specific feature
cataforge kg export F-001 --dry-run
```

---

### `cataforge kg query`

Execute a SPARQL query or a natural-language query against the graph.

```
cataforge kg query [OPTIONS] QUERY_OR_FILE
```

| Argument / Flag | Type | Default | Description |
|----------------|------|---------|-------------|
| `QUERY_OR_FILE` | string or path | required | SPARQL string, path to `.sparql` file, or natural-language prompt |
| `--nl` | flag | off | Treat input as natural language (LLM-translated to SPARQL) |
| `--timeout INT` | seconds | global default | Per-query override |
| `--limit INT` | int | 100 | Max rows |
| `--output [table\|json\|csv\|turtle]` | enum | `table` | |

**Output (table):**
```
feature      entity_id  title
----------   ---------  ----------------------------
cfprj:F-001  F-001      User authentication flow
cfprj:F-007  F-007      Password reset
```

**Exit codes:** 0; 6 on timeout; 2 on SPARQL parse error.

**Typical use:**
```bash
# Run a saved template
cataforge kg query queries/traceability.sparql --limit 50

# Ad-hoc SPARQL
cataforge kg query "SELECT ?f WHERE { ?f a cf:Feature . }" --output json

# Natural-language (requires LLM config)
cataforge kg query "Which features have no test cases?" --nl
```

---

### `cataforge kg trace`

Run a traceability chain query starting from a named business entity.

```
cataforge kg trace [OPTIONS] ENTITY_ID
```

| Argument / Flag | Type | Default | Description |
|----------------|------|---------|-------------|
| `ENTITY_ID` | positional | required | Starting entity (e.g. `REQ-001`, `F-001`, `C-014`) |
| `--from-requirement ID` | string | — | Alias: start from a requirement-layer entity |
| `--from-component ID` | string | — | Alias: start from an architecture component |
| `--from-feature ID` | string | — | Alias: start from a feature |
| `--direction [downstream\|upstream\|both]` | enum | `downstream` | Chain direction |
| `--max-depth INT` | int | `5` | Maximum hop depth |
| `--types LIST` | comma-str | all | Filter result types (e.g. `TestCase,Task`) |
| `--coverage` | flag | off | Append coverage status column |
| `--output [table\|json\|mermaid]` | enum | `table` | `mermaid` emits a graph diagram |

**Output (table):**
```
Traceability chain from F-001 (downstream, depth≤5)

Layer         Entity ID   Title                          Coverage
------------  ----------  ----------------------------   --------
Feature       F-001       User authentication flow       partial
Module        M-014       AuthService                    —
Task          T-021       Implement password hashing     done
TestCase      TC-007      Login valid credentials 200    pass
Release       REL-002     v1.2                           —
```

**Exit codes:** 0; 1 if entity not found; 3 if chain break detected (logged to EVENT-LOG).

**Typical use:**
```bash
# Full downstream chain from a feature
cataforge kg trace F-001 --direction downstream --coverage

# Upstream impact from a component
cataforge kg trace --from-component C-014 --direction upstream --output mermaid

# Check which requirements REQ-001 maps to in the task layer
cataforge kg trace REQ-001 --types Task,TestCase
```

---

### `cataforge kg add`

Add a new entity to the graph.

```
cataforge kg add [OPTIONS] ENTITY_TYPE ENTITY_ID
```

| Argument / Flag | Type | Default | Description |
|----------------|------|---------|-------------|
| `ENTITY_TYPE` | positional | required | LinkML class name (e.g. `Feature`, `Task`, `TestCase`) |
| `ENTITY_ID` | positional | required | Frontmatter ID (e.g. `F-042`) |
| `--title STR` | string | required | Entity title |
| `--slot KEY=VALUE` | repeatable | — | Arbitrary slot values |
| `--from-json PATH` | file | — | Load entity fields from JSON file |
| `--dry-run` | flag | off | Validate without writing |

**Output:** Prints URI of the created entity and triple count.

**Exit codes:** 0; 3 on SHACL failure; 5 on entity_id conflict.

**Typical use:**
```bash
cataforge kg add Feature F-042 --title "Offline sync" \
  --slot priority=high --slot status=draft

cataforge kg add TestCase TC-099 --title "Offline sync smoke test" \
  --slot verifies=F-042
```

---

### `cataforge kg update`

Update one or more slots of an existing entity.

```
cataforge kg update [OPTIONS] ENTITY_ID SLOT=VALUE [SLOT=VALUE ...]
```

| Argument / Flag | Type | Default | Description |
|----------------|------|---------|-------------|
| `ENTITY_ID` | positional | required | Entity to update (e.g. `F-001`) |
| `SLOT=VALUE` | positional | required | One or more slot assignments |
| `--dry-run` | flag | off | Show diff without writing |
| `--content-hash STR` | string | — | Optimistic lock: fail if current hash differs |

**Output:** Prints old vs. new slot values.

**Exit codes:** 0; 5 if `--content-hash` does not match (optimistic lock miss).

---

### `cataforge kg delete`

Delete an entity from the graph. Requires two-step confirmation.

```
cataforge kg delete [OPTIONS] ENTITY_ID [ENTITY_ID ...]
```

| Argument / Flag | Type | Default | Description |
|----------------|------|---------|-------------|
| `ENTITY_ID` | positional | required | One or more entity IDs |
| `--yes` | flag | off | Skip interactive confirmation prompt |
| `--cascade` | flag | off | Also delete inbound-reference edges |
| `--dry-run` | flag | off | Show what would be deleted |

**Confirmation flow (interactive):**

```
About to delete: cfprj:F-001 "User authentication flow"
  - 3 inbound edges would become dangling (use --cascade to remove them)
Type the entity ID to confirm: F-001
```

**Exit codes:** 0; 2 if confirmation fails; 3 if cascade would break SHACL constraints.

---

### `cataforge kg validate`

Run consistency checks: SHACL shapes, orphan-node detection, cross-reference integrity.

```
cataforge kg validate [OPTIONS]
```

| Argument / Flag | Type | Default | Description |
|----------------|------|---------|-------------|
| `--shapes PATH` | file | built-in | Extra SHACL shapes file |
| `--severity [info\|warning\|violation]` | enum | `warning` | Minimum severity to report |
| `--fix-orphans` | flag | off | Auto-remove orphan nodes (writes to store) |
| `--output [table\|json\|turtle]` | enum | `table` | |

**Output (table):**
```
Severity    Entity ID   Shape            Message
---------   ----------  ---------------  ----------------------------------------
violation   TC-012      cf:verifies-min  TestCase has no cf:verifies triple
warning     F-007       cf:coverage-adv  Feature has no inbound cf:verifies path
```

**Exit codes:** 0 (no violations); 3 (violations found).

---

### `cataforge kg snapshot`

Create a versioned snapshot of the current store state.

```
cataforge kg snapshot [OPTIONS] [LABEL]
```

| Argument / Flag | Type | Default | Description |
|----------------|------|---------|-------------|
| `LABEL` | positional | timestamp | Human-readable snapshot label |
| `--out-dir PATH` | path | `.cataforge/kg/snapshots/` | Snapshot storage directory |
| `--format [nquads\|turtle\|json-ld]` | enum | `nquads` | Serialization format |

**Output:** Snapshot path and triple count.

**Exit codes:** 0; 1 on write error.

---

### `cataforge kg rollback`

Restore the store to a previous snapshot.

```
cataforge kg rollback [OPTIONS] SNAPSHOT
```

| Argument / Flag | Type | Default | Description |
|----------------|------|---------|-------------|
| `SNAPSHOT` | positional | required | Snapshot label or path |
| `--yes` | flag | off | Skip confirmation |

**Confirmation flow:**

```
About to REPLACE current store with snapshot "2026-05-25T14:00"
This is irreversible without another snapshot. Type "rollback" to confirm:
```

**Exit codes:** 0; 2 if confirmation fails; 1 on IO error.

---

### `cataforge kg diff`

Show the semantic difference between two snapshots.

```
cataforge kg diff [OPTIONS] SNAPSHOT_A SNAPSHOT_B
```

| Argument / Flag | Type | Default | Description |
|----------------|------|---------|-------------|
| `SNAPSHOT_A` | positional | required | Base snapshot |
| `SNAPSHOT_B` | positional | required | Comparison snapshot |
| `--output [table\|json\|turtle\|patch]` | enum | `table` | `patch` emits a SPARQL UPDATE |
| `--filter-type STR` | string | — | Limit diff to one entity type |

**Output (table):**
```
Op      Entity ID   Predicate          Old value         New value
------  ----------  -----------------  ----------------  ----------------
+       F-042       cf:entity_id       —                 F-042
+       F-042       cf:title           —                 Offline sync
~       F-001       cf:status          draft             approved
-       TC-003      rdf:type           cf:TestCase       —
```

**Exit codes:** 0.

---

### `cataforge kg reconcile`

Beta: dual-track consistency — align strict cross-refs with the KG, optionally upgrading `mentions`-mode references.

```
cataforge kg reconcile [OPTIONS] [DOCS_PATH]
```

| Argument / Flag | Type | Default | Description |
|----------------|------|---------|-------------|
| `DOCS_PATH` | path | `docs/` | Root path to scan |
| `--coverage-mode [strict\|mentions]` | enum | `strict` | Resolution mode |
| `--upgrade` | flag | off | Promote `mentions`-style refs to strict `doc_id#§N.ITEM` form (codemod) |
| `--dry-run` | flag | off | Show proposed changes without writing |
| `--report PATH` | file | stdout | Write JSON reconciliation report |
| `--fail-on-unresolved` | flag | off | Exit 3 if any unresolved cross-refs remain |

**Mention → strict upgrade codemod:**

When `--upgrade` is given, the command:
1. Identifies all `mentions`-style cross-references in scanned documents.
2. Resolves each against the KG to find the canonical `doc_id#§N.ITEM` form.
3. Rewrites the source Markdown in-place (or prints the diff with `--dry-run`).
4. Emits a reconciliation report with per-document statistics.

**Exit codes:** 0; 3 if `--fail-on-unresolved` and unresolved refs exist; 1 on parse error.

**Typical use:**
```bash
# Validate strict cross-refs for entire docs/ tree
cataforge kg reconcile --coverage-mode strict --fail-on-unresolved

# Upgrade all legacy mention-style refs to strict form (preview first)
cataforge kg reconcile --upgrade --dry-run

# Apply upgrade and write JSON report
cataforge kg reconcile --upgrade --report .cataforge/reconcile-report.json
```

---

## §5.2 Python API

### KGConfig dataclass

```python
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


@dataclass
class KGConfig:
    """
    Configuration for a KnowledgeGraph connection.

    Parameters
    ----------
    store_backend:
        ``"oxigraph"`` — pyoxigraph RocksDB embedded (production default).
        ``"memory"``   — in-process only; data lost on process exit (testing).
    db_path:
        Filesystem path to the RocksDB store directory.
        Ignored when ``store_backend="memory"``.
    governance:
        When ``True``, load ``schemas/governance.yaml`` and lift
        ``docs/EVENT-LOG.jsonl`` into the graph.  Default ``False`` — business-
        only mode for downstream user projects.
    coverage_mode:
        ``"strict"``   — only strict cross-ref form ``doc_id#§N.ITEM`` is
                         resolved (default, recommended).
        ``"mentions"`` — legacy free-text mention resolution; opt-in only.
    query_timeout:
        Per-query SPARQL timeout in seconds.  Applies to both sync and async
        query paths.  ``None`` disables the timeout.
    max_transaction_retries:
        Optimistic-lock retry limit for transactional writes.
    base_namespace:
        Instance namespace prefix.
        Defaults to ``"https://cataforge.dev/instance/"``.
    ontology_namespace:
        Business ontology namespace prefix.
        Defaults to ``"https://cataforge.dev/ontology/"``.
    plugins_dir:
        Directory containing plugin YAML schemas.
        ``None`` disables plugin loading.
    """

    store_backend: Literal["oxigraph", "memory"] = "oxigraph"
    db_path: Path = field(default_factory=lambda: Path(".cataforge/kg/store"))
    governance: bool = False
    coverage_mode: Literal["strict", "mentions"] = "strict"
    query_timeout: float | None = 30.0
    max_transaction_retries: int = 3
    base_namespace: str = "https://cataforge.dev/instance/"
    ontology_namespace: str = "https://cataforge.dev/ontology/"
    plugins_dir: Path | None = None
```

---

### KnowledgeGraphProtocol

```python
from __future__ import annotations

from typing import Protocol, runtime_checkable

from cataforge.kg._config import KGConfig


@runtime_checkable
class KnowledgeGraphProtocol(Protocol):
    """
    Structural protocol that every KnowledgeGraph implementation must satisfy.

    Callers that accept any store backend should type-annotate against this
    protocol, not the concrete ``KnowledgeGraph`` class, to remain testable
    with ``memory`` backends.
    """

    @classmethod
    def connect(cls, config: KGConfig) -> "KnowledgeGraphProtocol":
        """Open a synchronous connection; blocks until the store is ready."""
        ...

    @classmethod
    async def aconnect(cls, config: KGConfig) -> "KnowledgeGraphProtocol":
        """Open an asynchronous connection."""
        ...

    def close(self) -> None:
        """Close the synchronous connection and flush pending buffers."""
        ...

    async def aclose(self) -> None:
        """Close the asynchronous connection."""
        ...

    def __enter__(self) -> "KnowledgeGraphProtocol": ...
    def __exit__(self, *exc: object) -> None: ...
    async def __aenter__(self) -> "KnowledgeGraphProtocol": ...
    async def __aexit__(self, *exc: object) -> None: ...
```

---

### KnowledgeGraph — connection management

```python
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, contextmanager
from typing import AsyncIterator, Iterator

import pyoxigraph as ox

from cataforge.kg._config import KGConfig
from cataforge.kg._query import QueryAPI
from cataforge.kg._trace import TraceAPI
from cataforge.kg._transaction import TransactionContext
from cataforge.kg._protocol import KnowledgeGraphProtocol


class KnowledgeGraph:
    """
    Top-level facade for the CataForge 0.5.0 knowledge graph.

    Implements :class:`KnowledgeGraphProtocol`.  The instance exposes three
    namespaced sub-APIs:

    - ``kg.query``  — read operations (sync + async read, plan_load)
    - ``kg.trace``  — traceability chain queries
    - ``kg.transaction()`` — async context manager for transactional writes

    Connection management
    ---------------------
    Sync:   ``with KnowledgeGraph.connect(config) as kg: ...``
    Async:  ``async with KnowledgeGraph.aconnect(config) as kg: ...``
    Both patterns guarantee proper store close/flush on exit.

    Thread safety
    -------------
    Read operations are safe to call concurrently.  All write operations are
    serialized through an internal ``asyncio.Lock``; concurrent ``transaction()``
    contexts queue and execute serially.
    """

    def __init__(self, store: ox.Store, config: KGConfig) -> None:
        self._store = store
        self._config = config
        self._write_lock = asyncio.Lock()
        self.query = QueryAPI(store, config)
        self.trace = TraceAPI(store, config)
        # Async-flavoured sub-APIs exposed via properties (see below)

    # ------------------------------------------------------------------
    # Sync connection
    # ------------------------------------------------------------------

    @classmethod
    @contextmanager
    def connect(cls, config: KGConfig) -> Iterator["KnowledgeGraph"]:
        """
        Open a synchronous connection.

        Parameters
        ----------
        config:
            Fully populated :class:`KGConfig`.

        Yields
        ------
        KnowledgeGraph
            A ready-to-use graph instance.

        Raises
        ------
        KGStoreNotInitializedError
            If ``store_backend="oxigraph"`` and ``db_path`` does not exist.
        """
        store = cls._open_store(config)
        kg = cls(store, config)
        try:
            yield kg
        finally:
            kg.close()

    # ------------------------------------------------------------------
    # Async connection
    # ------------------------------------------------------------------

    @classmethod
    @asynccontextmanager
    async def aconnect(cls, config: KGConfig) -> AsyncIterator["KnowledgeGraph"]:
        """
        Open an asynchronous connection.

        The store is opened in a thread (``asyncio.to_thread``) to avoid
        blocking the event loop during RocksDB startup.

        Parameters
        ----------
        config:
            Fully populated :class:`KGConfig`.

        Yields
        ------
        KnowledgeGraph
            A ready-to-use graph instance with async-capable sub-APIs.

        Raises
        ------
        KGStoreNotInitializedError
            If ``store_backend="oxigraph"`` and ``db_path`` does not exist.
        """
        store = await asyncio.to_thread(cls._open_store, config)
        kg = cls(store, config)
        try:
            yield kg
        finally:
            await kg.aclose()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Flush and close the underlying store (sync)."""
        self._store.flush()

    async def aclose(self) -> None:
        """Flush and close the underlying store (async)."""
        await asyncio.to_thread(self._store.flush)

    def __enter__(self) -> "KnowledgeGraph":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    async def __aenter__(self) -> "KnowledgeGraph":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    # ------------------------------------------------------------------
    # Transactional write context manager
    # ------------------------------------------------------------------

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator["TransactionContext"]:
        """
        Async transactional write context.

        All write operations (add / update / delete / bulk_insert) must be
        performed inside this context.  Concurrent callers queue; there is no
        deadlock risk because the lock is non-reentrant.

        Usage
        -----
        ::

            async with kg.transaction() as txn:
                await txn.add(feature)
                await txn.update("F-001", status="approved")

        Raises
        ------
        KGNodeConflictError
            On optimistic-lock failure after ``KGConfig.max_transaction_retries``
            attempts.
        KGGraphInconsistencyError
            If the final SHACL validation fails after all writes.
        """
        async with self._write_lock:
            txn = TransactionContext(self._store, self._config)
            try:
                yield txn
                await txn._commit()
            except Exception:
                await txn._rollback()
                raise

    # ------------------------------------------------------------------
    # Async-flavoured sub-APIs (thin wrappers that call asyncio.to_thread)
    # ------------------------------------------------------------------

    @property
    def atrace(self) -> "AsyncTraceAPI":
        """Async wrapper around :class:`TraceAPI`."""
        return AsyncTraceAPI(self.trace)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _open_store(config: KGConfig) -> ox.Store:
        if config.store_backend == "memory":
            return ox.Store()
        path = config.db_path
        if not path.exists():
            raise KGStoreNotInitializedError(
                f"Store path {path!r} does not exist. Run `cataforge kg init` first."
            )
        return ox.Store(str(path))
```

---

### QueryAPI — business-entity queries by SDLC layer

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

import pyoxigraph as ox

from cataforge.kg._config import KGConfig
from cataforge.kg._models_core import (
    Feature, Module, Component, Task, TestCase, SoftwareArtifact,
)
from cataforge.kg._exceptions import KGQueryTimeoutError


CF = "https://cataforge.dev/ontology/"
CFPRJ = "https://cataforge.dev/instance/"


@dataclass
class SearchResult:
    """A single hit from :meth:`QueryAPI.search`."""
    uri: str
    entity_id: str
    title: str
    entity_type: str
    score: float


@dataclass
class LoadPlan:
    """
    A token-budget-aware ordered load plan produced by :meth:`QueryAPI.plan_load`.

    Attributes
    ----------
    ordered_uris:
        Entity URIs in the recommended load order (topological + sort_key).
    estimated_tokens:
        Rough token count for the entire plan.
    dropped_uris:
        URIs that were requested but did not fit within ``token_budget``.
    """
    ordered_uris: list[str]
    estimated_tokens: int
    dropped_uris: list[str]


class QueryAPI:
    """
    Read-only queries organized by SDLC layer.

    All methods are synchronous.  For async callers, use
    ``await asyncio.to_thread(kg.query.<method>, ...)``, or use the
    async wrappers on the ``KnowledgeGraph.atrace`` property.

    Query timeout is applied to every SPARQL execution; raises
    :class:`KGQueryTimeoutError` on breach.
    """

    def __init__(self, store: ox.Store, config: KGConfig) -> None:
        self._store = store
        self._config = config

    # ------------------------------------------------------------------
    # Requirement layer
    # ------------------------------------------------------------------

    def requirement(self, req_id: str) -> SoftwareArtifact | None:
        """
        Fetch any Requirement-layer artifact by entity_id.

        Covers Feature, UserStory, and Epic via ``rdfs:subClassOf* cf:Requirement``.

        Parameters
        ----------
        req_id:
            Entity ID in any Requirement subclass format (e.g. ``"F-001"``,
            ``"EP-003"``, ``"US-012"``).

        Returns
        -------
        SoftwareArtifact or None
            The most specific Pydantic v2 model (Feature / UserStory / Epic),
            or ``None`` if the entity is not found.
        """
        ...

    def feature(self, feature_id: str) -> Feature | None:
        """
        Fetch a :class:`Feature` by entity_id (pattern ``F-NNN``).

        Parameters
        ----------
        feature_id:
            E.g. ``"F-001"``.

        Returns
        -------
        Feature or None
        """
        return self._fetch_typed("Feature", feature_id, Feature)

    # ------------------------------------------------------------------
    # Architecture layer
    # ------------------------------------------------------------------

    def component(self, comp_id: str) -> Component | None:
        """
        Fetch a :class:`Component` by entity_id (pattern ``C-NNN``).

        Parameters
        ----------
        comp_id:
            E.g. ``"C-014"``.

        Returns
        -------
        Component or None
        """
        return self._fetch_typed("Component", comp_id, Component)

    def module(self, module_id: str) -> Module | None:
        """
        Fetch a :class:`Module` by entity_id (pattern ``M-NNN``).

        Parameters
        ----------
        module_id:
            E.g. ``"M-014"``.

        Returns
        -------
        Module or None
        """
        return self._fetch_typed("Module", module_id, Module)

    # ------------------------------------------------------------------
    # Task / planning layer
    # ------------------------------------------------------------------

    def task(self, task_id: str) -> Task | None:
        """
        Fetch a :class:`Task` by entity_id (pattern ``T-NNN``).

        Parameters
        ----------
        task_id:
            E.g. ``"T-021"``.

        Returns
        -------
        Task or None
        """
        return self._fetch_typed("Task", task_id, Task)

    # ------------------------------------------------------------------
    # Test layer
    # ------------------------------------------------------------------

    def test_case(self, tc_id: str) -> TestCase | None:
        """
        Fetch a :class:`TestCase` by entity_id (pattern ``TC-NNN``).

        Parameters
        ----------
        tc_id:
            E.g. ``"TC-007"``.

        Returns
        -------
        TestCase or None
        """
        return self._fetch_typed("TestCase", tc_id, TestCase)

    # ------------------------------------------------------------------
    # Generic accessors
    # ------------------------------------------------------------------

    def entity(self, uri: str) -> SoftwareArtifact | None:
        """
        Fetch any entity by its full URI.

        The returned object is the most specific Pydantic v2 model available.

        Parameters
        ----------
        uri:
            Full URI, e.g. ``"https://cataforge.dev/instance/F-001"``.

        Returns
        -------
        SoftwareArtifact or None
        """
        ...

    def search(
        self,
        text: str,
        *,
        types: Sequence[str] | None = None,
        filters: dict[str, Any] | None = None,
        limit: int = 20,
    ) -> list[SearchResult]:
        """
        Full-text search across entity titles and descriptions.

        Implemented as a SPARQL ``FILTER(CONTAINS(LCASE(?title), LCASE(?text)))``
        scan; for large graphs consider a dedicated text-index extension.

        Parameters
        ----------
        text:
            Search string (case-insensitive substring match).
        types:
            Restrict to these LinkML class names, e.g. ``["Feature", "Task"]``.
        filters:
            Additional slot-value constraints, e.g. ``{"status": "approved"}``.
        limit:
            Maximum number of results.

        Returns
        -------
        list[SearchResult]
            Results ordered by relevance score (title-match first, then
            description-match), then by ``sort_key``.
        """
        ...

    # ------------------------------------------------------------------
    # plan_load — token-budget-aware load ordering
    # ------------------------------------------------------------------

    def plan_load(
        self,
        uris: Sequence[str],
        token_budget: int,
        *,
        include_related: bool = True,
    ) -> LoadPlan:
        """
        Produce a topologically ordered load plan for a set of entity URIs
        within a token budget.

        Used by agents that need to populate a context window with the
        minimum set of triples required to reason about a feature or task.

        Algorithm
        ---------
        1. Fetch requested URIs and their 1-hop related entities (when
           ``include_related=True``).
        2. Build a DAG from ``cf:depends_on`` / ``cf:part_of`` edges.
        3. Topological-sort the DAG; break ties with ``sort_key``.
        4. Greedily include entities until the estimated token count reaches
           ``token_budget``; remainder goes to ``LoadPlan.dropped_uris``.

        Parameters
        ----------
        uris:
            URIs of the seed entities to load.
        token_budget:
            Rough upper bound on context tokens.  Estimation uses a
            fixed ratio of 1 triple ≈ 12 tokens.
        include_related:
            If ``True``, also include direct neighbours via structural
            predicates (``depends_on``, ``part_of``, ``realizes``).

        Returns
        -------
        LoadPlan
            Ordered list of URIs to load, estimated token cost, and
            any URIs that did not fit.
        """
        ...

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fetch_typed(self, class_name: str, entity_id: str, model_cls: type) -> Any | None:
        sparql = f"""
        PREFIX cf: <{CF}>
        PREFIX cfprj: <{CFPRJ}>
        DESCRIBE ?s WHERE {{
            ?s a cf:{class_name} ; cf:entity_id "{entity_id}" .
        }}
        """
        results = list(self._store.query(sparql))
        if not results:
            return None
        return model_cls(**self._triples_to_dict(results))

    def _triples_to_dict(self, triples: list) -> dict[str, Any]:
        # Convert SPARQL DESCRIBE result triples to a Pydantic-compatible dict
        ...
```

---

### TraceAPI — traceability chain queries

```python
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Literal

import pyoxigraph as ox

from cataforge.kg._config import KGConfig
from cataforge.kg._models_core import (
    Feature, Module, Component, Task, TestCase, Release, SoftwareArtifact,
)


@dataclass
class TraceChain:
    """
    Full traceability chain rooted at a requirement.

    Attributes
    ----------
    root:
        The starting entity of the chain.
    requirements:
        Requirement-layer ancestors or self (Feature / Epic / UserStory).
    acceptance_criteria:
        AcceptanceCriteria directly attached to root or its children.
    modules:
        Module entities in the implementation chain.
    components:
        Component entities in the implementation chain.
    tasks:
        Task entities realizing the above modules/components.
    test_cases:
        TestCase entities that verify root or any entity in the chain.
    releases:
        Release entities delivering root.
    coverage_status:
        ``"full"`` — all features have ≥1 passing TestRun.
        ``"partial"`` — some features have TestCases but no passing run.
        ``"none"`` — no TestCases found.
    chain_breaks:
        List of (from_uri, predicate, to_uri) tuples where the expected
        edge is missing (e.g. a Task that realizes nothing).
    """

    root: SoftwareArtifact
    requirements: list[SoftwareArtifact] = field(default_factory=list)
    acceptance_criteria: list[SoftwareArtifact] = field(default_factory=list)
    modules: list[Module] = field(default_factory=list)
    components: list[Component] = field(default_factory=list)
    tasks: list[Task] = field(default_factory=list)
    test_cases: list[TestCase] = field(default_factory=list)
    releases: list[Release] = field(default_factory=list)
    coverage_status: Literal["full", "partial", "none"] = "none"
    chain_breaks: list[tuple[str, str, str]] = field(default_factory=list)


@dataclass
class CoverageStatus:
    """
    Coverage status for a single requirement URI.

    Attributes
    ----------
    requirement_uri:
        The URI that was checked.
    has_test_cases:
        True if any TestCase has a ``cf:verifies+`` path to this requirement.
    has_passing_run:
        True if at least one TestRun for those TestCases has ``test_result=pass``.
    uncovered_acceptance_criteria:
        AcceptanceCriteria nodes with no inbound ``cf:verifies`` edge.
    status:
        ``"full"`` / ``"partial"`` / ``"none"``.
    """

    requirement_uri: str
    has_test_cases: bool
    has_passing_run: bool
    uncovered_acceptance_criteria: list[str]
    status: Literal["full", "partial", "none"]


class TraceAPI:
    """
    Traceability chain queries.

    All methods are synchronous.  Use :class:`AsyncTraceAPI` (accessible via
    ``kg.atrace``) for ``await``-able versions.
    """

    def __init__(self, store: ox.Store, config: KGConfig) -> None:
        self._store = store
        self._config = config

    def from_requirement(
        self,
        req_id: str,
        *,
        max_depth: int = 5,
        direction: Literal["downstream", "upstream", "both"] = "downstream",
    ) -> TraceChain:
        """
        Build the full traceability chain starting from a requirement entity.

        Traverses the graph via the five direct predicates defined in §3.3:
        ``cf:implemented_by``, ``cf:realizes``, ``cf:verifies``,
        ``cf:delivers``, and ``cf:affects``.

        Parameters
        ----------
        req_id:
            Any Requirement entity_id (e.g. ``"F-001"``, ``"EP-003"``).
        max_depth:
            Maximum number of predicate hops from the root.
        direction:
            ``"downstream"`` — from requirement to implementations, tasks,
            tests, and releases.
            ``"upstream"``   — from requirement to Epics / refinement parents.
            ``"both"``       — full bidirectional walk.

        Returns
        -------
        TraceChain
            Fully populated chain with coverage status and chain-break list.

        Raises
        ------
        KGEntityNotFoundError
            If ``req_id`` does not exist in the graph.
        KGTraceabilityBreakError
            If a required edge is missing and break detection is enabled
            (logged to EVENT-LOG regardless).
        """
        ...

    def coverage(self, requirement_uri: str) -> CoverageStatus:
        """
        Determine the test-coverage status of a single requirement.

        Executes SPARQL template Q1 scoped to the given URI.

        Parameters
        ----------
        requirement_uri:
            Full URI of the requirement, e.g.
            ``"https://cataforge.dev/instance/F-001"``.

        Returns
        -------
        CoverageStatus
        """
        ...

    def impact(
        self,
        entity_id: str,
        *,
        max_depth: int = 5,
    ) -> list[SoftwareArtifact]:
        """
        Return the transitive impact set for a ChangeRequest or component.

        Executes SPARQL template Q4 (``cf:affects+`` closure) for
        ChangeRequest entities, or Q2 (reverse upstream closure) for
        architecture entities.

        Parameters
        ----------
        entity_id:
            Entity ID of the root change or component.
        max_depth:
            Maximum hop depth for the transitive closure.

        Returns
        -------
        list[SoftwareArtifact]
            All artifacts in the impact set, ordered by sort_key.
        """
        ...


class AsyncTraceAPI:
    """
    Async wrapper around :class:`TraceAPI`.

    All methods delegate to the underlying sync API via
    ``asyncio.to_thread`` to avoid blocking the event loop.
    """

    def __init__(self, sync_api: TraceAPI) -> None:
        self._sync = sync_api

    async def from_requirement(
        self,
        req_id: str,
        *,
        max_depth: int = 5,
        direction: Literal["downstream", "upstream", "both"] = "downstream",
    ) -> TraceChain:
        """Async version of :meth:`TraceAPI.from_requirement`."""
        return await asyncio.to_thread(
            self._sync.from_requirement,
            req_id,
            max_depth=max_depth,
            direction=direction,
        )

    async def coverage(self, requirement_uri: str) -> CoverageStatus:
        """Async version of :meth:`TraceAPI.coverage`."""
        return await asyncio.to_thread(self._sync.coverage, requirement_uri)

    async def impact(self, entity_id: str, *, max_depth: int = 5) -> list[SoftwareArtifact]:
        """Async version of :meth:`TraceAPI.impact`."""
        return await asyncio.to_thread(self._sync.impact, entity_id, max_depth=max_depth)
```

---

### TransactionContext — transactional write API

```python
from __future__ import annotations

import asyncio
from typing import Any, Sequence

import pyoxigraph as ox

from cataforge.kg._config import KGConfig
from cataforge.kg._models_core import SoftwareArtifact
from cataforge.kg._exceptions import KGNodeConflictError, KGGraphInconsistencyError


class TransactionContext:
    """
    Write-side context produced by ``async with kg.transaction() as txn:``.

    All write methods buffer triples into a local staging graph; ``_commit``
    validates via SHACL and merges into the main store atomically.  On any
    exception, ``_rollback`` discards the staging graph without touching the
    live store.

    Optimistic locking
    ------------------
    When a caller supplies ``content_hash`` on ``update``, the context checks
    the current hash against the stored value before applying the write.  On
    mismatch, :class:`KGNodeConflictError` is raised.  The caller (or the
    ``KnowledgeGraph.transaction`` context manager) may retry up to
    ``KGConfig.max_transaction_retries`` times.
    """

    def __init__(self, store: ox.Store, config: KGConfig) -> None:
        self._store = store
        self._config = config
        self._staging: list[ox.Quad] = []
        self._deletes: list[ox.Quad] = []

    async def add(
        self,
        entity: SoftwareArtifact,
        *,
        on_conflict: str = "error",
    ) -> None:
        """
        Stage a new entity for insertion.

        Parameters
        ----------
        entity:
            A Pydantic v2 model instance (any concrete ``SoftwareArtifact``
            subclass).
        on_conflict:
            ``"error"``     — raise :class:`KGNodeConflictError` if the URI
                              already exists (default).
            ``"overwrite"`` — replace all triples for the URI.
            ``"skip"``      — silently ignore if URI already exists.

        Raises
        ------
        KGNodeConflictError
            If the entity URI already exists and ``on_conflict="error"``.
        """
        quads = await asyncio.to_thread(self._entity_to_quads, entity)
        self._staging.extend(quads)

    async def update(
        self,
        entity_id: str,
        *,
        content_hash: str | None = None,
        **slot_values: Any,
    ) -> None:
        """
        Stage a partial update to an existing entity.

        Parameters
        ----------
        entity_id:
            Frontmatter ID of the entity to update (e.g. ``"F-001"``).
        content_hash:
            If provided, the current stored hash must match this value;
            otherwise :class:`KGNodeConflictError` is raised (optimistic lock).
        **slot_values:
            Keyword arguments mapping LinkML slot names to new values.

        Raises
        ------
        KGNodeConflictError
            If ``content_hash`` is given and does not match stored value.
        KGEntityNotFoundError
            If ``entity_id`` is not found in the store.
        """
        ...

    async def delete(
        self,
        entity_id: str,
        *,
        cascade: bool = False,
    ) -> None:
        """
        Stage deletion of an entity.

        Parameters
        ----------
        entity_id:
            Frontmatter ID to delete.
        cascade:
            If ``True``, also stage removal of all inbound edges that
            reference this entity.

        Raises
        ------
        KGEntityNotFoundError
            If the entity is not found.
        """
        ...

    async def bulk_insert(
        self,
        entities: Sequence[SoftwareArtifact],
        *,
        batch_size: int = 500,
    ) -> None:
        """
        Stage multiple entities for insertion, chunked into ``batch_size``
        batches to bound memory usage.

        Parameters
        ----------
        entities:
            Iterable of Pydantic v2 model instances.
        batch_size:
            Number of entities converted to triples per batch.
        """
        for entity in entities:
            await self.add(entity)

    # ------------------------------------------------------------------
    # Internal commit / rollback
    # ------------------------------------------------------------------

    async def _commit(self) -> None:
        """
        Validate staging graph with SHACL, then merge into the live store.

        Called automatically by ``KnowledgeGraph.transaction()``; do not
        call directly.

        Raises
        ------
        KGGraphInconsistencyError
            If SHACL validation of the merged graph fails.
        """
        await asyncio.to_thread(self._apply_deletes)
        await asyncio.to_thread(self._apply_inserts)
        violations = await asyncio.to_thread(self._run_shacl)
        if violations:
            await self._rollback()
            raise KGGraphInconsistencyError(violations)

    async def _rollback(self) -> None:
        """Discard all staged changes without touching the live store."""
        self._staging.clear()
        self._deletes.clear()

    def _entity_to_quads(self, entity: SoftwareArtifact) -> list[ox.Quad]:
        ...

    def _apply_inserts(self) -> None:
        for quad in self._staging:
            self._store.add(quad)

    def _apply_deletes(self) -> None:
        for quad in self._deletes:
            self._store.remove(quad)

    def _run_shacl(self) -> list[str]:
        # Returns list of violation messages; empty list means valid.
        ...
```

---

## §5.3 Typical Use Cases

### CLI use cases

**Use case C-1: PM checks requirement coverage before a release**

```bash
# Step 1: trace the full downstream chain with coverage column
cataforge kg trace F-001 --direction downstream --coverage --output table

# Step 2: validate that all features have SHACL-compliant TestCase edges
cataforge kg validate --severity violation

# Step 3: run Q1 template to list all uncovered features
cataforge kg query queries/traceability.sparql --limit 200
```

Expected: Table shows F-001 with coverage=full, no violations in step 2, Q1 returns empty set.

---

**Use case C-2: Architect assesses the impact of changing Component C-014**

```bash
# Upstream reverse closure: which requirements are affected?
cataforge kg trace --from-component C-014 --direction upstream --output mermaid > impact.mmd

# Then inspect the mermaid diagram in the browser
```

Expected: Mermaid graph shows the requirement chain back to Epics; architect can share the diagram.

---

**Use case C-3: Tech lead promotes `mentions` refs to `strict` form before merging a PR**

```bash
# Preview what would change
cataforge kg reconcile --upgrade --dry-run

# Apply and write a report
cataforge kg reconcile --upgrade --report .cataforge/reconcile-report.json

# Verify no unresolved refs remain
cataforge kg reconcile --coverage-mode strict --fail-on-unresolved
```

Expected: All `mentions`-style cross-refs are rewritten to `doc_id#§N.ITEM`; exit 0.

---

### Python API use cases

**Use case A-1 (traceability): PM queries whether REQ-001 is fully covered**

```python
import asyncio
from cataforge.kg import KnowledgeGraph, KGConfig

config = KGConfig(db_path=".cataforge/kg/store")

async def check_coverage() -> None:
    async with KnowledgeGraph.aconnect(config) as kg:
        trace = await kg.atrace.from_requirement("F-001")
        print(f"实现模块: {[m.entity_id for m in trace.modules]}")
        print(f"开发任务: {[t.entity_id for t in trace.tasks]}")
        print(f"测试用例: {[tc.entity_id for tc in trace.test_cases]}")
        print(f"覆盖状态: {trace.coverage_status}")
        if trace.chain_breaks:
            print(f"链断点: {trace.chain_breaks}")

asyncio.run(check_coverage())
```

---

**Use case A-2: QA engineer adds a new TestCase and links it to a feature**

```python
import asyncio
from cataforge.kg import KnowledgeGraph, KGConfig
from cataforge.kg._models_core import TestCase

config = KGConfig(db_path=".cataforge/kg/store")

async def add_test_case() -> None:
    async with KnowledgeGraph.aconnect(config) as kg:
        tc = TestCase(
            id="https://cataforge.dev/instance/TC-099",
            entity_id="TC-099",
            sort_key="TC:000099",
            title="Offline sync smoke test",
            verifies=["https://cataforge.dev/instance/F-042"],
            belongs_to_project="https://cataforge.dev/instance/proj-demo",
        )
        async with kg.transaction() as txn:
            await txn.add(tc)
        print("TC-099 committed.")

asyncio.run(add_test_case())
```

---

**Use case A-3: Agent uses plan_load to fit context within a token budget**

```python
from cataforge.kg import KnowledgeGraph, KGConfig

config = KGConfig(db_path=".cataforge/kg/store")

with KnowledgeGraph.connect(config) as kg:
    # Agent wants F-001, M-014, T-021 and their 1-hop neighbours
    plan = kg.query.plan_load(
        uris=[
            "https://cataforge.dev/instance/F-001",
            "https://cataforge.dev/instance/M-014",
            "https://cataforge.dev/instance/T-021",
        ],
        token_budget=4096,
        include_related=True,
    )
    print(f"Loading {len(plan.ordered_uris)} entities "
          f"(~{plan.estimated_tokens} tokens)")
    if plan.dropped_uris:
        print(f"Budget exceeded; dropped: {plan.dropped_uris}")

    for uri in plan.ordered_uris:
        entity = kg.query.entity(uri)
        # feed entity into agent context ...
```

---

**Use case A-4: Bulk import from Markdown parse results (transactional)**

```python
import asyncio
from cataforge.kg import KnowledgeGraph, KGConfig
from cataforge.kg._models_core import Feature, Module

config = KGConfig(db_path=".cataforge/kg/store")

async def bulk_import(features: list[Feature], modules: list[Module]) -> None:
    async with KnowledgeGraph.aconnect(config) as kg:
        async with kg.transaction() as txn:
            await txn.bulk_insert(features)
            await txn.bulk_insert(modules)
        print("Bulk import committed.")

asyncio.run(bulk_import(parsed_features, parsed_modules))
```

---

## §5.4 Error-Handling Strategy

### Exception hierarchy

```python
from __future__ import annotations


class KGError(Exception):
    """Base class for all CataForge KG exceptions."""


class KGStoreNotInitializedError(KGError):
    """
    Raised when the Oxigraph store path does not exist.

    Trigger:
        ``KnowledgeGraph.connect()`` or ``aconnect()`` called before
        ``cataforge kg init``.

    User recoverability:
        Run ``cataforge kg init`` to create the store, then retry.

    Auto-retry:
        No — this is a configuration error, not a transient failure.

    EVENT-LOG:
        Not logged; printed to stderr as a user-facing diagnostic.
    """


class KGGraphInconsistencyError(KGError):
    """
    Raised when SHACL validation fails after a transaction commit.

    Trigger:
        A write produces a graph state that violates one or more SHACL shapes
        defined in ``core.shacl.ttl`` or ``extra.shacl.ttl``.

    Attributes
    ----------
    violations:
        List of human-readable SHACL violation messages.

    User recoverability:
        Inspect ``violations`` to identify which entity and which shape
        failed.  Fix the entity data and retry the transaction.

    Auto-retry:
        No — the violation must be resolved at the data level first.

    EVENT-LOG:
        Logged at ERROR level with full SHACL report payload.
    """

    def __init__(self, violations: list[str]) -> None:
        self.violations = violations
        super().__init__(
            f"SHACL validation failed ({len(violations)} violation(s)): "
            + "; ".join(violations[:3])
        )


class KGNodeConflictError(KGError):
    """
    Raised on an optimistic-lock miss during a transactional write.

    Trigger:
        Caller supplied ``content_hash`` on ``txn.update()`` and the stored
        hash has since changed (concurrent write from another process).

    Attributes
    ----------
    entity_id:
        The entity that caused the conflict.
    expected_hash:
        The hash the caller expected.
    actual_hash:
        The hash currently stored in the graph.

    User recoverability:
        Re-fetch the entity, incorporate the latest changes, and retry.

    Auto-retry:
        Yes — ``KnowledgeGraph.transaction()`` retries up to
        ``KGConfig.max_transaction_retries`` (default 3) times with
        exponential backoff (0.1 s, 0.2 s, 0.4 s).

    EVENT-LOG:
        Logged at WARNING level on each retry; ERROR level if all retries
        exhausted.
    """

    def __init__(
        self, entity_id: str, expected_hash: str, actual_hash: str
    ) -> None:
        self.entity_id = entity_id
        self.expected_hash = expected_hash
        self.actual_hash = actual_hash
        super().__init__(
            f"Optimistic lock conflict on {entity_id!r}: "
            f"expected hash {expected_hash!r}, found {actual_hash!r}"
        )


class KGQueryTimeoutError(KGError):
    """
    Raised when a SPARQL query exceeds ``KGConfig.query_timeout``.

    Trigger:
        pyoxigraph query execution wall-clock time exceeds the configured
        timeout.

    Attributes
    ----------
    query_snippet:
        First 200 characters of the query that timed out.
    timeout_seconds:
        The configured timeout value.

    User recoverability:
        Increase ``KGConfig.query_timeout``, add a ``LIMIT`` clause to the
        query, or pre-filter with more specific ``BIND`` constraints.

    Auto-retry:
        No — timeouts indicate a structural query issue, not transience.

    EVENT-LOG:
        Logged at WARNING level with query snippet and timeout value.
    """

    def __init__(self, query_snippet: str, timeout_seconds: float) -> None:
        self.query_snippet = query_snippet
        self.timeout_seconds = timeout_seconds
        super().__init__(
            f"SPARQL query timed out after {timeout_seconds}s. "
            f"Query: {query_snippet[:200]!r}"
        )


class KGTraceabilityBreakError(KGError):
    """
    Raised (or recorded) when a traceability chain traversal detects a
    missing required edge.

    Trigger:
        ``kg.trace.from_requirement()`` encounters a Task with no
        ``cf:realizes`` edge, or a TestCase with no ``cf:verifies`` edge.
        Also emitted by ``cataforge kg validate`` when the SHACL advisory
        shape fires.

    Attributes
    ----------
    from_uri:
        Subject of the missing edge.
    predicate:
        Expected predicate that is absent.
    context:
        Human-readable description of the traversal context.

    User recoverability:
        Add the missing traceability edge in the source Markdown and
        re-import, or use ``cataforge kg update`` to add the edge directly.

    Auto-retry:
        No — the graph data must be corrected.

    EVENT-LOG:
        Logged at ERROR level; included in ``TraceChain.chain_breaks``.
    """

    def __init__(self, from_uri: str, predicate: str, context: str = "") -> None:
        self.from_uri = from_uri
        self.predicate = predicate
        self.context = context
        super().__init__(
            f"Traceability break: {from_uri!r} is missing edge {predicate!r}. {context}"
        )


class KGEntityNotFoundError(KGError):
    """
    Raised when a requested entity_id or URI is not present in the graph.

    Trigger:
        Any ``kg.query.*`` or ``kg.trace.*`` method that receives an unknown
        identifier.

    User recoverability:
        Verify the entity_id pattern (e.g. ``F-NNN``), check that import has
        been run, or use ``cataforge kg query`` to inspect the graph.

    Auto-retry:
        No.

    EVENT-LOG:
        Not logged; returned as a user-facing exception message.
    """
```

### Retry decorator (for KGNodeConflictError)

```python
import asyncio
import functools
from typing import Callable, TypeVar

F = TypeVar("F", bound=Callable)


def retry_on_conflict(max_retries: int = 3, base_delay: float = 0.1) -> Callable[[F], F]:
    """
    Decorator that retries an async function on :class:`KGNodeConflictError`.

    Applied automatically by ``KnowledgeGraph.transaction()`` when
    ``max_transaction_retries > 0``.  Callers that manage their own retry
    logic can also apply this decorator directly.

    Parameters
    ----------
    max_retries:
        Maximum number of retry attempts (not counting the first attempt).
    base_delay:
        Initial backoff delay in seconds; doubles on each retry.
    """
    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            delay = base_delay
            for attempt in range(max_retries + 1):
                try:
                    return await fn(*args, **kwargs)
                except KGNodeConflictError:
                    if attempt == max_retries:
                        raise
                    await asyncio.sleep(delay)
                    delay *= 2
        return wrapper  # type: ignore[return-value]
    return decorator
```

---

## §5.5 Backward-Compatibility Shim Layer

### Scope

The shim layer provides drop-in replacements for the five business-doc call points identified in Task 1 §1.3. Framework-asset call points (skill loading, agent registry, rule evaluation, EVENT-LOG lifting) do **not** require shims because they operate on `.cataforge/` filesystem assets that are not mediated by the 0.4.x KG API.

The shim module is located at `src/cataforge/kg/_shim.py` and is imported by `src/cataforge/docs/_compat.py` for backward compatibility.

### Deprecation policy

All shim functions emit a `DeprecationWarning` at call time. They will be removed in CataForge 0.6.0. Callers should migrate to the `KnowledgeGraph` API in §5.2.

### Shim implementations

```python
"""
cataforge/kg/_shim.py

Backward-compatible shims for 0.4.x business-doc call points.
All five functions are thin wrappers that open a transient synchronous
KnowledgeGraph connection, run the equivalent query, and return results
in the 0.4.x dict/list format.

FRAMEWORK-ASSET call points (skill loading, agent registry, rule
evaluation) do NOT have shims — they access .cataforge/ filesystem
assets directly and are unaffected by the KG migration.
"""
from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any

from cataforge.kg._kg import KnowledgeGraph
from cataforge.kg._config import KGConfig

_DEFAULT_CONFIG = KGConfig()


def _get_config(db_path: str | Path | None = None) -> KGConfig:
    if db_path is None:
        return _DEFAULT_CONFIG
    return KGConfig(db_path=Path(db_path))


# ---------------------------------------------------------------------------
# Shim 1 — extract
# ---------------------------------------------------------------------------

def extract(
    doc_type: str,
    section_id: str,
    *,
    db_path: str | Path | None = None,
) -> dict[str, Any] | None:
    """
    0.4.x shim: extract a single entity by doc_type and section anchor.

    Replaces the old ``cataforge.docs.extract(doc_type, section_id)`` call
    that read from ``.doc-index.json``.

    Parameters
    ----------
    doc_type:
        Source document type (e.g. ``"prd"``, ``"arch"``, ``"dev-plan"``).
        Used to narrow the SPARQL query to entities sourced from that doc type.
    section_id:
        Section anchor (e.g. ``"§2.F-001"``).  Matches ``cf:source_section``
        in the KG.

    Returns
    -------
    dict or None
        Entity fields as a flat dict (0.4.x format), or ``None`` if not found.

    .. deprecated:: 0.5.0
        Use ``kg.query.entity(uri)`` or ``kg.query.feature(feature_id)`` instead.
    """
    warnings.warn(
        "extract() is deprecated since 0.5.0; use kg.query.entity() or "
        "kg.query.<type>() instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    config = _get_config(db_path)
    with KnowledgeGraph.connect(config) as kg:
        sparql = f"""
        PREFIX cf: <https://cataforge.dev/ontology/>
        SELECT ?uri ?entity_id ?title ?status
        WHERE {{
            ?uri cf:source_section "{section_id}" .
            OPTIONAL {{ ?uri cf:entity_id ?entity_id }}
            OPTIONAL {{ ?uri cf:title ?title }}
            OPTIONAL {{ ?uri cf:status ?status }}
        }}
        LIMIT 1
        """
        results = list(kg._store.query(sparql))
        if not results:
            return None
        row = results[0]
        return {
            "uri": str(row[0]),
            "entity_id": str(row[1]) if row[1] else None,
            "title": str(row[2]) if row[2] else None,
            "status": str(row[3]) if row[3] else None,
            "doc_type": doc_type,
            "source_section": section_id,
        }


# ---------------------------------------------------------------------------
# Shim 2 — extract_batch
# ---------------------------------------------------------------------------

def extract_batch(
    specs: list[dict[str, str]],
    *,
    db_path: str | Path | None = None,
) -> list[dict[str, Any] | None]:
    """
    0.4.x shim: batch-extract multiple entities by spec list.

    Replaces the old ``cataforge.docs.extract_batch(specs)`` call.

    Parameters
    ----------
    specs:
        List of dicts, each with keys ``"doc_type"`` and ``"section_id"``.
        Example: ``[{"doc_type": "prd", "section_id": "§2.F-001"}, ...]``.

    Returns
    -------
    list
        One result per input spec, in the same order.  Each element is a
        dict or ``None`` (not found).

    .. deprecated:: 0.5.0
        Use ``kg.query.plan_load()`` for bulk retrieval with token budgeting.
    """
    warnings.warn(
        "extract_batch() is deprecated since 0.5.0; use kg.query.plan_load() instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    config = _get_config(db_path)
    with KnowledgeGraph.connect(config) as kg:
        results = []
        for spec in specs:
            result = extract(
                spec["doc_type"],
                spec["section_id"],
                db_path=config.db_path,
            )
            results.append(result)
        return results


# ---------------------------------------------------------------------------
# Shim 3 — plan_load
# ---------------------------------------------------------------------------

def plan_load(
    items: list[str],
    budget: int,
    *,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """
    0.4.x shim: produce a load plan for a list of entity_id strings.

    Replaces the old ``cataforge.docs.plan_load(items, budget)`` call that
    operated on the ``.doc-index.json`` dependency graph.

    Parameters
    ----------
    items:
        List of entity_id strings (e.g. ``["F-001", "M-014", "T-021"]``).
    budget:
        Approximate token budget.

    Returns
    -------
    dict
        Keys: ``"ordered"`` (list of entity_id strings), ``"dropped"``
        (entity_ids that did not fit), ``"estimated_tokens"`` (int).

    .. deprecated:: 0.5.0
        Use ``kg.query.plan_load(uris, token_budget)`` instead.
    """
    warnings.warn(
        "plan_load() is deprecated since 0.5.0; use kg.query.plan_load() instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    config = _get_config(db_path)
    with KnowledgeGraph.connect(config) as kg:
        CF_NS = "https://cataforge.dev/instance/"
        uris = [f"{CF_NS}{eid}" for eid in items]
        load_plan = kg.query.plan_load(uris, budget)
        # Strip namespace prefix back to bare entity_id for 0.4.x callers
        def _strip(uri: str) -> str:
            return uri.replace(CF_NS, "")
        return {
            "ordered": [_strip(u) for u in load_plan.ordered_uris],
            "dropped": [_strip(u) for u in load_plan.dropped_uris],
            "estimated_tokens": load_plan.estimated_tokens,
        }


# ---------------------------------------------------------------------------
# Shim 4 — build_full_index
# ---------------------------------------------------------------------------

def build_full_index(
    project_uri: str | None = None,
    *,
    db_path: str | Path | None = None,
) -> dict[str, dict[str, Any]]:
    """
    0.4.x shim: build a full entity index dict keyed by entity_id.

    Replaces the old ``cataforge.docs.build_full_index()`` call that
    scanned ``.doc-index.json`` to build an in-memory dict for downstream
    skills.  Now implemented as a SPARQL SELECT across all SoftwareArtifact
    instances (Q6-style deterministic sort).

    Parameters
    ----------
    project_uri:
        Optional project URI to scope the query.  If ``None``, returns
        all entities in the store.
    db_path:
        Override the default KG store path.

    Returns
    -------
    dict
        ``{entity_id: {title, status, sort_key, source_doc, source_section, ...}}``
        in sort_key order.

    .. deprecated:: 0.5.0
        Use ``kg.query.search("", limit=None)`` or direct SPARQL via
        ``kg.query`` for targeted queries.
    """
    warnings.warn(
        "build_full_index() is deprecated since 0.5.0; use kg.query.search() "
        "or direct SPARQL instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    config = _get_config(db_path)
    with KnowledgeGraph.connect(config) as kg:
        project_filter = (
            f'?artifact cf:belongs_to_project <{project_uri}> .'
            if project_uri else ""
        )
        sparql = f"""
        PREFIX cf:   <https://cataforge.dev/ontology/>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT ?artifact ?entity_id ?title ?status ?sort_key ?source_doc ?source_section
        WHERE {{
            ?artifact a/rdfs:subClassOf* cf:SoftwareArtifact ;
                      cf:entity_id ?entity_id ;
                      cf:sort_key  ?sort_key ;
                      cf:title     ?title .
            {project_filter}
            OPTIONAL {{ ?artifact cf:status       ?status }}
            OPTIONAL {{ ?artifact cf:source_doc   ?source_doc }}
            OPTIONAL {{ ?artifact cf:source_section ?source_section }}
        }}
        ORDER BY ASC(?sort_key)
        """
        index: dict[str, dict[str, Any]] = {}
        for row in kg._store.query(sparql):
            eid = str(row[1])
            index[eid] = {
                "uri": str(row[0]),
                "entity_id": eid,
                "title": str(row[2]),
                "status": str(row[3]) if row[3] else None,
                "sort_key": str(row[4]),
                "source_doc": str(row[5]) if row[5] else None,
                "source_section": str(row[6]) if row[6] else None,
            }
        return index


# ---------------------------------------------------------------------------
# Shim 5 — resolve_deps
# ---------------------------------------------------------------------------

def resolve_deps(
    item_id: str,
    *,
    db_path: str | Path | None = None,
) -> list[str]:
    """
    0.4.x shim: return the list of entity_ids that ``item_id`` depends on.

    Replaces the old ``cataforge.docs.resolve_deps(item_id)`` call that
    walked the ``.doc-index.json`` dependency graph.  Now implemented as a
    SPARQL query over ``cf:depends_on`` edges.

    Parameters
    ----------
    item_id:
        Frontmatter ID of the entity (e.g. ``"T-021"``).

    Returns
    -------
    list[str]
        Ordered list of entity_id strings for all direct dependencies.
        Transitive closure is NOT returned by default (unlike the KG API's
        ``plan_load`` which includes 1-hop neighbours).

    .. deprecated:: 0.5.0
        Use ``kg.query.plan_load([uri], budget)`` for dependency-aware
        loading, or SPARQL ``cf:depends_on+`` for transitive closure.
    """
    warnings.warn(
        "resolve_deps() is deprecated since 0.5.0; use kg.query.plan_load() "
        "for dependency-aware loading.",
        DeprecationWarning,
        stacklevel=2,
    )
    config = _get_config(db_path)
    with KnowledgeGraph.connect(config) as kg:
        CF_NS = "https://cataforge.dev/instance/"
        subject_uri = f"{CF_NS}{item_id}"
        sparql = f"""
        PREFIX cf: <https://cataforge.dev/ontology/>
        SELECT ?dep_id
        WHERE {{
            <{subject_uri}> cf:depends_on ?dep .
            ?dep cf:entity_id ?dep_id .
        }}
        ORDER BY ?dep_id
        """
        return [str(row[0]) for row in kg._store.query(sparql)]
```

---

## [依赖传递摘要]

**关键决策**:

- `KGConfig` 确立两后端 (`oxigraph` / `memory`)，不引入 remote-sparql；`coverage_mode` 默认 `strict`，`mentions` 为 opt-in；`governance` 默认 `false`。Task 6（Markdown 导出）、Task 7（上线策略）的配置层都必须以 `KGConfig` 为单一配置源。
- 所有写操作强制走 `async with kg.transaction() as txn:`，由 `asyncio.Lock` 串行化；读操作允许并发（同步直读 + `asyncio.to_thread` 异步读）。任何下游 agent 若绕过 `transaction()` 直写 store，将破坏 SHACL 后验证保证。
- `cataforge kg trace` 提供 `--from-requirement` / `--from-component` / `--from-feature` 三个别名入口点，`TraceChain` 结构体承载完整链 + `chain_breaks` + `coverage_status`；Task 6 的导出管道和 Task 7 的健康检查脚本均可复用 `TraceAPI.from_requirement()` 直接获取完整链，无需重新实现遍历逻辑。
- 异常层级（`KGError` → 5 个子类）与 EVENT-LOG 绑定；`KGNodeConflictError` 触发最多 3 次指数退避重试，其余异常不自动重试。Task 6 / Task 7 实现时应捕获具体子类，不得吞 `KGError` 基类。
- Shim 层仅覆盖 5 个 **业务文档** call point（`extract` / `extract_batch` / `plan_load` / `build_full_index` / `resolve_deps`）；框架资产 call point 不需要 shim，已在文档中明确说明，Task 7 上线脚本无需为其编写兼容适配。
- `cataforge kg reconcile --upgrade` 是 mention→strict 升级的唯一官方入口；Task 7 上线检查单中应将其列为 Beta 前置步骤。

**输出物路径/位置**: `docs/proposals/kg-migration-0.5.0/task-5-cli-api.md`

**阻塞标记**: NONE。`[待验证]` 项（`belongs_to_work_unit` SPARQL CONSTRUCT 推断规则 / `sh:closed true` per-class lockdown / 自然语言查询 LLM 配置接口）为 Task 5 实施时的工程验证项，不阻塞 Task 6 / Task 7 设计。
