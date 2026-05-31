"""Full promotion of the business doc_type set into the KG paths.

Covers the two halves of "support a doc_type end to end":

* **render** — every SoftwareArtifact subclass materializes to Markdown,
  via a bespoke template when registered and the generic `_artifact`
  fallback otherwise. ui-spec / dev-plan / deploy-spec entities have no
  bespoke template yet, so they exercise the fallback.
* **wiring** — the active set, the ingest default, and `kg import`'s
  default scope all derive from the single `BUSINESS_DOC_TYPES` source,
  so a plain `kg import` ingests exactly what dispatch + the doctor gate
  expect (no `test` vs `test-report` drift, no hardcoded triplet).
"""

from __future__ import annotations

import gc
import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from cataforge.domain.kg._config import BUSINESS_DOC_TYPES


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _doc(doc_id: str, doc_type: str, section: str, body: str) -> str:
    return (
        f"---\nid: {doc_id}\ndoc_type: {doc_type}\nauthor: x\n"
        f"status: approved\ndeps: []\n---\n# {doc_id}\n\n{section}\n\n{body}\n"
    )


def _ingest_memory(project_root: Path, doc_types: tuple[str, ...]):
    from cataforge.domain.kg import KGConfig, init_store
    from cataforge.domain.kg.ingest import run_migration

    config = KGConfig(store_backend="memory")
    handle = init_store(config, force=True)
    run_migration(handle.raw, project_root, config, doc_types=doc_types)
    return handle


@pytest.fixture
def promoted_project(tmp_path: Path) -> Path:
    """A project carrying ui-spec / dev-plan / deploy-spec entities."""
    _write(
        tmp_path / "docs" / "ui-spec" / "ui-spec.md",
        _doc("ui-spec", "ui-spec", "## 3. Pages", "### P-001 Login page\n\nContains the form."),
    )
    _write(
        tmp_path / "docs" / "dev-plan" / "dev-plan.md",
        _doc("dev-plan", "dev-plan", "## 2. Tasks", "### T-001 Implement login\n\nBuild the flow."),
    )
    _write(
        tmp_path / "docs" / "deploy-spec" / "deploy-spec.md",
        _doc("deploy-spec", "deploy-spec", "## 1. Deployments", "### DP-001 Prod rollout\n\nB/G."),
    )
    return tmp_path


# --------------------------------------------------------------------------- #
# render — generic fallback                                                    #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("entity_id", "title_fragment"),
    [("P-001", "Login page"), ("T-001", "Implement login"), ("DP-001", "Prod rollout")],
)
def test_generic_fallback_renders_untemplated_classes(
    promoted_project: Path, entity_id: str, title_fragment: str
) -> None:
    from cataforge.domain.kg.export import render_entity

    handle = _ingest_memory(promoted_project, ("ui-spec", "dev-plan", "deploy-spec"))
    try:
        rendered = render_entity(handle.raw, entity_id)
    finally:
        del handle
        gc.collect()

    assert rendered is not None, f"{entity_id} did not render via the generic fallback"
    assert f"entity_id: {entity_id}" in rendered
    assert title_fragment in rendered
    assert rendered.startswith("---")  # artifact_base frontmatter


def test_registry_falls_back_to_generic_for_untemplated_class() -> None:
    from cataforge.domain.kg.export._entity_meta import GENERIC_SPARQL_KEY
    from cataforge.domain.kg.export.registry import SparqlRegistry

    reg = SparqlRegistry()
    # No bespoke Deployment template, but render is still possible: the
    # untemplated class resolves to the generic core-slots query.
    assert reg.get("Deployment") == reg.get(GENERIC_SPARQL_KEY)
    # A bespoke class keeps its own template.
    assert reg.get("Feature") != reg.get(GENERIC_SPARQL_KEY)


# --------------------------------------------------------------------------- #
# wiring — single source of truth                                              #
# --------------------------------------------------------------------------- #


def test_ingest_default_equals_business_doc_types() -> None:
    from cataforge.domain.kg.ingest import DEFAULT_DOC_TYPES

    assert tuple(DEFAULT_DOC_TYPES) == BUSINESS_DOC_TYPES


def test_business_set_uses_canonical_test_report_doc_id() -> None:
    # `test-report` is the doc_id refs use; the legacy `test` alias would
    # never match in dispatch's doc_id membership test.
    assert "test-report" in BUSINESS_DOC_TYPES
    assert "test" not in BUSINESS_DOC_TYPES


def test_kg_import_default_scope_follows_active_doc_types(tmp_path: Path) -> None:
    """A plain `kg import` ingests the project's active doc_types — proving
    import scope is wired to framework.json, not a hardcoded triplet."""
    from cataforge.domain.kg._dispatch import invalidate_cache
    from cataforge.interface.cli.main import _register_commands, cli

    project = tmp_path / "proj"
    _write(
        project / ".cataforge" / "framework.json",
        json.dumps({"context": {"kg_active_doc_types": ["dev-plan"]}}),
    )
    _write(
        project / "docs" / "dev-plan" / "dev-plan.md",
        _doc("dev-plan", "dev-plan", "## 2. Tasks", "### T-001 Implement login\n\nBuild it."),
    )
    # A prd doc that must NOT be ingested, since prd is not active here.
    _write(
        project / "docs" / "prd" / "prd.md",
        _doc("prd", "prd", "## 2. Features", "### F-001 Login\n\nUser logs in."),
    )
    invalidate_cache()
    _register_commands()
    runner = CliRunner()
    db_path = project / ".cataforge" / "kg" / "store"
    init = runner.invoke(cli, ["kg", "init", "--db-path", str(db_path), "--force"])
    assert init.exit_code == 0, init.output
    try:
        result = runner.invoke(
            cli,
            ["kg", "import", "--project-root", str(project), "--db-path", str(db_path), "--json"],
        )
        assert result.exit_code == 0, result.output
        stats = json.loads(result.output)
        # T-001 (dev-plan, active) ingested; F-001 (prd, inactive) skipped.
        assert stats["entities_written"] == 1, stats
    finally:
        gc.collect()
        invalidate_cache()
