"""Tests for `cataforge kg diff` — semantic snapshot diffing."""

from __future__ import annotations

from pathlib import Path

from tests.kg._kg_fixtures import hx


def _make_kg():
    from cataforge.domain.kg import KGConfig, KnowledgeGraph, init_store
    from cataforge.domain.kg.ingest.writer import write_project

    config = KGConfig(store_backend="memory")
    handle = init_store(config, force=True)
    project_iri = write_project(handle.raw, "proj-test", "Test Project", "waterfall", config)
    return KnowledgeGraph(handle.raw, config), config, project_iri


def _seed_baseline(kg, project_iri):
    """F-001, F-002, M-001 + edge M-001 cf:implements F-001."""
    with kg.transaction() as txn:
        for eid, title, h in (
            ("F-001", "Login", "h-f1"),
            ("F-002", "Logout", "h-f2"),
        ):
            txn.add_entity(
                entity_id=eid,
                class_name="Feature",
                title=title,
                source_doc="prd",
                source_section=f"{eid} {title}",
                content_hash=hx(h),
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
        txn.add_relation("M-001", "cf:implements", "F-001")


def _snapshot(kg, config, out_dir: Path, label: str) -> Path:
    from cataforge.domain.kg.snapshot import create_snapshot

    return create_snapshot(kg.store, config, out_dir, label=label).path


def test_diff_identical_snapshots_is_ok(tmp_path: Path) -> None:
    from cataforge.domain.kg.diff import diff_snapshots

    kg, config, project_iri = _make_kg()
    _seed_baseline(kg, project_iri)
    a = _snapshot(kg, config, tmp_path, "a")
    b = _snapshot(kg, config, tmp_path, "b")

    diff = diff_snapshots(a, b)

    assert diff.ok
    assert diff.divergence_count == 0


def test_diff_detects_all_change_classes(tmp_path: Path) -> None:
    from cataforge.domain.kg.diff import diff_snapshots

    kg, config, project_iri = _make_kg()
    _seed_baseline(kg, project_iri)
    a = _snapshot(kg, config, tmp_path, "a")

    with kg.transaction() as txn:
        txn.add_entity(
            entity_id="F-003",
            class_name="Feature",
            title="Reset",
            source_doc="prd",
            source_section="F-003 Reset",
            content_hash=hx("h-f3"),
            project_iri=project_iri,
        )
        txn.delete_entity("F-002")
        txn.update_entity("M-001", content_hash=hx("h-m1-v2"))
        txn.remove_relation("M-001", "cf:implements", "F-001")
        txn.add_relation("M-001", "cf:implements", "F-003")

    b = _snapshot(kg, config, tmp_path, "b")
    diff = diff_snapshots(a, b)

    assert diff.added_entities == ["F-003"]
    assert diff.removed_entities == ["F-002"]
    assert diff.modified_entities == ["M-001"]
    assert diff.added_relations == [("M-001", "cf:implements", "F-003")]
    assert diff.removed_relations == [("M-001", "cf:implements", "F-001")]
    assert not diff.ok


def test_diff_ignores_bootstrap_axioms(tmp_path: Path) -> None:
    """An empty store carries subclass axioms; diffing two empties is clean."""
    from cataforge.domain.kg import KGConfig, KnowledgeGraph, init_store
    from cataforge.domain.kg.diff import diff_snapshots

    config = KGConfig(store_backend="memory")
    kg = KnowledgeGraph(init_store(config, force=True).raw, config)
    a = _snapshot(kg, config, tmp_path, "a")
    b = _snapshot(kg, config, tmp_path, "b")

    diff = diff_snapshots(a, b)

    assert diff.ok
    assert diff.added_entities == []
    assert diff.removed_entities == []


def test_diff_direction_is_a_to_b(tmp_path: Path) -> None:
    """Swapping arguments turns adds into removes."""
    from cataforge.domain.kg.diff import diff_snapshots

    kg, config, project_iri = _make_kg()
    _seed_baseline(kg, project_iri)
    a = _snapshot(kg, config, tmp_path, "a")

    with kg.transaction() as txn:
        txn.add_entity(
            entity_id="F-003",
            class_name="Feature",
            title="Reset",
            source_doc="prd",
            source_section="F-003 Reset",
            content_hash=hx("h-f3"),
            project_iri=project_iri,
        )
    b = _snapshot(kg, config, tmp_path, "b")

    assert diff_snapshots(a, b).added_entities == ["F-003"]
    assert diff_snapshots(b, a).removed_entities == ["F-003"]


def test_diff_to_dict_is_json_serializable(tmp_path: Path) -> None:
    import json

    from cataforge.domain.kg.diff import diff_snapshots, render_diff_json

    kg, config, project_iri = _make_kg()
    _seed_baseline(kg, project_iri)
    a = _snapshot(kg, config, tmp_path, "a")
    with kg.transaction() as txn:
        txn.add_relation("M-001", "cf:implements", "F-002")
    b = _snapshot(kg, config, tmp_path, "b")

    diff = diff_snapshots(a, b)
    payload = json.loads(render_diff_json(diff))

    assert payload["added_relations"] == [["M-001", "cf:implements", "F-002"]]
    assert payload["ok"] is False
    assert payload["divergence_count"] == 1


def test_diff_cli_exits_nonzero_on_divergence(tmp_path: Path) -> None:
    from click.testing import CliRunner

    from cataforge.interface.cli.kg import kg_group

    kg, config, project_iri = _make_kg()
    _seed_baseline(kg, project_iri)
    a = _snapshot(kg, config, tmp_path, "a")
    with kg.transaction() as txn:
        txn.add_entity(
            entity_id="F-009",
            class_name="Feature",
            title="New",
            source_doc="prd",
            source_section="F-009 New",
            content_hash=hx("h-f9"),
            project_iri=project_iri,
        )
    b = _snapshot(kg, config, tmp_path, "b")

    runner = CliRunner()
    result = runner.invoke(kg_group, ["diff", str(a), str(b)])
    assert result.exit_code == 1
    assert "F-009" in result.output

    clean = runner.invoke(kg_group, ["diff", str(a), str(a)])
    assert clean.exit_code == 0
    assert "No differences" in clean.output
