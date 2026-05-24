"""``allow-kg-migration`` escape hatch in check_no_design_residue.py.

Design §9.3 R-09 anticipates that the KG cutover PR will touch many
agent / skill files at once. To keep the design-residue guard from
flapping on legitimate migration justifications, we accept a narrow
sibling marker (``<!-- allow-kg-migration: ... -->``) that:

* whitelists the offending line just like ``allow-design-residue`` does
* remains greppable separately so the post-cutover sweep can remove
  every migration-justification line in one pass
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GUARD_PATH = REPO_ROOT / "scripts" / "checks" / "check_no_design_residue.py"


def _load_guard():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("check_residue", GUARD_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_kg_migration_marker_whitelists_a_forbidden_line() -> None:
    guard = _load_guard()
    line = "Bridges to issue #126 <!-- allow-kg-migration: KG cutover -->"
    assert guard.is_whitelisted(line) is True


def test_design_residue_marker_still_works() -> None:
    guard = _load_guard()
    line = "see PR #999 <!-- allow-design-residue: legacy reference -->"
    assert guard.is_whitelisted(line) is True


def test_unannotated_residue_still_blocked() -> None:
    guard = _load_guard()
    line = "Bridges to issue #126"
    assert guard.is_whitelisted(line) is False
