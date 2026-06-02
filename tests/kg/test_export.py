"""Export pipeline tests on the waterfall + agile fixtures.

Sub-PR 4 exit condition pieces verified here:

* **byte-identical idempotency** — two consecutive `compile_to_markdown`
  calls over an unchanged store produce the same SHA-256 for every file.
* **entity coverage** — every business entity in the KG ends up with
  exactly one `.md` file under the right `doc_type/` subdir.
* **relation presence** — every traceability edge in the KG is rendered
  as a relative Markdown link in the source file.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "kg-vertical-slice"
VARIANTS = ("waterfall", "agile")

EXPECTED_ENTITIES = {
    "F-001": "prd",
    "F-002": "prd",
    "AC-001": "prd",
    "AC-002": "prd",
    "M-001": "arch",
    "M-002": "arch",
    "TS-001": "arch",
    "TC-001": "test-report",
    "TC-002": "test-report",
}

EXPECTED_RELATIONS = {
    ("M-001", "F-001"),
    ("M-002", "F-002"),
    ("TC-001", "AC-001"),
    ("TC-002", "AC-002"),
}


def _open_memory_store():
    from cataforge.domain.kg import KGConfig, init_store

    config = KGConfig(store_backend="memory")
    return init_store(config, force=True), config


def _ingest_fixture(variant: str):
    from cataforge.domain.kg.ingest import run_migration

    handle, config = _open_memory_store()
    run_migration(handle.raw, FIXTURE_ROOT / variant, config)
    return handle, config


def _sha256_dir(directory: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for path in sorted(directory.rglob("*.md")):
        out[str(path.relative_to(directory)).replace("\\", "/")] = hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
    return out


@pytest.mark.parametrize("variant", VARIANTS)
def test_export_renders_every_entity(tmp_path: Path, variant: str) -> None:
    from cataforge.domain.kg.export import compile_to_markdown

    handle, _ = _ingest_fixture(variant)
    result = compile_to_markdown(handle.raw, tmp_path / "out")

    assert not result.errors, f"{variant}: export reported errors: {result.errors}"
    rendered_ids = {r.entity_id for r in result.file_records}
    assert rendered_ids == set(EXPECTED_ENTITIES), (
        f"{variant}: rendered {rendered_ids}, expected {set(EXPECTED_ENTITIES)}"
    )
    for entity_id, doc_type in EXPECTED_ENTITIES.items():
        f = tmp_path / "out" / doc_type / f"{entity_id}.md"
        assert f.is_file(), f"{variant}: missing {f}"


@pytest.mark.parametrize("variant", VARIANTS)
def test_export_is_byte_identical_across_runs(tmp_path: Path, variant: str) -> None:
    from cataforge.domain.kg.export import compile_to_markdown

    handle, _ = _ingest_fixture(variant)
    out1 = tmp_path / "run1"
    out2 = tmp_path / "run2"

    r1 = compile_to_markdown(handle.raw, out1)
    r2 = compile_to_markdown(handle.raw, out2)
    assert not r1.errors and not r2.errors

    hashes1 = _sha256_dir(out1)
    hashes2 = _sha256_dir(out2)
    assert hashes1.keys() == hashes2.keys(), (
        f"{variant}: file sets differ between runs: {hashes1.keys() ^ hashes2.keys()}"
    )
    for rel in hashes1:
        assert hashes1[rel] == hashes2[rel], (
            f"{variant}: SHA-256 mismatch for {rel}: {hashes1[rel]} != {hashes2[rel]}"
        )

    # CompileResult.file_hashes must match the on-disk hashes.
    assert r1.file_hashes == hashes1
    assert r2.file_hashes == hashes2


@pytest.mark.parametrize("variant", VARIANTS)
def test_export_in_place_overwrite_is_idempotent(tmp_path: Path, variant: str) -> None:
    """Two exports into the SAME directory must leave bytes unchanged.

    Guards against any rendering path that depends on whether the output
    file already existed (mtime injection, append modes, etc.).
    """
    from cataforge.domain.kg.export import compile_to_markdown

    handle, _ = _ingest_fixture(variant)
    out = tmp_path / "in-place"

    compile_to_markdown(handle.raw, out)
    first = _sha256_dir(out)
    compile_to_markdown(handle.raw, out)
    second = _sha256_dir(out)

    assert first == second, (
        f"{variant}: in-place re-export produced different bytes: "
        f"{set(first.items()) ^ set(second.items())}"
    )


@pytest.mark.parametrize("variant", VARIANTS)
def test_export_renders_every_relation_as_link(tmp_path: Path, variant: str) -> None:
    """Each (subject, object) traceability pair must appear as a relative link."""
    from cataforge.domain.kg.export import compile_to_markdown

    handle, _ = _ingest_fixture(variant)
    out = tmp_path / "out"
    compile_to_markdown(handle.raw, out)

    for subject, target in EXPECTED_RELATIONS:
        subject_doc = EXPECTED_ENTITIES[subject]
        subject_file = out / subject_doc / f"{subject}.md"
        body = subject_file.read_text(encoding="utf-8")
        # The template emits `[<target>](<relative>/<target>.md)` for
        # every outbound traceability edge.
        assert f"]({target}.md" in body or f"/{target}.md" in body, (
            f"{variant}: {subject}.md is missing a link to {target}\nbody=\n{body}"
        )


@pytest.mark.parametrize("variant", VARIANTS)
def test_export_strict_undefined_blocks_generated_at(tmp_path: Path, variant: str) -> None:
    """`StrictUndefined` is the safety net against accidental timestamps."""
    from cataforge.domain.kg.export import compile_to_markdown

    handle, _ = _ingest_fixture(variant)
    out = tmp_path / "out"
    compile_to_markdown(handle.raw, out)

    for md in out.rglob("*.md"):
        text = md.read_text(encoding="utf-8")
        # generated_at / exported_at would break idempotency. Absence
        # is enforced indirectly by StrictUndefined (a template author
        # adding `{{ generated_at }}` would crash this test).
        assert "generated_at" not in text, f"{md} contains generated_at"
        assert "exported_at" not in text, f"{md} contains exported_at"
