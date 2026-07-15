"""Export rendering for ui-spec (Page / UIComponent) and dev-plan (Task).

These classes have bespoke templates that surface the traceability edges
the ingest pipeline produces (`satisfies`, `realizes`, `verifies`) — the
generic `_base/artifact.md.j2` renders none of them. The store is built
through the public CRUD path so the test exercises the templates without
touching the shared vertical-slice golden fixture.
"""

from __future__ import annotations

from pathlib import Path

from tests.kg._kg_fixtures import hx


def _make_store_with_ui_devplan():
    from cataforge.domain.kg import KGConfig, KnowledgeGraph, init_store
    from cataforge.domain.kg.ingest.writer import write_project

    config = KGConfig(store_backend="memory")
    handle = init_store(config, force=True)
    project_iri = write_project(handle.raw, "proj-ui", "UI Slice", "waterfall", config)
    kg = KnowledgeGraph(handle.raw, config)

    with kg.transaction() as txn:
        txn.add_entity(
            entity_id="F-001",
            class_name="Feature",
            title="Login",
            source_doc="prd",
            source_section="F-001 Login",
            content_hash=hx("h-f1"),
            project_iri=project_iri,
        )
        txn.add_entity(
            entity_id="AC-001",
            class_name="AcceptanceCriteria",
            title="Valid creds accepted",
            source_doc="prd",
            source_section="AC-001",
            content_hash=hx("h-ac1"),
            project_iri=project_iri,
        )
        txn.add_entity(
            entity_id="M-001",
            class_name="Module",
            title="Auth",
            source_doc="arch",
            source_section="M-001 Auth",
            content_hash=hx("h-m1"),
            project_iri=project_iri,
        )
        txn.add_entity(
            entity_id="P-001",
            class_name="Page",
            title="Login Page",
            source_doc="ui-spec",
            source_section="P-001 Login Page",
            content_hash=hx("h-p1"),
            project_iri=project_iri,
            extra_slots={"ui_route": "/login", "layout_spec": "single-column"},
        )
        txn.add_entity(
            entity_id="UC-001",
            class_name="UIComponent",
            title="Login Form",
            source_doc="ui-spec",
            source_section="UC-001 Login Form",
            content_hash=hx("h-uc1"),
            project_iri=project_iri,
        )
        txn.add_entity(
            entity_id="T-001",
            class_name="Task",
            title="Build auth module",
            source_doc="dev-plan",
            source_section="T-001",
            content_hash=hx("h-t1"),
            project_iri=project_iri,
            extra_slots={"task_status": "in_progress"},
        )
        txn.add_entity(
            entity_id="TC-001",
            class_name="TestCase",
            title="Auth login test",
            source_doc="test-report",
            source_section="TC-001",
            content_hash=hx("h-tc1"),
            project_iri=project_iri,
        )

    with kg.transaction() as txn:
        txn.add_relation("P-001", "cf:satisfies", "F-001")
        txn.add_relation("UC-001", "cf:satisfies", "F-001")
        txn.add_relation("T-001", "cf:realizes", "M-001")
        txn.add_relation("T-001", "cf:satisfies", "AC-001")
        txn.add_relation("TC-001", "cf:verifies", "T-001")

    return kg


def _export(kg, out: Path):
    from cataforge.domain.kg.export import compile_to_markdown

    result = compile_to_markdown(kg.store, out)
    assert not result.errors, f"export errors: {result.errors}"
    return result


def test_page_renders_route_layout_and_satisfies(tmp_path: Path) -> None:
    kg = _make_store_with_ui_devplan()
    out = tmp_path / "out"
    _export(kg, out)

    page = (out / "ui-spec" / "P-001.md").read_text(encoding="utf-8")
    assert "## Route" in page
    assert "/login" in page
    assert "## Layout" in page
    assert "single-column" in page
    assert "## Satisfies" in page
    assert "[F-001](../prd/F-001.md)" in page
    assert "Login" in page


def test_uicomponent_renders_satisfies(tmp_path: Path) -> None:
    kg = _make_store_with_ui_devplan()
    out = tmp_path / "out"
    _export(kg, out)

    uc = (out / "ui-spec" / "UC-001.md").read_text(encoding="utf-8")
    assert "## Satisfies" in uc
    assert "[F-001](../prd/F-001.md)" in uc


def test_task_renders_status_realizes_satisfies_verified_by(tmp_path: Path) -> None:
    kg = _make_store_with_ui_devplan()
    out = tmp_path / "out"
    _export(kg, out)

    task = (out / "dev-plan" / "T-001.md").read_text(encoding="utf-8")
    assert "## Status" in task
    assert "in_progress" in task
    assert "## Realizes" in task
    assert "[M-001](../arch/M-001.md)" in task
    assert "## Satisfies" in task
    assert "[AC-001](../prd/AC-001.md)" in task
    assert "## Verified By" in task
    assert "[TC-001](../test-report/TC-001.md)" in task


def test_ui_devplan_export_is_byte_identical_across_runs(tmp_path: Path) -> None:
    kg = _make_store_with_ui_devplan()
    r1 = _export(kg, tmp_path / "out1")
    r2 = _export(kg, tmp_path / "out2")
    assert r1.file_hashes == r2.file_hashes


def test_page_without_optional_scalars_omits_sections(tmp_path: Path) -> None:
    """A Page with no ui_route/layout_spec renders no Route/Layout headings."""
    from cataforge.domain.kg import KGConfig, KnowledgeGraph, init_store
    from cataforge.domain.kg.export import compile_to_markdown
    from cataforge.domain.kg.ingest.writer import write_project

    config = KGConfig(store_backend="memory")
    handle = init_store(config, force=True)
    project_iri = write_project(handle.raw, "proj-ui", "UI Slice", "waterfall", config)
    kg = KnowledgeGraph(handle.raw, config)
    with kg.transaction() as txn:
        txn.add_entity(
            entity_id="P-009",
            class_name="Page",
            title="Bare Page",
            source_doc="ui-spec",
            source_section="P-009",
            content_hash=hx("h-p9"),
            project_iri=project_iri,
        )

    out = tmp_path / "out"
    result = compile_to_markdown(kg.store, out)
    assert not result.errors

    page = (out / "ui-spec" / "P-009.md").read_text(encoding="utf-8")
    assert "## Route" not in page
    assert "## Layout" not in page
    assert "## Satisfies" not in page
