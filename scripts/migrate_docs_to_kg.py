#!/usr/bin/env python3
"""Markdown → KG migration codemod (task-7 §7.2 six-phase pipeline).

This script is a thin shell wrapper around `cataforge kg import`; the
real logic lives in `cataforge.kg.ingest`. Use the CLI for normal
operation:

    cataforge kg import --project-root . --doc-type prd --doc-type arch

This script exists so the migration pipeline has a discoverable entry
point matching `task-7 §7.2`'s explicit reference to
`scripts/migrate_docs_to_kg.py`.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from cataforge.utils.common import ensure_utf8  # noqa: E402

ensure_utf8()


def main(argv: list[str] | None = None) -> int:
    from cataforge.cli.main import _register_commands, cli  # noqa: PLC0415

    _register_commands()
    argv = ["kg", "import", *(argv if argv is not None else sys.argv[1:])]
    try:
        cli.main(args=argv, standalone_mode=False)
        return 0
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else 1


if __name__ == "__main__":
    sys.exit(main())
