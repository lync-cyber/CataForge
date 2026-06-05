"""Typed views over QueryAPI dict records, backed by LinkML-generated models.

The generated module lives under ``_generated/`` (produced by
``scripts/codegen_kg_schema.py`` and checked in). When it cannot be imported —
codegen never run in a bare source tree, or a slimmed install — :func:`to_model`
returns ``None`` so callers fall back to the dict form they already handle.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any, cast

_core: Any
try:
    _core = importlib.import_module("cataforge.domain.kg._generated.core_pydantic")
    _MODELS_AVAILABLE = True
except ImportError:
    _core = None
    _MODELS_AVAILABLE = False

if TYPE_CHECKING:
    from pydantic import BaseModel


def models_available() -> bool:
    """Return True when the generated Pydantic models can be imported."""
    return _MODELS_AVAILABLE


def to_model(record: dict[str, Any] | None) -> BaseModel | None:
    """Build a typed scalar view of a QueryAPI dict record.

    Returns ``None`` when ``record`` is ``None``, the generated models are not
    importable, or ``record["_class"]`` has no matching model — never raises on
    absence, so it is a safe opt-in over the dict path.

    QueryAPI records are scalar projections: they carry the SoftwareArtifact
    scalar slots plus ``uri`` / ``_class`` but omit required relation slots such
    as ``belongs_to_project``. The store is the source of truth (validated at
    ingest), so the record is filtered to the model's own fields and built with
    ``model_construct`` — a typed scalar view (field access + IDE completion),
    not a re-validated entity; relation slots are left unset. ``id`` is the
    LinkML identifier slot, surfaced by QueryAPI as ``uri``.
    """
    if record is None or not _MODELS_AVAILABLE:
        return None
    class_name = record.get("_class")
    model_cls = getattr(_core, class_name, None) if class_name else None
    if model_cls is None:
        return None
    known = set(model_cls.model_fields)
    payload = {k: v for k, v in record.items() if k in known and v is not None}
    if "id" in known and record.get("uri"):
        payload["id"] = record["uri"]
    return cast("BaseModel | None", model_cls.model_construct(**payload))


__all__ = ["models_available", "to_model"]
