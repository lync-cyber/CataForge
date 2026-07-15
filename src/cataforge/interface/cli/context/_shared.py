"""Shared helpers for the ``cataforge context`` command families."""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING

import click

from cataforge.core.errors import KGStoreError

if TYPE_CHECKING:
    from collections.abc import Generator


@contextmanager
def _kg_store_guard() -> Generator[None]:
    """Turn a missing-store crash into a clean ``Error:`` with an init hint.

    Under ``graph`` the lifecycle commands open the graph; on a
    project that never ran ``cataforge kg init`` the connect raises
    ``KGStoreNotInitializedError``, which would otherwise escape as an
    uncaught traceback. The ``cataforge kg`` twin commands already convert it
    to :class:`KGStoreError`; mirror that here.
    """
    from cataforge.domain.kg import KGStoreNotInitializedError

    try:
        yield
    except KGStoreNotInitializedError as exc:
        raise KGStoreError(f"{exc}\nHint: run `cataforge kg init` first.") from exc


def _kv(pairs: tuple[str, ...]) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in pairs:
        if "=" not in raw:
            raise click.ClickException(f"--slot expects KEY=VALUE, got: {raw}")
        key, value = raw.split("=", 1)
        out[key.strip()] = value
    return out


def _relations(pairs: tuple[str, ...]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for raw in pairs:
        if "=" not in raw:
            raise click.ClickException(f"--relation expects PREDICATE=OBJECT_ID, got: {raw}")
        predicate, object_id = raw.split("=", 1)
        out.append((predicate.strip(), object_id.strip()))
    return out


def _rooted(ctx: click.Context, project_root: str | None) -> str:
    """Resolve ``--project-root`` to a concrete path, honouring ``--project-dir``.

    Every context command carries its own ``--project-root`` (default ``None``);
    an explicitly-passed value wins, a defaulted one re-roots under the global
    ``--project-dir``, and absent both it falls back to the discovered project
    root. The single return type lets callers drop per-command fallbacks.
    """
    from cataforge.interface.cli._support.helpers import resolve_root, root_relative_default

    resolved = root_relative_default(ctx, "project_root", project_root)
    return str(resolved) if resolved is not None else str(resolve_root())
