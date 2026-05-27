"""Exception hierarchy for the KG layer (subset of task-5 §5.4).

Sub-PR 2 only declares the errors actually raised by `store.py` /
`cataforge kg init`. The remaining error classes from task-5 §5.4 land
alongside the code paths that raise them (validation, traceability,
transaction conflict).
"""
from __future__ import annotations


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


class KGTransactionConflictError(KGError):
    """Raised when a transaction's content_hash conflicts after max retries."""


class KGValidationError(KGError):
    """Raised when an entity write fails post-validation (orphan/xref/SHACL)."""


class KGEntityNotFoundError(KGError):
    """Raised when update/delete targets an entity_id absent from the store."""
