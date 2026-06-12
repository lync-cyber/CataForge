"""`cataforge kg add / update / delete` CLI tests (backlog C3 / C4 / C5).

Each command is exercised against a freshly initialized RocksDB-backed
Oxigraph store at a tmp_path; happy path + at least one error path per
command. The shared ``_seed_project_with_entity`` fixture mirrors the
ingest writer's `write_project` + TransactionContext flow so update /
delete have something to operate on.
"""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner


def _cli():
    from cataforge.interface.cli.main import _register_commands, cli

    _register_commands()
    return cli


def _init_store(tmp_path: Path) -> Path:
    db = tmp_path / "store"
    result = CliRunner().invoke(_cli(), ["kg", "init", "--db-path", str(db)])
    assert result.exit_code == 0, result.output
    return db


def _seed_section(db: Path) -> None:
    import gc

    from cataforge.domain.kg import KGConfig, KnowledgeGraphStore
    from cataforge.domain.kg._dispatch import invalidate_cache
    from cataforge.domain.kg._quads import build_section_quads

    config = KGConfig(store_backend="oxigraph", db_path=db)
    with KnowledgeGraphStore.connect(config) as handle:
        for q in build_section_quads("prd", "§1 概览", "§1 概览", "正文", "a" * 64, "prd", config):
            handle.raw.add(q)
    gc.collect()
    invalidate_cache()


def _seed_project_with_entity(tmp_path: Path) -> Path:
    db = _init_store(tmp_path)
    result = CliRunner().invoke(
        _cli(),
        [
            "kg",
            "add",
            "F-001",
            "--class",
            "Feature",
            "--title",
            "Login flow",
            "--source-doc",
            "prd",
            "--source-section",
            "F-001 Login flow",
            "--project-id",
            "proj-test",
            "--project-title",
            "Test Project",
            "--db-path",
            str(db),
        ],
    )
    assert result.exit_code == 0, result.output
    return db


# ------------------------------------------------------------------
# kg add
# ------------------------------------------------------------------


class TestAdd:
    def test_add_creates_entity(self, tmp_path: Path) -> None:
        db = _seed_project_with_entity(tmp_path)
        result = CliRunner().invoke(
            _cli(),
            [
                "kg",
                "query",
                "--db-path",
                str(db),
                "--output",
                "json",
                "PREFIX cf: <https://cataforge.dev/ontology/> "
                "SELECT ?eid WHERE { ?s a cf:Feature ; cf:entity_id ?eid }",
            ],
        )
        assert result.exit_code == 0, result.output
        rows = json.loads(result.output)
        assert any(r["eid"] == "F-001" for r in rows)

    def test_add_idempotent_on_same_content_hash(self, tmp_path: Path) -> None:
        db = _seed_project_with_entity(tmp_path)
        result = CliRunner().invoke(
            _cli(),
            [
                "kg",
                "add",
                "F-001",
                "--class",
                "Feature",
                "--title",
                "Login flow",
                "--source-doc",
                "prd",
                "--source-section",
                "F-001 Login flow",
                "--db-path",
                str(db),
                "--json",
            ],
        )
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["entity_id"] == "F-001"
        assert payload["pending_inserts"] == 0
        assert payload["pending_deletes"] == 0

    def test_add_with_slots_and_relations(self, tmp_path: Path) -> None:
        db = _seed_project_with_entity(tmp_path)
        result = CliRunner().invoke(
            _cli(),
            [
                "kg",
                "add",
                "M-001",
                "--class",
                "Module",
                "--title",
                "Auth module",
                "--source-doc",
                "arch",
                "--source-section",
                "M-001 Auth",
                "--slot",
                "cf:priority=high",
                "--relation",
                "cf:implements=F-001",
                "--db-path",
                str(db),
                "--json",
            ],
        )
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["entity_id"] == "M-001"
        assert payload["relations_added"] == 1

        ask = CliRunner().invoke(
            _cli(),
            [
                "kg",
                "query",
                "--db-path",
                str(db),
                "PREFIX cf: <https://cataforge.dev/ontology/> "
                "ASK { <https://cataforge.dev/instance/M-001> "
                "cf:implements <https://cataforge.dev/instance/F-001> }",
            ],
        )
        assert ask.exit_code == 0, ask.output
        assert ask.output.strip() == "true"

    def test_add_requires_project_when_store_has_none(self, tmp_path: Path) -> None:
        db = _init_store(tmp_path)
        result = CliRunner().invoke(
            _cli(),
            [
                "kg",
                "add",
                "F-001",
                "--class",
                "Feature",
                "--title",
                "Login",
                "--db-path",
                str(db),
            ],
        )
        assert result.exit_code != 0
        assert "No cf:Project" in result.output

    def test_add_rejects_malformed_slot(self, tmp_path: Path) -> None:
        db = _seed_project_with_entity(tmp_path)
        result = CliRunner().invoke(
            _cli(),
            [
                "kg",
                "add",
                "F-002",
                "--class",
                "Feature",
                "--title",
                "Logout",
                "--source-doc",
                "prd",
                "--source-section",
                "F-002 Logout",
                "--slot",
                "missing_equals_sign",
                "--db-path",
                str(db),
            ],
        )
        assert result.exit_code != 0
        assert "--slot expects KEY=VALUE" in result.output


