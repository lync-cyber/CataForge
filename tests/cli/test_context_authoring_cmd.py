"""CLI surface for the P-2 authoring API: context write parent/relation/narrative
and the context transact multi-op command."""

from __future__ import annotations

import gc
import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from cataforge.domain.kg import KGConfig, KnowledgeGraph, init_store
from cataforge.domain.kg._dispatch import invalidate_cache


@pytest.fixture(autouse=True)
def _clear_caches():
    invalidate_cache()
    gc.collect()
    yield
    invalidate_cache()
    gc.collect()


def _cli():
    from cataforge.interface.cli.main import _register_commands, cli

    _register_commands()
    return cli


def _project(tmp_path: Path) -> Path:
    proj = tmp_path / "p"
    (proj / ".cataforge").mkdir(parents=True)
    (proj / "docs").mkdir()
    cfg = KGConfig(
        store_backend="oxigraph",
        db_path=proj / ".cataforge" / "kg" / "store",
        kg_active_doc_types={"prd", "arch", "test-report"},
    )
    handle = init_store(cfg, force=True)
    handle.raw.flush()
    handle.close()
    ctx = {"mode": "graph", "kg_active_doc_types": ["prd", "arch", "test-report"]}
    (proj / ".cataforge" / "framework.json").write_text(
        json.dumps({"context": ctx}), encoding="utf-8"
    )
    invalidate_cache()
    gc.collect()
    return proj


def _connect(proj: Path) -> KGConfig:
    return KGConfig(
        store_backend="oxigraph",
        db_path=proj / ".cataforge" / "kg" / "store",
        kg_active_doc_types={"prd", "arch", "test-report"},
    )


def _ns(cfg: KGConfig) -> str:
    return cfg.ontology_namespace.rstrip("/") + "/"


def _ask(kg: KnowledgeGraph, sparql: str) -> bool:
    from cataforge.domain.kg._ask import ask

    return ask(kg.store, sparql)


def test_context_write_parent_relation_narrative_full_slice(tmp_path: Path) -> None:
    proj = _project(tmp_path)
    runner = CliRunner()

    r = runner.invoke(
        _cli(),
        [
            "context",
            "write",
            "--entity-id",
            "F-001",
            "--class",
            "Feature",
            "--title",
            "用户登录",
            "--project-root",
            str(proj),
        ],
    )
    assert r.exit_code == 0, r.output
    gc.collect()

    r = runner.invoke(
        _cli(),
        [
            "context",
            "write",
            "--entity-id",
            "AC-001",
            "--class",
            "AcceptanceCriteria",
            "--title",
            "支持邮箱登录",
            "--parent",
            "F-001",
            "--narrative-stdin",
            "--project-root",
            str(proj),
        ],
        input="验收说明第一行\n\n验收说明第二行\n",
    )
    assert r.exit_code == 0, r.output
    gc.collect()

    r = runner.invoke(
        _cli(),
        [
            "context",
            "write",
            "--entity-id",
            "M-001",
            "--class",
            "Module",
            "--title",
            "认证模块",
            "--relation",
            "implements=F-001",
            "--project-root",
            str(proj),
        ],
    )
    assert r.exit_code == 0, r.output
    gc.collect()

    cfg = _connect(proj)
    ns = _ns(cfg)
    ac_iri = "https://cataforge.dev/instance/F-001/AC-001"
    with KnowledgeGraph.connect(cfg) as kg:
        assert _ask(
            kg, f"ASK {{ <{ac_iri}> <{ns}part_of> <https://cataforge.dev/instance/F-001> }}"
        )
        assert _ask(
            kg,
            f"ASK {{ <https://cataforge.dev/instance/M-001> "
            f"<{ns}implements> <https://cataforge.dev/instance/F-001> }}",
        )
        rows = list(
            kg.store.query(
                f"PREFIX cf: <{ns}> SELECT ?b WHERE {{ <{ac_iri}> cf:narrative_body ?b }}"
            )
        )
        assert rows and "验收说明第二行" in str(rows[0]["b"].value)
    gc.collect()


def test_context_write_narrative_inline_flag(tmp_path: Path) -> None:
    proj = _project(tmp_path)
    r = CliRunner().invoke(
        _cli(),
        [
            "context",
            "write",
            "--entity-id",
            "F-001",
            "--class",
            "Feature",
            "--title",
            "登录",
            "--narrative",
            "一句话说明",
            "--project-root",
            str(proj),
        ],
    )
    assert r.exit_code == 0, r.output
    gc.collect()
    cfg = _connect(proj)
    ns = _ns(cfg)
    with KnowledgeGraph.connect(cfg) as kg:
        rows = list(
            kg.store.query(
                f"PREFIX cf: <{ns}> SELECT ?b WHERE {{ "
                "<https://cataforge.dev/instance/F-001> cf:narrative_body ?b }"
            )
        )
        assert rows and "一句话说明" in str(rows[0]["b"].value)
    gc.collect()


