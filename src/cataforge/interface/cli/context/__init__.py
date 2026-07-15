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

from cataforge.interface.cli.main import cli


@cli.group("context")
def context_group() -> None:
    """Mode-routed context I/O — the single document/context entry point.

    Read & index: ``read`` (section load), ``index`` (build .doc-index.json),
    ``validate`` (read-only index integrity gate). Authoring lifecycle:
    ``write`` / ``write-narrative`` / ``transact`` / ``finalize`` / ``ingest``
    / ``reconcile``. The ``docs`` group's ``load`` / ``index`` / ``validate``
    are deprecated aliases of ``read`` / ``index`` / ``validate``.
    """


from . import index, lifecycle, query, write  # noqa: E402,F401
