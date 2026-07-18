"""Real-pipeline ↔ real-shapes conformance.

`tests/kg/test_shacl_bridge.py` proves the pyoxigraph→rdflib→pyshacl plumbing
with synthetic inline shapes; this module closes the gap that plumbing tests
cannot: the *committed* generated shapes must accept what the *actual* ingest
pipeline writes. Any schema edit or pipeline change that de-syncs the two
(missing declared slot, dangling contains_entity edge, unfilled required slot)
fails here instead of surfacing as downstream validate noise.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "kg-vertical-slice"
SHAPES = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "cataforge"
    / "domain"
    / "kg"
    / "_generated"
    / "core_shapes.ttl"
)

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("pyshacl") is None or importlib.util.find_spec("rdflib") is None,
    reason="pyshacl/rdflib not installed (shacl extra)",
)


def _ingested_store(variant: str):
    from cataforge.domain.kg import KGConfig, init_store
    from cataforge.domain.kg.ingest import run_migration

    config = KGConfig(store_backend="memory")
    handle = init_store(config, force=True)
    run_migration(handle.raw, FIXTURE_ROOT / variant, config)
    return handle, config


def test_generated_shapes_are_committed() -> None:
    # The shapes ship in the wheel; a gitignore regression would silently
    # revert every SHACL surface to "skipped".
    assert SHAPES.is_file(), (
        "core_shapes.ttl missing from _generated/ — run scripts/codegen_kg_schema.py"
    )


@pytest.mark.parametrize("variant", ("waterfall", "agile"))
def test_ingest_pipeline_output_conforms_to_generated_shapes(variant: str) -> None:
    from cataforge.domain.kg.validate import _run_shacl

    handle, _config = _ingested_store(variant)
    skip_reason, violations = _run_shacl(handle.raw)
    assert skip_reason is None, f"SHACL unexpectedly skipped: {skip_reason}"
    blocking = [v for v in violations if v.severity == "violation"]
    assert not blocking, "pipeline ↔ schema drift:\n" + "\n".join(
        f"  {v.entity_id} {v.shape}: {v.message}" for v in blocking
    )


@pytest.mark.parametrize("variant", ("waterfall", "agile"))
def test_section_contains_entity_edges_resolve_to_typed_nodes(variant: str) -> None:
    # Subordinate entities (AcceptanceCriteria) live on parent-scoped IRIs; a
    # flat-IRI contains_entity edge dangles and vanishes from every
    # `?e cf:entity_id ?eid` join.
    handle, config = _ingested_store(variant)
    ns = config.ontology_namespace.rstrip("/") + "/"
    dangling = list(
        handle.raw.query(
            f"PREFIX cf: <{ns}> SELECT ?e WHERE {{ "
            "?s a cf:Section ; cf:contains_entity ?e . "
            "FILTER NOT EXISTS { ?e a ?cls } }"
        )
    )
    assert not dangling, (
        f"dangling contains_entity targets: {[str(r['e'].value) for r in dangling]}"
    )


@pytest.mark.parametrize("variant", ("waterfall", "agile"))
def test_acceptance_criteria_carry_required_acceptance_text(variant: str) -> None:
    handle, config = _ingested_store(variant)
    ns = config.ontology_namespace.rstrip("/") + "/"
    rows = list(
        handle.raw.query(
            f"PREFIX cf: <{ns}> SELECT ?id ?text WHERE {{ "
            "?ac a cf:AcceptanceCriteria ; cf:entity_id ?id . "
            "OPTIONAL { ?ac cf:acceptance_text ?text } }"
        )
    )
    assert rows, "fixture must contain AcceptanceCriteria entities"
    missing = [str(r["id"].value) for r in rows if r["text"] is None]
    assert not missing, f"ACs without acceptance_text: {missing}"
