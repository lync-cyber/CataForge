"""Exception hierarchy for the KG layer."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence


class KGError(Exception):
    """Base class for every KG-layer exception."""


class KGStoreNotInitializedError(KGError):
    """Raised when a caller asks for a store at a path that does not exist.

    `cataforge kg init` is the only constructor; opening a non-existent
    store path (without `init`) is treated as user error rather than
    silently materializing a new database.
    """


class KGStoreAlreadyExistsError(KGError):
    """Raised by `kg init` when `db_path` already exists and `--force` is off."""


class KGValidationError(KGError):
    """Raised when an entity write fails post-validation (orphan/xref/SHACL)."""


class KGEntityNotFoundError(KGError):
    """Raised when update/delete targets an entity_id absent from the store."""


class KGEntityCollisionError(KGError):
    """Raised when one entity_id is defined across documents with diverging
    content, which the flat `cfprj:<entity_id>` IRI scheme would collapse into
    a single node with silent data loss."""


class KGDocumentCollisionError(KGError):
    """Raised when multiple scanned files resolve to one logical document id.

    One doc_id owns one Document IRI; letting two files claim it would
    collapse their Document nodes (last write wins) and per-file rewrites
    would delete each other's Sections. ``collisions`` carries the structured
    `DocIdCollision` list for report-building consumers (reconcile)."""

    def __init__(self, message: str, collisions: Sequence[Any] | None = None) -> None:
        super().__init__(message)
        self.collisions: list[Any] = list(collisions or [])
