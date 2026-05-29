"""Golden-file regression tests for the KG export pipeline.

Compares `compile_to_markdown()` output against pinned reference files
under `tests/golden/kg/`. Any byte-level divergence from the golden
baseline signals an unintended rendering change.

Set env var ``UPDATE_GOLDEN=1`` to regenerate the baselines after an
intentional template or pipeline change.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "kg-vertical-slice"
GOLDEN_ROOT = Path(__file__).resolve().parents[1] / "golden" / "kg"
VARIANTS = ("waterfall", "agile")
_UPDATE = os.environ.get("UPDATE_GOLDEN") == "1"


def _build_store(variant: str):
    from cataforge.kg import KGConfig, init_store
    from cataforge.kg.ingest import run_migration

    config = KGConfig(store_backend="memory")
    handle = init_store(config, force=True)
    run_migration(handle.raw, FIXTURE_ROOT / variant, config)
    return handle


@pytest.mark.parametrize("variant", VARIANTS)
def test_export_matches_golden_hashes(tmp_path: Path, variant: str) -> None:
    from cataforge.kg.export import compile_to_markdown

    handle = _build_store(variant)
    out = tmp_path / "export"
    result = compile_to_markdown(handle.raw, out)
    assert not result.errors, f"export errors: {result.errors}"

    if _UPDATE:
        golden_dir = GOLDEN_ROOT / variant
        golden_dir.mkdir(parents=True, exist_ok=True)
        for rec in result.file_records:
            dest = golden_dir / rec.output_path.relative_to(out)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(rec.output_path.read_bytes())
        manifest = GOLDEN_ROOT / f"{variant}_hashes.json"
        manifest.write_text(
            json.dumps(result.file_hashes, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        pytest.skip("golden files updated")
        return

    manifest_path = GOLDEN_ROOT / f"{variant}_hashes.json"
    assert manifest_path.is_file(), (
        f"missing golden manifest {manifest_path}; "
        f"run with UPDATE_GOLDEN=1 to generate"
    )
    golden_hashes = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert result.file_hashes == golden_hashes, (
        f"{variant}: hash divergence from golden baseline:\n"
        f"  expected: {golden_hashes}\n"
        f"  got:      {result.file_hashes}"
    )


@pytest.mark.parametrize("variant", VARIANTS)
def test_export_content_matches_golden_files(
    tmp_path: Path, variant: str
) -> None:
    from cataforge.kg.export import compile_to_markdown

    if _UPDATE:
        pytest.skip("golden update mode — use hash test")

    handle = _build_store(variant)
    out = tmp_path / "export"
    result = compile_to_markdown(handle.raw, out)
    assert not result.errors

    golden_dir = GOLDEN_ROOT / variant
    assert golden_dir.is_dir(), f"missing golden dir {golden_dir}"

    for rec in result.file_records:
        rel = rec.output_path.relative_to(out)
        golden_file = golden_dir / rel
        assert golden_file.is_file(), f"missing golden file: {golden_file}"
        actual = rec.output_path.read_text(encoding="utf-8")
        expected = golden_file.read_text(encoding="utf-8")
        assert actual == expected, (
            f"{variant}/{rel}: content differs from golden baseline"
        )