def test_context_transact_from_stdin(tmp_path: Path) -> None:
    proj = _project(tmp_path)
    payload = {
        "operations": [
            {"op": "add_entity", "entity_id": "F-001", "class": "Feature", "title": "登录"},
            {
                "op": "add_entity",
                "entity_id": "AC-001",
                "class": "AcceptanceCriteria",
                "title": "验收一",
                "parent": "F-001",
            },
        ]
    }
    r = CliRunner().invoke(
        _cli(),
        ["context", "transact", "--project-root", str(proj)],
        input=json.dumps(payload),
    )
    assert r.exit_code == 0, r.output
    assert "2" in r.output
    gc.collect()
    cfg = _connect(proj)
    with KnowledgeGraph.connect(cfg) as kg:
        assert kg.query.exists("F-001")
        assert kg.query.exists("AC-001")
    gc.collect()


def test_context_transact_from_file(tmp_path: Path) -> None:
    proj = _project(tmp_path)
    payload = {
        "operations": [
            {"op": "add_entity", "entity_id": "F-001", "class": "Feature", "title": "登录"},
        ]
    }
    spec = tmp_path / "ops.json"
    spec.write_text(json.dumps(payload), encoding="utf-8")
    r = CliRunner().invoke(
        _cli(),
        ["context", "transact", "--file", str(spec), "--project-root", str(proj)],
    )
    assert r.exit_code == 0, r.output
    gc.collect()
    cfg = _connect(proj)
    with KnowledgeGraph.connect(cfg) as kg:
        assert kg.query.exists("F-001")
    gc.collect()


def test_context_transact_malformed_json_errors(tmp_path: Path) -> None:
    proj = _project(tmp_path)
    r = CliRunner().invoke(
        _cli(),
        ["context", "transact", "--project-root", str(proj)],
        input="{not json",
    )
    assert r.exit_code != 0
    assert "Error:" in r.output


def test_context_transact_registered_in_help() -> None:
    r = CliRunner().invoke(_cli(), ["context", "--help"])
    assert r.exit_code == 0
    assert "transact" in r.output


_DOC_MD = (
    "---\nid: prd\ndoc_type: prd\nstatus: draft\n---\n\n"
    "# PRD\n\nIntro.\n\n## §1 Features\n\n### F-001 登录\n\n说明文本。\n"
)


def test_context_write_doc_from_stdin(tmp_path: Path) -> None:
    proj = _project(tmp_path)
    r = CliRunner().invoke(
        _cli(),
        ["context", "write-doc", "--project-root", str(proj)],
        input=_DOC_MD,
    )
    assert r.exit_code == 0, r.output
    assert "authored prd" in r.output
    gc.collect()
    cfg = _connect(proj)
    with KnowledgeGraph.connect(cfg) as kg:
        assert kg.query.exists("F-001")
    gc.collect()


def test_context_write_doc_from_file(tmp_path: Path) -> None:
    proj = _project(tmp_path)
    doc = tmp_path / "prd.md"
    doc.write_text(_DOC_MD, encoding="utf-8")
    r = CliRunner().invoke(
        _cli(),
        ["context", "write-doc", "--file", str(doc), "--project-root", str(proj)],
    )
    assert r.exit_code == 0, r.output
    gc.collect()


def test_writedoc_warns_when_coverage_prose_yields_zero_relations(tmp_path: Path) -> None:
    """A whole-doc write whose coverage field is bare prose (no strict xref)
    extracts zero relations — write-doc warns on stderr, mirroring kg import."""
    proj = _project(tmp_path)
    md = (
        "---\nid: arch\ndoc_type: arch\nstatus: draft\n---\n\n"
        "# ARCH\n\n## §2 模块\n\n### M-001 认证模块\n\n- 对应功能: F-001\n"
    )
    r = CliRunner().invoke(
        _cli(),
        ["context", "write-doc", "--project-root", str(proj)],
        input=md,
    )
    assert r.exit_code == 0, r.output
    assert "0 relations" in r.output
    assert "relations=0" in r.stderr
    gc.collect()


def test_context_write_doc_registered_in_help() -> None:
    r = CliRunner().invoke(_cli(), ["context", "--help"])
    assert r.exit_code == 0
    assert "write-doc" in r.output
    assert "write-meta" in r.output


def test_context_write_meta_updates_status(tmp_path: Path) -> None:
    proj = _project(tmp_path)
    r = CliRunner().invoke(
        _cli(),
        ["context", "write-doc", "--project-root", str(proj)],
        input=_DOC_MD,
    )
    assert r.exit_code == 0, r.output
    gc.collect()
    r = CliRunner().invoke(
        _cli(),
        ["context", "write-meta", "prd", "--status", "approved", "--project-root", str(proj)],
    )
    assert r.exit_code == 0, r.output
    assert "status=approved" in r.output
    gc.collect()


def test_context_write_meta_requires_an_option(tmp_path: Path) -> None:
    proj = _project(tmp_path)
    r = CliRunner().invoke(
        _cli(),
        ["context", "write-meta", "prd", "--project-root", str(proj)],
    )
    assert r.exit_code != 0
    assert "at least one" in r.output
