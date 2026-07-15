"""Doctor `kg_ingestion_completeness` gate tests.

The gate runs at ERROR severity: missing entities contribute directly to
the doctor exit code.
"""

from __future__ import annotations

import gc
import json
from dataclasses import dataclass
from pathlib import Path

from tests.kg._kg_fixtures import setup_project_with_kg as _setup_project_with_kg


@dataclass
class FakePaths:
    root: Path

    @property
    def framework_json(self) -> Path:
        return self.root / ".cataforge" / "framework.json"


@dataclass
class FakeConfig:
    paths: FakePaths


def test_gate_passes_when_fs_matches_kg(tmp_path, capsys) -> None:
    from cataforge.interface.cli.doctor.kg_ingestion import check_kg_ingestion_completeness

    project_root = _setup_project_with_kg(tmp_path)
    cfg = FakeConfig(paths=FakePaths(root=project_root))

    failures = check_kg_ingestion_completeness(cfg)
    out = capsys.readouterr().out

    assert failures == 0, out
    assert "OK" in out


def test_gate_fails_when_kg_missing_fs_entity(tmp_path, capsys) -> None:
    from cataforge.interface.cli.doctor.kg_ingestion import check_kg_ingestion_completeness

    project_root = _setup_project_with_kg(tmp_path)
    # Append a brand-new entity to the PRD so FS has it but KG does not.
    prd = project_root / "docs" / "prd" / "prd-vertical-slice.md"
    prd.write_text(
        prd.read_text(encoding="utf-8") + "\n\n### §2.3 F-999 New feature\n",
        encoding="utf-8",
    )
    cfg = FakeConfig(paths=FakePaths(root=project_root))

    failures = check_kg_ingestion_completeness(cfg)
    out = capsys.readouterr().out

    assert failures == 1
    assert "FAIL" in out
    assert "F-999" in out


def test_gate_warns_but_does_not_fail_on_stale_only(tmp_path, capsys) -> None:
    """A KG entity present but no longer on disk surfaces as WARN; the
    gate stays green because the active read path still resolves —
    stale entities are cleanup debt, not correctness hazards.
    """
    from cataforge.interface.cli.doctor.kg_ingestion import check_kg_ingestion_completeness

    project_root = _setup_project_with_kg(tmp_path)
    # Remove TC-002 from the test-report so KG has it but FS does not.
    # Use a non-entity-id replacement so FS sees fewer entities, not new ones.
    tc_file = project_root / "docs" / "test-report" / "test-report-vertical-slice.md"
    content = tc_file.read_text(encoding="utf-8")
    new_content = content.replace("TC-002", "REMOVED")
    tc_file.write_text(new_content, encoding="utf-8")

    cfg = FakeConfig(paths=FakePaths(root=project_root))
    failures = check_kg_ingestion_completeness(cfg)
    out = capsys.readouterr().out

    # FS = {F-001, F-002, AC-001, AC-002, M-001, M-002, TC-001}
    # KG = {... + TC-002}
    # missing: ∅ → no FAIL
    # stale:   {TC-002} → WARN, but failures stays 0
    assert failures == 0, out
    assert "TC-002" in out, "stale TC-002 must appear in WARN"
    assert "WARN" in out


def test_gate_warns_not_fails_on_reference_defined_nowhere(tmp_path, capsys) -> None:
    """A bare reference to an entity defined in no active doc_type source
    (e.g. ADR-NNNN whose decision record never lands as a heading) cannot be
    fixed by `kg repair` — it surfaces as WARN with actionable guidance, not
    FAIL. ADR's home doc_type (arch) is active, so the guidance is the
    relation-endpoint/exempt variant, not the moot ``register`` advice."""
    from cataforge.interface.cli.doctor.kg_ingestion import check_kg_ingestion_completeness

    project_root = _setup_project_with_kg(tmp_path)
    prd = project_root / "docs" / "prd" / "prd-vertical-slice.md"
    prd.write_text(
        prd.read_text(encoding="utf-8") + "\n\n依据决策 ADR-0001 采用扁平 IRI 方案。\n",
        encoding="utf-8",
    )
    cfg = FakeConfig(paths=FakePaths(root=project_root))

    failures = check_kg_ingestion_completeness(cfg)
    out = capsys.readouterr().out

    assert failures == 0, out
    assert "FAIL" not in out
    assert "WARN" in out
    assert "ADR-0001" in out
    assert "relation endpoint" in out
    assert "1 ADR- id(s) referenced, none defined in active sources" in out


