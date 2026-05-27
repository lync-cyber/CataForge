"""Atomic text-file write helper.

Several CLI commands rewrite small, hand-edited config files
(``framework.json``, ``CORRECTIONS-LOG.md``, deploy-state caches, …)
with a plain ``path.write_text(...)``. That call is non-atomic — if the
process dies between truncate and write the file is left zero-length or
half-written, and the next run cannot parse it.

The accepted pattern in the repo (see ``core/event_log.append_batch``)
is *write to a sibling temp file then* ``os.replace`` *into place*: on
POSIX this is atomic within a filesystem, on Windows it is atomic when
source and dest sit on the same volume (which they do, since the temp
file is created in ``path.parent``).

This module centralises that pattern so call sites can express intent
in one line instead of replicating the ``tempfile.mkstemp`` + try /
cleanup boilerplate every time.
"""

from __future__ import annotations

import contextlib
import os
import tempfile
from pathlib import Path

__all__ = ["atomic_write_text"]


def atomic_write_text(
    path: Path,
    data: str,
    *,
    encoding: str = "utf-8",
    newline: str = "\n",
) -> None:
    """Write *data* to *path* atomically.

    The text is materialised in a sibling temp file in ``path.parent``
    and then renamed via ``os.replace`` — readers always observe either
    the prior content or the full new content, never a half-written
    state. The temp file is removed if the write fails for any reason.

    *path.parent* is created if missing, matching the surface of
    ``Path.write_text`` so callers can swap in this helper without
    reordering surrounding ``mkdir`` calls.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline=newline) as f:
            f.write(data)
        os.replace(tmp_name, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
        raise
