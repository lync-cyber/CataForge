"""Tests for the retired-skill registry and its scaffold guarantees."""

from __future__ import annotations

from pathlib import Path

from cataforge.core.retired_assets import RETIRED_SKILL_IDS, retired_skill_dirs
from cataforge.core.scaffold import iter_scaffold_files


def _bundled_skill_ids() -> set[str]:
    ids: set[str] = set()
    for rel, _ in iter_scaffold_files():
        parts = rel.split("/")
        if len(parts) >= 2 and parts[0] == "skills":
            ids.add(parts[1])
    return ids


def test_registry_disjoint_from_current_scaffold() -> None:
    """A retired id must never name a skill the current scaffold still ships —
    otherwise doctor/upgrade would warn on / prune a live skill."""
    assert RETIRED_SKILL_IDS.isdisjoint(_bundled_skill_ids())


def test_retired_skill_dirs_finds_only_retired(tmp_path: Path) -> None:
    skills = tmp_path / "skills"
    (skills / "doc-gen").mkdir(parents=True)  # retired
    (skills / "context").mkdir()  # live
    (skills / "my-custom").mkdir()  # user skill (not retired)
    found = {p.name for p in retired_skill_dirs(skills)}
    assert found == {"doc-gen"}


def test_retired_skill_dirs_missing_dir_is_empty(tmp_path: Path) -> None:
    assert retired_skill_dirs(tmp_path / "nope") == []
