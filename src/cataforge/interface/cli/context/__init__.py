"""``cataforge context`` — the unified context-IO facade.

One command family over the capability ports: read/relation and the
authoring lifecycle (write → write-narrative → finalize → ingest →
reconcile), all routed by ``context.mode``. This is the
backend-routing door the single ``context`` skill targets; callers never
name the graph or the file store.

Command families (one module each):
- query:     read, status
- index:     index, validate
- write:     write, write-narrative, write-doc, write-meta, transact, update, delete
- lifecycle: finalize, ingest, ensure-store, reconcile
"""

from __future__ import annotations

from cataforge.interface.cli.context._group import context_group as context_group

from . import index, lifecycle, query, write  # noqa: E402,F401
