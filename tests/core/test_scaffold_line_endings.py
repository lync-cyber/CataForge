"""The bundled scaffold must ship with LF line endings, and runtime KG state
must never be classified as scaffold.

The wheel force-includes repo-root ``.cataforge/`` verbatim from the working
tree. On a Windows checkout with ``core.autocrlf=true`` and no ``.gitattributes``
the tree is CRLF, so the wheel ships CRLF while downstream projects hold LF.
The scaffold drift detector compares raw bytes, so every byte-identical-but-for
line-endings file reads as ``drift`` on ``cataforge upgrade apply`` — a wall of
false positives that can bury real drift.

Three guards:

* a cross-platform static guard that the repo pins LF via ``.gitattributes``;
* an invariant guard that the shipped scaffold source carries no CR byte;
* a guard that the per-project KG RocksDB store is excluded from the scaffold.
"""

from __future__ import annotations

from importlib.resources import as_file
from pathlib import Path

import pytest

import cataforge
from cataforge.core.scaffold import iter_scaffold_files


def _repo_root() -> Path | None:
    """Repo root when tests run from a source checkout, else ``None``.

    ``.gitattributes`` is a repo-root file, not packaged into the wheel, so the
    static guard only applies when running against the source tree (the
    ``pythonpath=["src"]`` test layout this project uses).
    """
    root = Path(cataforge.__file__).resolve().parents[2]
    return root if (root / "pyproject.toml").is_file() else None


def test_repo_pins_lf_via_gitattributes() -> None:
    """The repo ships a ``.gitattributes`` forcing LF so any clone — Windows
    included — checks out (and packs into the wheel) LF scaffold bytes."""
    root = _repo_root()
    if root is None:
        pytest.skip("not a source checkout — .gitattributes is not packaged")
    ga = root / ".gitattributes"
    assert ga.is_file(), ".gitattributes missing — Windows checkouts ship CRLF scaffold"
    body = ga.read_text(encoding="utf-8")
    assert "text=auto" in body and "eol=lf" in body, (
        ".gitattributes must normalize text to LF (`* text=auto eol=lf`)"
    )


def test_bundled_scaffold_source_uses_lf() -> None:
    """No text file the scaffold ships may contain a CR byte."""
    offenders: list[str] = []
    for rel, src in iter_scaffold_files():
        with as_file(src) as src_path:
            data = Path(src_path).read_bytes()
        if b"\x00" in data:  # binary — line-ending rules don't apply
            continue
        if b"\r" in data:
            offenders.append(rel)
    assert not offenders, (
        "scaffold source ships CRLF (expected LF) — a CRLF wheel makes every "
        "downstream `upgrade apply` report false drift:\n  " + "\n  ".join(sorted(offenders))
    )


def test_scaffold_excludes_kg_runtime_store() -> None:
    """The per-project KG RocksDB store is runtime state, never scaffold.

    Packing it into the wheel (a dirty build that walked a live ``.cataforge/kg/``)
    makes ``upgrade apply`` report the store's CURRENT/LOG/*.sst files as
    new/drift in every downstream project.
    """
    rels = [rel for rel, _ in iter_scaffold_files()]
    kg_rels = [rel for rel in rels if rel == "kg" or rel.startswith("kg/")]
    assert not kg_rels, "KG runtime store leaked into the scaffold:\n  " + "\n  ".join(kg_rels)