def test_gate_aggregates_dangling_prefix_with_no_definitions(tmp_path, capsys) -> None:
    """References whose prefix has zero definitions anywhere in active sources
    collapse to a one-line per-prefix summary instead of an id-by-id list."""
    from cataforge.interface.cli.doctor.kg_ingestion import check_kg_ingestion_completeness

    project_root = _setup_project_with_kg(tmp_path)
    prd = project_root / "docs" / "prd" / "prd-vertical-slice.md"
    prd.write_text(
        prd.read_text(encoding="utf-8") + "\n\n覆盖矩阵涉及 UC-101, UC-102, UC-103。\n",
        encoding="utf-8",
    )
    cfg = FakeConfig(paths=FakePaths(root=project_root))

    failures = check_kg_ingestion_completeness(cfg)
    out = capsys.readouterr().out

    assert failures == 0, out
    assert "3 UC- id(s) referenced, none defined in active sources" in out
    assert "['UC-101'" not in out, "wholly-undefined prefixes must not get an id-by-id list"


def test_gate_lists_dangling_ids_when_prefix_has_definitions(tmp_path, capsys) -> None:
    """A stale reference under a prefix that does have definitions stays an
    individually listed id — it is a real fix-me, not doc_type-activation debt."""
    from cataforge.interface.cli.doctor.kg_ingestion import check_kg_ingestion_completeness

    project_root = _setup_project_with_kg(tmp_path)
    tr = project_root / "docs" / "test-report" / "test-report-vertical-slice.md"
    tr.write_text(
        tr.read_text(encoding="utf-8") + "\n\n回归引用 TC-099 见附录。\n",
        encoding="utf-8",
    )
    cfg = FakeConfig(paths=FakePaths(root=project_root))

    failures = check_kg_ingestion_completeness(cfg)
    out = capsys.readouterr().out

    assert failures == 0, out
    assert "TC-099" in out
    assert "TC- id(s) referenced, none defined" not in out


def test_gate_exempts_reference_only_relation_participants(tmp_path, capsys) -> None:
    """A matrix id whose class is defined nowhere active, whose home doc_type is
    active, and which participates in a relation (a coverage rule verifying an
    existing AC) is a graph endpoint, not dangling debt — demoted to an info
    line, never a WARN."""
    from cataforge.interface.cli.doctor.kg_ingestion import check_kg_ingestion_completeness

    project_root = _setup_project_with_kg(tmp_path)
    tr = project_root / "docs" / "test-report" / "test-report-vertical-slice.md"
    tr.write_text(
        tr.read_text(encoding="utf-8") + "\n\n## §3 覆盖规则\n\n- CR-001 覆盖 prd#§2.AC-001\n",
        encoding="utf-8",
    )
    cfg = FakeConfig(paths=FakePaths(root=project_root))

    failures = check_kg_ingestion_completeness(cfg)
    out = capsys.readouterr().out

    assert failures == 0, out
    assert "CR-001" not in out, "reference-only relation participant must not be flagged"
    assert "CR- id(s) referenced, none defined" not in out
    assert "reference-only" in out
    assert "CR×1" in out


def test_gate_warns_on_bare_reference_to_active_home_class(tmp_path, capsys) -> None:
    """A bare prose mention of a definable class (not a relation endpoint) whose
    home doc_type is active is NOT exempted — it stays a WARN, so the
    reference-only demotion never silences a genuine stray/stale reference."""
    from cataforge.interface.cli.doctor.kg_ingestion import check_kg_ingestion_completeness

    project_root = _setup_project_with_kg(tmp_path)
    prd = project_root / "docs" / "prd" / "prd-vertical-slice.md"
    prd.write_text(
        prd.read_text(encoding="utf-8") + "\n\n覆盖矩阵涉及 UC-101, UC-102。\n",
        encoding="utf-8",
    )
    cfg = FakeConfig(paths=FakePaths(root=project_root))

    failures = check_kg_ingestion_completeness(cfg)
    out = capsys.readouterr().out

    assert failures == 0, out
    assert "WARN" in out
    assert "2 UC- id(s) referenced, none defined in active sources" in out
    assert "reference-only" not in out


def test_gate_dangling_with_active_home_gets_relation_or_exempt_guidance(tmp_path, capsys) -> None:
    """A dangling id whose home doc_type is already active but which is defined
    nowhere and is no relation endpoint cannot be fixed by registering the
    doc_type (it is already active). The WARN must point at making it a relation
    endpoint or exempting it, not the moot ``kg_active_doc_types`` advice."""
    from cataforge.interface.cli.doctor.kg_ingestion import check_kg_ingestion_completeness

    project_root = _setup_project_with_kg(tmp_path)
    tr = project_root / "docs" / "test-report" / "test-report-vertical-slice.md"
    tr.write_text(
        tr.read_text(encoding="utf-8") + "\n\n附注：CR-099 覆盖规则待补充。\n",
        encoding="utf-8",
    )
    cfg = FakeConfig(paths=FakePaths(root=project_root))

    failures = check_kg_ingestion_completeness(cfg)
    out = capsys.readouterr().out

    assert failures == 0, out
    assert "WARN" in out
    assert "CR-099" in out
    assert "relation endpoint" in out, "active-home dangling must get relation-endpoint guidance"
    assert "register" not in out, "register-the-doc_type advice is moot when the home is active"


