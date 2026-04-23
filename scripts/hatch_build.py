"""Hatch build hook — refresh the bundled scaffold before packaging.

Runs :mod:`scripts.sync_scaffold` so that every sdist / wheel ships with the
``src/cataforge/_assets/cataforge_scaffold/`` mirror matching the canonical
``.cataforge/`` source tree.  Without this hook, local editors could ship
stale scaffolds if CI was bypassed.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class SyncScaffoldBuildHook(BuildHookInterface):
    PLUGIN_NAME = "sync-scaffold"

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        script = Path(self.root) / "scripts" / "sync_scaffold.py"
        if not script.is_file():
            return
        result = subprocess.run(
            [sys.executable, str(script)],
            cwd=self.root,
            capture_output=True,
            text=True,
        )
        sys.stdout.write(result.stdout)
        sys.stderr.write(result.stderr)
        if result.returncode != 0:
            raise RuntimeError(
                f"sync_scaffold failed (exit {result.returncode}) — aborting build"
            )

        # Register scaffold files explicitly so hatchling picks them up even
        # when they are not yet recorded in the VCS index (e.g. wheel built
        # from sdist where git metadata is absent).
        scaffold = Path(self.root) / "src" / "cataforge" / "_assets" / "cataforge_scaffold"
        if scaffold.is_dir():
            for path in sorted(scaffold.rglob("*")):
                if path.is_file():
                    build_data["artifacts"].append(
                        str(path.relative_to(self.root))
                    )
