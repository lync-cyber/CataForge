#!/usr/bin/env python3
"""Anti-rot guard: checked-in KG codegen output stays in sync with the schemas.

`src/cataforge/domain/kg/_generated/core_pydantic.py`, `subclass_axioms.ttl`
and `core_shapes.ttl` are committed so the runtime imports/loads them and the
wheel ships them. Regenerating from `schemas/*.yaml` must produce no diff; a
drift means a schema was edited without rerunning
`python scripts/codegen_kg_schema.py`. Mirrors the `uv lock --check` contract.

The SHACL shapes are byte-stable because codegen canonicalizes them (sorted
N-Triples, `sh:order` stripped, set-semantics lists sorted — see
`_canonicalize_shacl` in scripts/codegen_kg_schema.py).

Skipped gracefully when `linkml` is unavailable (no dev extra) so Python-only
contributor setups still pass; CI installs the dev extra and covers it.
"""

from __future__ import annotations

import filecmp
import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))
from cataforge.utils.encoding import ensure_utf8  # noqa: E402

ensure_utf8()

GENERATED = REPO_ROOT / "src" / "cataforge" / "domain" / "kg" / "_generated"
CODEGEN = REPO_ROOT / "scripts" / "codegen_kg_schema.py"

# Deterministic, checked-in artifacts.
GUARDED = ("core_pydantic.py", "subclass_axioms.ttl", "core_shapes.ttl")


def main() -> int:
    if importlib.util.find_spec("linkml") is None:
        print("  (skipped — linkml not installed; run via dev extra / CI to cover)")
        return 0

    with tempfile.TemporaryDirectory() as td:
        result = subprocess.run(
            [sys.executable, str(CODEGEN), "--out", td],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print("FAIL: codegen errored — cannot verify freshness:", file=sys.stderr)
            print(result.stdout, file=sys.stderr)
            print(result.stderr, file=sys.stderr)
            return 1

        missing: list[str] = []
        stale: list[str] = []
        for name in GUARDED:
            committed = GENERATED / name
            if not committed.is_file():
                missing.append(name)
            elif not filecmp.cmp(Path(td) / name, committed, shallow=False):
                stale.append(name)

    if missing or stale:
        print(
            "FAIL: src/cataforge/domain/kg/_generated/ is out of sync with the LinkML schemas.",
            file=sys.stderr,
        )
        for name in missing:
            print(f"  missing (not checked in): {name}", file=sys.stderr)
        for name in stale:
            print(f"  stale (schema changed?):  {name}", file=sys.stderr)
        print("\nRegenerate and commit:\n  python scripts/codegen_kg_schema.py", file=sys.stderr)
        return 1

    print(f"OK: kg codegen output in sync ({len(GUARDED)} artifacts)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
