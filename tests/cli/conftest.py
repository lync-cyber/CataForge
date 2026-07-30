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

import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import click


def invoke_under_group(command: click.Command, args: list[str] | None = None, **kwargs):
    """Invoke ``command`` mounted under a ``CataforgeGroup``.

    Framework errors render via the CLI adapter group, not the error class
    itself; invoking a bare command/subgroup in isolation skips that
    rendering. Mounting under :class:`~cataforge.interface.cli._support.errors.CataforgeGroup`
    reproduces the production path so a raised ``CataforgeError`` becomes the
    expected ``Error: <msg>`` output + ``exit_code``.
    """
    from click.testing import CliRunner

    from cataforge.interface.cli._support.errors import CataforgeGroup

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
        hooks_yaml.write_text("schema_version: 2\nhooks: {}\n", encoding="utf-8")


def make_minimal_project(tmp_path: Path, *, framework_json: dict | None = None) -> Path:
    """Create a doctor-clean ``.cataforge/`` skeleton at *tmp_path*; return *tmp_path*.

    ``framework.json`` defaults to the minimal valid ``version`` /
    ``runtime_api_version`` pair. Pass ``framework_json`` to merge extra keys
    (e.g. ``{"migration_checks": [...]}``) over that base. Required source-asset
    directories are populated so ``doctor`` doesn't fail the project for an
    unrelated setup gap.
    """
    cf = tmp_path / ".cataforge"
    cf.mkdir()
    payload: dict = {"version": "0.1.0", "runtime_api_version": "1.0"}
    if framework_json:
        payload.update(framework_json)
    (cf / "framework.json").write_text(json.dumps(payload), encoding="utf-8")
    populate_required_source_assets(cf)
    return tmp_path


def write_doc(root: Path, rel: str, body: str) -> Path:
    """Write *body* to ``root/rel``, creating parent directories; return the path."""
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p