def test_gate_dangling_with_inactive_home_keeps_register_guidance(tmp_path, capsys) -> None:
    """When a dangling id's home doc_type is genuinely inactive, registering it
    in ``kg_active_doc_types`` is the actionable fix — that guidance must stay."""
    from cataforge.domain.kg._config import DEFAULT_KG_ACTIVE_DOC_TYPES
    from cataforge.interface.cli.doctor.kg_ingestion import check_kg_ingestion_completeness

    project_root = _setup_project_with_kg(tmp_path)
    fjson = project_root / ".cataforge" / "framework.json"
    data = json.loads(fjson.read_text(encoding="utf-8"))
    # Drop ui-spec (no ingested entities in this fixture) so a UC reference has
    # a home doc_type that is genuinely inactive.
    data.setdefault("context", {})["kg_active_doc_types"] = [
        d for d in sorted(DEFAULT_KG_ACTIVE_DOC_TYPES) if d != "ui-spec"
    ]
    fjson.write_text(json.dumps(data), encoding="utf-8")
    prd = project_root / "docs" / "prd" / "prd-vertical-slice.md"
    prd.write_text(
        prd.read_text(encoding="utf-8") + "\n\n参见界面用例 UC-101。\n",
        encoding="utf-8",
    )
    cfg = FakeConfig(paths=FakePaths(root=project_root))

    failures = check_kg_ingestion_completeness(cfg)
    out = capsys.readouterr().out

    assert failures == 0, out
    assert "UC-101" in out
    assert "register the defining doc_type in `context.kg_active_doc_types`" in out


def test_gate_still_fails_on_defined_but_uningested_alongside_dangling(tmp_path, capsys) -> None:
    """Dangling references must not mask a genuine ingestion gap: an entity
    defined in FS but absent from KG keeps the gate red."""
    from cataforge.interface.cli.doctor.kg_ingestion import check_kg_ingestion_completeness

    project_root = _setup_project_with_kg(tmp_path)
    prd = project_root / "docs" / "prd" / "prd-vertical-slice.md"
    prd.write_text(
        prd.read_text(encoding="utf-8") + "\n\n### §2.3 F-999 New feature\n\n依据决策 ADR-0001。\n",
        encoding="utf-8",
    )
    cfg = FakeConfig(paths=FakePaths(root=project_root))

    failures = check_kg_ingestion_completeness(cfg)
    out = capsys.readouterr().out

    assert failures == 1, out
    assert "F-999" in out
    assert "kg repair" in out


def test_gate_passes_with_doc_level_frontmatter_id(tmp_path, capsys) -> None:
    """A document-level frontmatter ``id`` (the scaffold's ``id: prd-<x>``
    shape) must not be demanded of the graph.

    The importer mints ``cf:entity_id`` only for item-level entities
    (F-/M-/...), never for document nodes. Treating the doc-level id as a
    required entity made every happy-path KG-active project FAIL with no
    working remediation.
    """
    from cataforge.interface.cli.doctor.kg_ingestion import check_kg_ingestion_completeness

    project_root = _setup_project_with_kg(tmp_path)
    prd = project_root / "docs" / "prd" / "prd-vertical-slice.md"
    body = prd.read_text(encoding="utf-8").split("---", 2)[2]
    prd.write_text(
        "---\nid: prd-vertical-slice\ndoc_type: prd\n---" + body,
        encoding="utf-8",
    )
    cfg = FakeConfig(paths=FakePaths(root=project_root))

    failures = check_kg_ingestion_completeness(cfg)
    out = capsys.readouterr().out

    assert failures == 0, out
    assert "FAIL" not in out
    assert "prd-vertical-slice" not in out


def test_gate_fails_on_diverging_definitions_within_authority(tmp_path, capsys) -> None:
    """Two files of the authoritative doc_type defining the same entity with
    diverging content collapse onto one flat IRI; the gate must FAIL with
    per-occurrence source guidance rather than stay falsely green on the
    set-vs-set comparison the collapsed node satisfies."""
    from cataforge.interface.cli.doctor.kg_ingestion import check_kg_ingestion_completeness

    project_root = _setup_project_with_kg(tmp_path)
    extra = project_root / "docs" / "prd" / "prd-extra.md"
    extra.write_text(
        "---\nid: prd-extra\ndoc_type: prd\n---\n# PRD Extra\n\n## §2 Features\n\n"
        "### §2.9 F-001 另一种登录叙述\n\n与主卷分叉的描述。\n",
        encoding="utf-8",
    )
    cfg = FakeConfig(paths=FakePaths(root=project_root))

    failures = check_kg_ingestion_completeness(cfg)
    out = capsys.readouterr().out

    assert failures == 1, out
    assert "FAIL" in out
    assert "F-001" in out
    assert "prd-extra" in out
    assert "另一种登录叙述" in out, "FAIL output must point at the diverging source section"
    assert "authoritative" in out