# ------------------------------------------------------------------
# kg update
# ------------------------------------------------------------------


class TestUpdate:
    def test_update_changes_title(self, tmp_path: Path) -> None:
        db = _seed_project_with_entity(tmp_path)
        result = CliRunner().invoke(
            _cli(),
            [
                "kg",
                "update",
                "F-001",
                "--title",
                "Login flow v2",
                "--db-path",
                str(db),
                "--json",
            ],
        )
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert "title" in payload["slots_updated"]
        assert payload["pending_inserts"] >= 1

        query = CliRunner().invoke(
            _cli(),
            [
                "kg",
                "query",
                "--db-path",
                str(db),
                "--output",
                "json",
                "PREFIX cf: <https://cataforge.dev/ontology/> "
                "SELECT ?title WHERE { "
                "  <https://cataforge.dev/instance/F-001> cf:title ?title }",
            ],
        )
        assert query.exit_code == 0, query.output
        rows = json.loads(query.output)
        assert rows[0]["title"] == "Login flow v2"

    def test_update_content_hash_match_is_noop(self, tmp_path: Path) -> None:
        import hashlib

        db = _seed_project_with_entity(tmp_path)
        payload = b"prd|F-001 Login flow|Login flow"
        original_hash = hashlib.sha256(payload).hexdigest()

        result = CliRunner().invoke(
            _cli(),
            [
                "kg",
                "update",
                "F-001",
                "--title",
                "ignored update",
                "--content-hash",
                original_hash,
                "--db-path",
                str(db),
                "--json",
            ],
        )
        assert result.exit_code == 0, result.output
        out = json.loads(result.output)
        assert out["pending_inserts"] == 0
        assert out["pending_deletes"] == 0

    def test_update_missing_entity_errors(self, tmp_path: Path) -> None:
        db = _seed_project_with_entity(tmp_path)
        result = CliRunner().invoke(
            _cli(),
            [
                "kg",
                "update",
                "F-999",
                "--title",
                "nope",
                "--db-path",
                str(db),
            ],
        )
        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_update_without_any_change_field_errors(self, tmp_path: Path) -> None:
        db = _seed_project_with_entity(tmp_path)
        result = CliRunner().invoke(
            _cli(),
            ["kg", "update", "F-001", "--db-path", str(db)],
        )
        assert result.exit_code != 0
        assert "at least one of" in result.output


# ------------------------------------------------------------------
# kg delete
# ------------------------------------------------------------------


