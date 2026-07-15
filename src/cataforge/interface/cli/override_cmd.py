"""cataforge override — manage user/project override layers.

Override layers let a project (``overrides/project/``) or an individual
(``overrides/user/``) customise framework agents / skills without editing the
scaffold, so ``upgrade apply`` never clobbers the changes. Two granularities:

* whole-file — drop a full ``AGENT.md`` / ``SKILL.md`` to replace the base;
* section patch — drop ``<name>.patch.md`` whose ``## `` sections override
  matching base sections and append new ones.

``eject`` writes a correct starting point for either; ``list`` shows which
layers currently define each asset.
"""

from __future__ import annotations

import click

from cataforge.core.layers import OVERRIDE_LAYERS
from cataforge.interface.cli._support.guards import require_initialized
from cataforge.interface.cli._support.helpers import resolve_root
from cataforge.interface.cli.main import cli

_MAIN_FILE = {"agents": "AGENT.md", "skills": "SKILL.md"}
_KINDS = sorted(_MAIN_FILE)


@cli.group("override")
def override_group() -> None:
    """Customise framework agents/skills in upgrade-immune override layers."""


@override_group.command("list")
@require_initialized
def override_list() -> None:
    """Show every agent/skill and which layers define it."""
    from cataforge.core.paths import ProjectPaths
    from cataforge.interface.cli._support.ui import ui

    paths = ProjectPaths(resolve_root())
    for kind in _KINDS:
        layer_roots = {
            "scaffold": paths.cataforge_dir / kind,
            **{layer: paths.override_layer(layer) / kind for layer in OVERRIDE_LAYERS},
        }
        ids = sorted(
            {
                d.name
                for root in layer_roots.values()
                if root.is_dir()
                for d in root.iterdir()
                if d.is_dir()
            }
        )
        ui.section(kind)
        if not ids:
            ui.print("  (none)")
            continue
        for asset_id in ids:
            marks = [name for name, root in layer_roots.items() if (root / asset_id).is_dir()]
            ui.print(f"  {asset_id:<28} {' + '.join(marks)}")


@override_group.command("eject")
@click.argument("kind", type=click.Choice(_KINDS))
@click.argument("asset_id")
@click.option(
    "--layer",
    type=click.Choice(list(OVERRIDE_LAYERS)),
    default="project",
    help="Override layer to write into (default: project).",
)
@click.option(
    "--patch",
    is_flag=True,
    help="Write a section-patch stub instead of a whole-file copy.",
)
@click.option(
    "--section",
    "section",
    default=None,
    help="With --patch: seed the stub with this section's current body.",
)
@click.option("--force", is_flag=True, help="Overwrite an existing override file.")
@require_initialized
def override_eject(
    kind: str,
    asset_id: str,
    layer: str,
    patch: bool,
    section: str | None,
    force: bool,
) -> None:
    """Seed an override for KIND/ASSET_ID from the shipped scaffold."""
    from cataforge.core.paths import ProjectPaths
    from cataforge.interface.cli._support.ui import ui

    paths = ProjectPaths(resolve_root())
    main = _MAIN_FILE[kind]
    base_file = paths.cataforge_dir / kind / asset_id / main
    if not base_file.is_file():
        raise click.UsageError(
            f"no scaffold {kind[:-1]} {asset_id!r} at {base_file.relative_to(paths.root)}"
        )

    dest_dir = paths.override_layer(layer) / kind / asset_id
    out_name = main.replace(".md", ".patch.md") if patch else main
    dest = dest_dir / out_name
    if dest.exists() and not force:
        raise click.UsageError(f"{dest.relative_to(paths.root)} exists; pass --force to overwrite")

    base_text = base_file.read_text()
    content = _patch_stub(base_text, section) if patch else base_text

    dest_dir.mkdir(parents=True, exist_ok=True)
    dest.write_text(content)
    ui.ok(f"ejected → {dest.relative_to(paths.root)}")
    ui.info("edit it, then `cataforge deploy` to apply.")


def _patch_stub(base_text: str, section: str | None) -> str:
    """Build a ``*.patch.md`` body — a real section to override, or a template."""
    from cataforge.core.section_patch import section_bodies

    sections = section_bodies(base_text)
    if section is not None:
        if section not in sections:
            raise click.UsageError(
                f"section {section!r} not found; available: {', '.join(sections) or '(none)'}"
            )
        return f"## {section}\n{sections[section]}"
    titles = ", ".join(list(sections)[:4]) or "<section title>"
    return (
        "<!-- Section patch: a '## Title' matching a base section overrides it; "
        "a new title is appended. -->\n\n"
        f"## {next(iter(sections), '<section title>')}\n"
        f"- replace this body to override the base section (base titles: {titles})\n\n"
        "## My New Section\n"
        "- add custom guidance here\n"
    )
