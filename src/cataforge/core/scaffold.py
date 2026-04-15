"""Copy the bundled ``.cataforge/`` scaffold into a user project.

The scaffold lives under :mod:`cataforge._assets.cataforge_scaffold` and is
shipped inside the wheel so ``pip install cataforge`` / ``uv tool install
cataforge`` give users a one-shot ``cataforge setup`` that can bootstrap a
fresh project from scratch — no git clone required.

Access goes through :func:`importlib.resources.files` so it works whether the
package is installed from a wheel, editable install, or running from source.
"""

from __future__ import annotations

import shutil
from importlib.resources import as_file, files
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Iterator

_PKG = "cataforge._assets"
_SCAFFOLD_SUBDIR = "cataforge_scaffold"


def _scaffold_root() -> Traversable:
    return files(_PKG).joinpath(_SCAFFOLD_SUBDIR)


def iter_scaffold_files() -> Iterator[tuple[str, Traversable]]:
    """Yield ``(relative_posix_path, traversable)`` for every bundled file."""

    def walk(node: Traversable, prefix: str) -> Iterator[tuple[str, Traversable]]:
        for child in node.iterdir():
            rel = f"{prefix}{child.name}"
            if child.is_dir():
                yield from walk(child, rel + "/")
            else:
                yield rel, child

    yield from walk(_scaffold_root(), "")


def copy_scaffold_to(
    dest: Path,
    *,
    force: bool = False,
) -> tuple[list[Path], list[Path]]:
    """Copy the bundled scaffold into *dest* (typically ``<project>/.cataforge``).

    Returns ``(written, skipped)`` — lists of destination paths that were
    newly written vs. preserved because they already existed. When *force*
    is ``True`` existing files are overwritten.
    """
    written: list[Path] = []
    skipped: list[Path] = []
    for rel, src in iter_scaffold_files():
        target = dest / rel
        if target.exists() and not force:
            skipped.append(target)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with as_file(src) as src_path:
            shutil.copyfile(src_path, target)
        written.append(target)
    return written, skipped
