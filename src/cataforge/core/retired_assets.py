"""Registry of framework skill ids retired from the bundled scaffold.

A project carried across many upgrades can retain a removed skill's source
directory under ``.cataforge/skills/<id>/`` when the manifest-scoped prune in
``copy_scaffold_to`` does not cover it — the files were never manifest-tracked
(project predates the manifest) or were edited and held back as ``protected``.
The stale directory then trips later guards: the doctor deprecated-reference
scan flags its old CLI calls, pointing at the symptom instead of the leftover.

Every id here is a framework skill removed from the scaffold. A
``.cataforge/skills/<id>/`` for one of them is always a stale leftover: the live
implementation is a package builtin (which ships no scaffold dir) or a renamed
skill, and legitimate user/project overrides live under ``.cataforge/overrides/``
— never under the framework-managed ``.cataforge/skills/`` scaffold layer. So
warning on / pruning these directories never touches a valid asset.
"""

from __future__ import annotations

from pathlib import Path

RETIRED_SKILL_IDS: frozenset[str] = frozenset(
    {
        "doc-gen",
        "doc-nav",
        "doc-consistency",
        "doc-review",
        "framework-issue-triage",
        "kg-ask",
        "self-update",
    }
)


def retired_skill_dirs(skills_dir: Path) -> list[Path]:
    """Existing ``<skills_dir>/<id>/`` directories whose id is retired."""
    if not skills_dir.is_dir():
        return []
    return sorted(skills_dir / sid for sid in RETIRED_SKILL_IDS if (skills_dir / sid).is_dir())