def test_gate_treats_non_authoritative_redefinition_as_reference(tmp_path, capsys) -> None:
    """A Feature heading inside arch is not a definition (Feature authority is
    prd), so it neither collides nor fails the gate."""
    from cataforge.interface.cli.doctor.kg_ingestion import check_kg_ingestion_completeness

    project_root = _setup_project_with_kg(tmp_path)
    arch = project_root / "docs" / "arch" / "arch-vertical-slice.md"
    arch.write_text(
        arch.read_text(encoding="utf-8")
        + "\n\n## §9 Arch features\n\n### F-001 架构侧特性\n\n架构侧的不同叙述。\n",
        encoding="utf-8",
    )
    cfg = FakeConfig(paths=FakePaths(root=project_root))

    failures = check_kg_ingestion_completeness(cfg)
    out = capsys.readouterr().out

    assert failures == 0, out
    assert "FAIL" not in out


def test_gate_skips_when_no_store(tmp_path, capsys) -> None:
    """No `.cataforge/kg/store/` present → gate returns 0 (skip).

    Downstream projects that have not opted into KG cutover are not
    blocked by this gate.
    """
    from cataforge.interface.cli.doctor.kg_ingestion import check_kg_ingestion_completeness

    project_root = tmp_path / "proj"
    (project_root / "docs").mkdir(parents=True)
    cfg = FakeConfig(paths=FakePaths(root=project_root))

    failures = check_kg_ingestion_completeness(cfg)
    out = capsys.readouterr().out

    assert failures == 0
    assert "skipping" in out


def test_gate_skips_when_no_active_doc_types(tmp_path, capsys) -> None:
    """Empty `context.kg_active_doc_types` in framework.json AND no
    built-in default for an empty project — skip cleanly.
    """
    from cataforge.interface.cli.doctor.kg_ingestion import check_kg_ingestion_completeness

    project_root = tmp_path / "proj"
    (project_root / ".cataforge" / "kg" / "store").mkdir(parents=True)
    (project_root / "docs").mkdir(parents=True)
    (project_root / ".cataforge" / "framework.json").write_text(
        json.dumps({"context": {"kg_active_doc_types": []}}),
        encoding="utf-8",
    )
    cfg = FakeConfig(paths=FakePaths(root=project_root))

    failures = check_kg_ingestion_completeness(cfg)
    out = capsys.readouterr().out

    assert failures == 0
    assert "skipping" in out


def test_xref_target_gate_passes_on_clean_store(tmp_path, capsys) -> None:
    from cataforge.interface.cli.doctor.kg_ingestion import check_kg_xref_target_integrity

    project_root = _setup_project_with_kg(tmp_path)
    cfg = FakeConfig(paths=FakePaths(root=project_root))

    failures = check_kg_xref_target_integrity(cfg)
    out = capsys.readouterr().out

    assert failures == 0, out
    assert "OK" in out


def test_xref_target_gate_fails_on_orphan_edge(tmp_path, capsys) -> None:
    """An edge whose target entity node was removed (a renamed/deleted entity)
    fails the gate, so doctor-clean implies edge-target integrity even though
    the entity_id-keyed reconcile diff drops the dangling edge."""
    import pyoxigraph as ox

    from cataforge.domain.kg import KGConfig, KnowledgeGraphStore
    from cataforge.domain.kg._quads import _slot_iri
    from cataforge.domain.kg._sparql_utils import cf_namespace
    from cataforge.domain.kg.ingest.iri import entity_iri
    from cataforge.interface.cli.doctor.kg_ingestion import check_kg_xref_target_integrity

    project_root = _setup_project_with_kg(tmp_path)
    config = KGConfig(
        store_backend="oxigraph",
        db_path=project_root / ".cataforge" / "kg" / "store",
        kg_active_doc_types={"prd", "arch", "test"},
    )
    ns = cf_namespace(config)
    with KnowledgeGraphStore.connect(config) as handle:
        handle.raw.add(
            ox.Quad(
                ox.NamedNode(entity_iri("M-001", config.base_namespace)),
                ox.NamedNode(_slot_iri("cf:implements", ns)),
                ox.NamedNode(entity_iri("F-404", config.base_namespace)),
            )
        )
    gc.collect()

    cfg = FakeConfig(paths=FakePaths(root=project_root))
    failures = check_kg_xref_target_integrity(cfg)
    out = capsys.readouterr().out

    assert failures == 1, out
    assert "FAIL" in out
    assert "kg repair" in out
