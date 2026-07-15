"""``cataforge feedback`` — package downstream signals into an upstream-ready bundle.

Command families (one module each):
- bundles: bug, suggest, correction-export (three assemblers sharing the sink flags)
- labels:  ensure-labels

Each bundle subcommand renders a single markdown body and emits it via one of
four mutually-exclusive sinks (``--print`` is the default):

    --print           write to stdout (pipe-friendly)
    --out PATH        write to a file (relative resolves under project root)
    --clip            push to the system clipboard via pbcopy / wl-copy / xclip / clip
    --gh              shell out to `gh issue create` (requires gh on PATH +
                      authenticated; passes the body via stdin so no temp file
                      is left on disk)

Privacy: paths are redacted to ``<project>`` / ``~`` by default. Pass
``--include-paths`` only when filing internally.

Exit codes follow the project convention (see ``cli/_support/errors.py``):
* 0 — body produced successfully
* 1 — assembler / sink failed (missing gh, write failed, etc.)
* 2 — Click usage error
"""

from __future__ import annotations

from cataforge.interface.cli.feedback._group import feedback_group as feedback_group

from . import bundles, labels  # noqa: E402,F401