class TestDelete:
    def test_delete_removes_entity(self, tmp_path: Path) -> None:
        db = _seed_project_with_entity(tmp_path)
        result = CliRunner().invoke(
            _cli(),
            [
                "kg",
                "delete",
                "F-001",
                "--yes",
                "--db-path",
                str(db),
                "--json",
            ],
        )
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["entity_id"] == "F-001"
        assert payload["pending_deletes"] >= 1

        ask = CliRunner().invoke(
            _cli(),
            [
                "kg",
                "query",
                "--db-path",
                str(db),
                'PREFIX cf: <https://cataforge.dev/ontology/> ASK { ?s cf:entity_id "F-001" }',
            ],
        )
        assert ask.exit_code == 0, ask.output
        assert ask.output.strip() == "false"

    def test_delete_rejects_incoming_edges_without_cascade(
        self,
        tmp_path: Path,
    ) -> None:
        db = _seed_project_with_entity(tmp_path)
        add_module = CliRunner().invoke(
            _cli(),
            [
                "kg",
                "add",
                "M-001",
                "--class",
                "Module",
                "--title",
                "Auth",
                "--source-doc",
                "arch",
                "--source-section",
                "M-001 Auth",
                "--relation",
                "cf:implements=F-001",
                "--db-path",
                str(db),
            ],
        )
        assert add_module.exit_code == 0, add_module.output

        result = CliRunner().invoke(
            _cli(),
            ["kg", "delete", "F-001", "--yes", "--db-path", str(db)],
        )
        assert result.exit_code != 0
        assert "incoming edge" in result.output
        assert "--cascade" in result.output

    def test_delete_cascade_removes_incoming_edges(self, tmp_path: Path) -> None:
        db = _seed_project_with_entity(tmp_path)
        CliRunner().invoke(
            _cli(),
            [
                "kg",
                "add",
                "M-001",
                "--class",
                "Module",
                "--title",
                "Auth",
                "--source-doc",
                "arch",
                "--source-section",
                "M-001 Auth",
                "--relation",
                "cf:implements=F-001",
                "--db-path",
                str(db),
            ],
        )

        result = CliRunner().invoke(
            _cli(),
            [
                "kg",
                "delete",
                "F-001",
                "--cascade",
                "--yes",
                "--db-path",
                str(db),
            ],
        )
        assert result.exit_code == 0, result.output
        assert "cascade" in result.output

        ask = CliRunner().invoke(
            _cli(),
            [
                "kg",
                "query",
                "--db-path",
                str(db),
                'PREFIX cf: <https://cataforge.dev/ontology/> ASK { ?s cf:entity_id "M-001" }',
            ],
        )
        assert ask.exit_code == 0
        assert ask.output.strip() == "true"

    def test_delete_missing_entity_errors(self, tmp_path: Path) -> None:
        db = _seed_project_with_entity(tmp_path)
        result = CliRunner().invoke(
            _cli(),
            ["kg", "delete", "F-999", "--yes", "--db-path", str(db)],
        )
        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_delete_interactive_abort(self, tmp_path: Path) -> None:
        db = _seed_project_with_entity(tmp_path)
        result = CliRunner().invoke(
            _cli(),
            ["kg", "delete", "F-001", "--db-path", str(db)],
            input="n\n",
        )
        assert result.exit_code == 0
        assert "Aborted" in result.output

        ask = CliRunner().invoke(
            _cli(),
            [
                "kg",
                "query",
                "--db-path",
                str(db),
                'PREFIX cf: <https://cataforge.dev/ontology/> ASK { ?s cf:entity_id "F-001" }',
            ],
        )
        assert ask.output.strip() == "true"

    def test_delete_section_by_structural_id(self, tmp_path: Path) -> None:
        db = _init_store(tmp_path)
        _seed_section(db)
        result = CliRunner().invoke(
            _cli(),
            ["kg", "delete", "doc/prd/sec/§1 概览", "--yes", "--db-path", str(db), "--json"],
        )
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["pending_deletes"] >= 1

        ask = CliRunner().invoke(
            _cli(),
            [
                "kg",
                "query",
                "--db-path",
                str(db),
                "PREFIX cf: <https://cataforge.dev/ontology/> ASK { ?s a cf:Section }",
            ],
        )
        assert ask.exit_code == 0, ask.output
        assert ask.output.strip() == "false"

    def test_delete_missing_section_reports_resolution(self, tmp_path: Path) -> None:
        db = _init_store(tmp_path)
        result = CliRunner().invoke(
            _cli(),
            ["kg", "delete", "doc/none/sec/missing", "--yes", "--db-path", str(db)],
        )
        assert result.exit_code != 0
        assert "not found" in result.output.lower()
        assert "section" in result.output.lower()

    def test_delete_malformed_structural_id_has_no_cascade_hint(self, tmp_path: Path) -> None:
        db = _init_store(tmp_path)
        result = CliRunner().invoke(
            _cli(),
            ["kg", "delete", "doc/", "--yes", "--db-path", str(db)],
        )
        assert result.exit_code != 0
        assert "--cascade" not in result.output

    def test_delete_help_documents_id_forms(self) -> None:
        result = CliRunner().invoke(_cli(), ["kg", "delete", "--help"])
        assert result.exit_code == 0
        assert "doc/" in result.output
        assert "/sec/" in result.output
        assert "IRI" in result.output

    def test_delete_json_without_yes_still_prompts(self, tmp_path: Path) -> None:
        """--json must not bypass the confirmation prompt (A4)."""
        db = _seed_project_with_entity(tmp_path)
        result = CliRunner().invoke(
            _cli(),
            ["kg", "delete", "F-001", "--json", "--db-path", str(db)],
            input="n\n",
        )
        assert result.exit_code == 0
        assert "Aborted" in result.output

        ask = CliRunner().invoke(
            _cli(),
            [
                "kg",
                "query",
                "--db-path",
                str(db),
                'PREFIX cf: <https://cataforge.dev/ontology/> ASK { ?s cf:entity_id "F-001" }',
            ],
        )
        assert ask.output.strip() == "true"
