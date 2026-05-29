"""Shared CLI test helpers.

``doctor`` now treats the source-asset directories under ``.cataforge/``
(``agents``, ``skills``, ``rules``, ``hooks``, ``platforms`` and
``hooks.yaml``) as *required* — missing them is a setup failure that
contributes to the exit code. Tests that build a ``.cataforge/`` from
scratch must therefore populate those directories, or doctor will fail
their setup for an unrelated reason.

This helper exists so each test file's local ``_minimal_project`` /
``_project`` factory can opt into the canonical-minimum layout without
each duplicating the same six-line boilerplate.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import click


def invoke_under_group(command: click.Command, args: list[str] | None = None, **kwargs):
    """Invoke ``command`` mounted under a ``CataforgeGroup``.

    Framework errors render via the CLI adapter group, not the error class
    itself; invoking a bare command/subgroup in isolation skips that
    rendering. Mounting under :class:`~cataforge.cli.errors.CataforgeGroup`
    reproduces the production path so a raised ``CataforgeError`` becomes the
    expected ``Error: <msg>`` output + ``exit_code``.
    """
    from click.testing import CliRunner

    from cataforge.cli.errors import CataforgeGroup

    root = CataforgeGroup("root")
    root.add_command(command)
    return CliRunner().invoke(root, [command.name, *(args or [])], **kwargs)


def populate_required_source_assets(cataforge_dir: Path) -> None:
    """Create the empty directories + hooks.yaml that ``doctor`` requires.

    Idempotent. Tests can call this on top of an already-populated
    ``.cataforge/`` to satisfy the strict source-asset gate without
    interfering with whatever else the test set up.
    """
    for name in ("agents", "skills", "rules", "hooks", "platforms"):
        (cataforge_dir / name).mkdir(parents=True, exist_ok=True)
    hooks_yaml = cataforge_dir / "hooks" / "hooks.yaml"
    if not hooks_yaml.is_file():
        hooks_yaml.write_text("version: 1\n", encoding="utf-8")
