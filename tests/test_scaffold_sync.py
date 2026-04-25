"""Guard: ``.cataforge/`` (dogfood) and ``src/cataforge/_assets/cataforge_scaffold/``
(shipped to new projects via ``cataforge setup``) must stay byte-identical
except for the explicit dogfood-only carve-outs.

Background — pre-#67 the two trees were maintained by hand and drift
produced two failure modes simultaneously:
  - dogfood (``.cataforge/``) gets a fix but the ship copy stays broken,
    so ``cataforge setup`` regenerates the same bug for users; or
  - the ship copy is updated but dogfood lags, masking the bug while
    iterating on it locally.

Both modes were latent in dep-analysis SKILL.md and the three Penpot
SKILL.md files until this test was added. Treat any new diff as a
deliberate change: either fix both copies, or extend ``EXPECTED_ONLY_IN_SOURCE``.
"""

from __future__ import annotations

import filecmp
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIR = REPO_ROOT / ".cataforge"
SHIPPED_DIR = REPO_ROOT / "src" / "cataforge" / "_assets" / "cataforge_scaffold"


# Paths that may exist in ``.cataforge/`` but must NOT ship in the scaffold
# (dogfood-only tooling). Relative to ``.cataforge/``.
EXPECTED_ONLY_IN_SOURCE: frozenset[str] = frozenset({
    "scripts/dogfood",
})

# Paths that may exist in the scaffold but not in dogfood. Currently empty —
# the scaffold should be a strict subset of the dogfood tree.
EXPECTED_ONLY_IN_SHIPPED: frozenset[str] = frozenset()


def _is_under(rel: str, prefixes: frozenset[str]) -> bool:
    rel_p = Path(rel).as_posix()
    return any(rel_p == p or rel_p.startswith(p + "/") for p in prefixes)


def _walk_diff(source: Path, shipped: Path) -> tuple[list[str], list[str], list[str]]:
    """Return (only_in_source, only_in_shipped, mismatched) — all paths
    relative to *source*.
    """
    only_in_source: list[str] = []
    only_in_shipped: list[str] = []
    mismatched: list[str] = []

    def recurse(rel: Path) -> None:
        cmp = filecmp.dircmp(source / rel, shipped / rel)
        for name in cmp.left_only:
            only_in_source.append((rel / name).as_posix())
        for name in cmp.right_only:
            only_in_shipped.append((rel / name).as_posix())
        for name in cmp.diff_files:
            mismatched.append((rel / name).as_posix())
        for sub in cmp.common_dirs:
            recurse(rel / sub)

    recurse(Path())
    return only_in_source, only_in_shipped, mismatched


@pytest.mark.skipif(
    not (SOURCE_DIR.is_dir() and SHIPPED_DIR.is_dir()),
    reason="run from a checkout that has both .cataforge/ and the scaffold",
)
def test_scaffold_mirrors_dogfood_tree() -> None:
    only_src, only_ship, mismatched = _walk_diff(SOURCE_DIR, SHIPPED_DIR)

    unexpected_src = [p for p in only_src if not _is_under(p, EXPECTED_ONLY_IN_SOURCE)]
    unexpected_ship = [p for p in only_ship if not _is_under(p, EXPECTED_ONLY_IN_SHIPPED)]

    msg_parts: list[str] = []
    if unexpected_src:
        msg_parts.append(
            "Files exist in .cataforge/ but not in the shipped scaffold "
            "(`cataforge setup` will not deliver them):\n  - "
            + "\n  - ".join(sorted(unexpected_src))
        )
    if unexpected_ship:
        msg_parts.append(
            "Files exist in the shipped scaffold but not in .cataforge/ "
            "(dogfood will not exercise them):\n  - "
            + "\n  - ".join(sorted(unexpected_ship))
        )
    if mismatched:
        msg_parts.append(
            "Files diverge between .cataforge/ and the shipped scaffold "
            "(fix both copies, or this is a regression):\n  - "
            + "\n  - ".join(sorted(mismatched))
        )

    assert not msg_parts, "\n\n".join(msg_parts)
