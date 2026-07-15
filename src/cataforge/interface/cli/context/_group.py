"""The ``context`` Click group — subcommands attach in the family modules."""

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
