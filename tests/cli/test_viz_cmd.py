"""Tests for ``cataforge viz`` + the shared core.viz IR / renderers."""

from __future__ import annotations

import ast
import json
import re
import sys
import threading
import time
import urllib.request
from pathlib import Path

import pytest
from click.testing import CliRunner

from cataforge.application.viz import html, service
from cataforge.core.errors import CataforgeError
from cataforge.core.viz import palette
from cataforge.core.viz.model import (
    Edge,
    Graph,
    MetricPoint,
    MetricSeries,
    Node,
    Status,
    Timeline,
    TimelineEvent,
)
from cataforge.core.viz.render import dot, json_, mermaid
from cataforge.interface.cli.main import cli

_CP_STYLE = palette.mermaid_style(Status.CRITICAL_PATH)


def _make_project(tmp_path: Path) -> Path:
    cf = tmp_path / ".cataforge"
    pm = cf / "agents" / "product-manager"
    pm.mkdir(parents=True)
    (pm / "AGENT.md").write_text("---\nskills: [research]\n---\nbody\n")
    framework = {
        "version": "0.1.0",
        "runtime_api_version": "1.0",
        "workflow": {
            "modes": {
                "standard": {
                    "phases": [
                        {"phase": "requirements", "role": "product-manager"},
                        {"phase": "development", "role": "tdd-engine"},
                    ]
                }
            }
        },
    }
    (cf / "framework.json").write_text(json.dumps(framework))
    return tmp_path


# ------------------------------------------------------------------
# Mermaid renderer — byte-exact, incl. the two legacy emitters' shapes
# ------------------------------------------------------------------


class TestMermaidRenderer:
    def test_trace_shape_quoted_labels_and_rel_edges(self) -> None:
        g = Graph(
            direction="TD",
            nodes=(Node("F-001", label="F-001: 标题"),),
            edges=(Edge("F-001", "M-001", label="implements"),),
        )
        assert mermaid.render(g) == (
            'graph TD\n    F-001["F-001: 标题"]\n    F-001 -->|implements| M-001'
        )

    def test_task_dep_shape_bare_edges_and_grouped_style(self) -> None:
        g = Graph(
            direction="LR",
            edges=(Edge("T-001", "T-002"), Edge("T-002", "T-003")),
            nodes=(
                Node("T-001", status=Status.CRITICAL_PATH),
                Node("T-003", status=Status.CRITICAL_PATH),
            ),
        )
        assert mermaid.render(g) == (
            f"graph LR\n    T-001 --> T-002\n    T-002 --> T-003\n    style T-001,T-003 {_CP_STYLE}"
        )

    def test_status_marker_prefixes_declared_label(self) -> None:
        g = Graph(direction="LR", nodes=(Node("F-001", label="F-001", status=Status.OK),))
        marker = palette.encoding(Status.OK).marker
        assert mermaid.render(g) == (
            f'graph LR\n    F-001["{marker} F-001"]\n'
            f"    style F-001 {palette.mermaid_style(Status.OK)}"
        )

    def test_cjk_label_stays_unquoted(self) -> None:
        g = Graph(direction="LR", nodes=(Node("n1", label="中文标签"),))
        assert mermaid.render(g) == "graph LR\n    n1[中文标签]"

    def test_empty_graph_renders_header_only(self) -> None:
        assert mermaid.render(Graph(direction="LR")) == "graph LR"

    def test_special_char_label_gets_quoted(self) -> None:
        g = Graph(nodes=(Node("a", label="has space"),))
        assert mermaid.render(g) == 'graph TD\n    a["has space"]'

    def test_timeline_groups_events_by_date(self) -> None:
        t = Timeline(
            title="evt",
            events=(
                TimelineEvent("2026-01-01T08:00:00", "phase_start requirements", "phase_start"),
                TimelineEvent("2026-01-01T09:00:00", "agent_dispatch architect", "agent_dispatch"),
                TimelineEvent("2026-01-02T00:00:00", "phase_end", "phase_end"),
            ),
        )
        assert mermaid.render(t) == (
            "timeline\n    title evt\n"
            "    2026-01-01 : phase_start requirements : agent_dispatch architect\n"
            "    2026-01-02 : phase_end"
        )

    def test_empty_timeline_placeholder(self) -> None:
        assert mermaid.render(Timeline()) == "timeline\n    title timeline\n    n/a : no events"

    def test_timeline_aggregated_count_suffix(self) -> None:
        t = Timeline(
            title="evt",
            events=(
                TimelineEvent("2026-01-01", "session_start", "session_start", count=9),
                TimelineEvent("2026-01-01", "correction", "correction"),
            ),
        )
        assert mermaid.render(t) == (
            "timeline\n    title evt\n    2026-01-01 : session_start ×9 : correction"
        )

    def test_rejects_metric_series(self) -> None:
        with pytest.raises(CataforgeError):
            mermaid.render(MetricSeries())


class TestDotRenderer:
    def test_basic(self) -> None:
        g = Graph(nodes=(Node("a", label="A"),), edges=(Edge("a", "b", label="rel"),))
        out = dot.render(g)
        assert "digraph G {" in out
        assert "rankdir=TB;" in out
        assert '"a" [label="A"];' in out
        assert '"a" -> "b" [label="rel"];' in out

    def test_rejects_non_graph(self) -> None:
        with pytest.raises(CataforgeError):
            dot.render(MetricSeries())


class TestJsonRenderer:
    def test_graph_kind(self) -> None:
        g = Graph(nodes=(Node("a", label="A"),), edges=(Edge("a", "b"),))
        data = json.loads(json_.render(g))
        assert data["kind"] == "graph"
        assert data["nodes"][0]["id"] == "a"
        assert data["edges"][0]["dst"] == "b"

    def test_timeline_kind(self) -> None:
        t = Timeline(events=(TimelineEvent("2026-01-01T00:00:00", "start", "phase"),))
        assert json.loads(json_.render(t))["kind"] == "timeline"

    def test_metrics_kind(self) -> None:
        m = MetricSeries(points=(MetricPoint("F-001", 1.0, "coverage"),))
        assert json.loads(json_.render(m))["kind"] == "metrics"

    def test_node_data_passthrough_and_omission(self) -> None:
        g = Graph(nodes=(Node("a", label="A", data={"type": "skill", "lines": 3}), Node("b")))
        nodes = json.loads(json_.render(g))["nodes"]
        assert nodes[0]["data"] == {"type": "skill", "lines": 3}
        assert "data" not in nodes[1]  # unset bag omitted — data-less JSON stays stable


# ------------------------------------------------------------------
# service dispatch guards
# ------------------------------------------------------------------


class TestService:
    def test_unknown_view(self, tmp_path: Path) -> None:
        with pytest.raises(CataforgeError):
            service.generate("nope", "mermaid", tmp_path)

    def test_unknown_format(self, tmp_path: Path) -> None:
        with pytest.raises(CataforgeError):
            service.generate("framework", "nope", tmp_path)

    def test_dashboard_requires_html(self, tmp_path: Path) -> None:
        with pytest.raises(CataforgeError, match="HTML-only"):
            service.generate("dashboard", "mermaid", tmp_path)


# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------


class TestVizCli:
    def test_group_help(self) -> None:
        result = CliRunner().invoke(cli, ["viz", "--help"])
        assert result.exit_code == 0, result.output
        assert "framework" in result.output

    def test_framework_help(self) -> None:
        result = CliRunner().invoke(cli, ["viz", "framework", "--help"])
        assert result.exit_code == 0, result.output

    def test_framework_mermaid(self, tmp_path: Path) -> None:
        _make_project(tmp_path)
        result = CliRunner().invoke(cli, ["--project-dir", str(tmp_path), "viz", "framework"])
        assert result.exit_code == 0, result.output
        for token in ("graph TD", "orchestrator", "requirements", "product-manager", "research"):
            assert token in result.output
        assert "tdd-engine" in result.output

    def test_framework_json(self, tmp_path: Path) -> None:
        _make_project(tmp_path)
        result = CliRunner().invoke(
            cli, ["--project-dir", str(tmp_path), "viz", "framework", "--format", "json"]
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["kind"] == "graph"
        labels = {n.get("label") for n in data["nodes"]}
        assert {"orchestrator", "requirements", "product-manager", "research"} <= labels

    def test_framework_nodes_carry_type(self, tmp_path: Path) -> None:
        # orchestrator / phase / agent / skill are visually distinct roles —
        # every framework node declares its kind for the type colour channel
        _make_project(tmp_path)
        result = CliRunner().invoke(
            cli, ["--project-dir", str(tmp_path), "viz", "framework", "--format", "json"]
        )
        assert result.exit_code == 0, result.output
        nodes = {n["id"]: n for n in json.loads(result.output)["nodes"]}
        assert nodes["orchestrator"]["data"]["type"] == "orchestrator"
        assert nodes["phase_requirements"]["data"]["type"] == "phase"
        assert nodes["agent_product_manager"]["data"]["type"] == "agent"
        assert nodes["skill_research"]["data"]["type"] == "skill"

    def test_framework_html_colours_types_without_clustering(self, tmp_path: Path) -> None:
        # the hierarchy IS the topology — types colour the nodes but must not
        # fold them into compound cluster boxes (that is the catalogue's form)
        _make_project(tmp_path)
        result = CliRunner().invoke(
            cli, ["--project-dir", str(tmp_path), "viz", "framework", "--html"]
        )
        assert result.exit_code == 0, result.output
        assert f'"bg": "{palette.TYPE_ENCODINGS["agent"].fill}"' in result.output
        assert '"parent": "cluster_' not in result.output
        assert "initCatalogue('" not in result.output

    def test_framework_dot(self, tmp_path: Path) -> None:
        _make_project(tmp_path)
        result = CliRunner().invoke(
            cli, ["--project-dir", str(tmp_path), "viz", "framework", "--format", "dot"]
        )
        assert result.exit_code == 0, result.output
        assert "digraph G {" in result.output

    def test_output_to_file(self, tmp_path: Path) -> None:
        _make_project(tmp_path)
        out = tmp_path / "fw.mmd"
        result = CliRunner().invoke(
            cli, ["--project-dir", str(tmp_path), "viz", "framework", "-o", str(out)]
        )
        assert result.exit_code == 0, result.output
        assert "graph TD" in out.read_text()


# ------------------------------------------------------------------
# KG views — trace / coverage / arch over the vertical-slice fixture
# ------------------------------------------------------------------

_KG_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "kg-vertical-slice" / "waterfall"


def _make_kg_project(tmp_path: Path) -> Path:
    """Project dir with an ingested KG store at the canonical location."""
    db = tmp_path / ".cataforge" / "kg" / "store"
    runner = CliRunner()
    init = runner.invoke(cli, ["kg", "init", "--db-path", str(db)])
    assert init.exit_code == 0, init.output
    imp = runner.invoke(
        cli, ["kg", "import", "--project-root", str(_KG_FIXTURE), "--db-path", str(db)]
    )
    assert imp.exit_code == 0, imp.output
    return tmp_path


def _viz(tmp_path: Path, *args: str):
    return CliRunner().invoke(cli, ["--project-dir", str(tmp_path), "viz", *args])


class TestVizTrace:
    def test_single_entity_reaches_module(self, tmp_path: Path) -> None:
        _make_kg_project(tmp_path)
        result = _viz(tmp_path, "trace", "F-001")
        assert result.exit_code == 0, result.output
        assert "graph TD" in result.output
        assert "F-001" in result.output
        assert "M-001" in result.output
        assert "-->" in result.output

    def test_aggregate_covers_all_features(self, tmp_path: Path) -> None:
        _make_kg_project(tmp_path)
        result = _viz(tmp_path, "trace")
        assert result.exit_code == 0, result.output
        assert "F-001" in result.output
        assert "F-002" in result.output

    def test_json_kind_graph(self, tmp_path: Path) -> None:
        _make_kg_project(tmp_path)
        result = _viz(tmp_path, "trace", "F-001", "--format", "json")
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["kind"] == "graph"
        assert any(n["id"] == "F-001" for n in data["nodes"])

    def test_trace_nodes_carry_layer_type(self, tmp_path: Path) -> None:
        # each node names its chain layer — the fold chips and the inspector
        # read the layer from data.type, no id-prefix guessing
        _make_kg_project(tmp_path)
        result = _viz(tmp_path, "trace", "F-001", "--format", "json")
        nodes = {n["id"]: n for n in json.loads(result.output)["nodes"]}
        assert nodes["F-001"]["data"]["type"] == "requirements"
        assert nodes["M-001"]["data"]["type"] == "modules"

    def test_nonexistent_entity_fails(self, tmp_path: Path) -> None:
        _make_kg_project(tmp_path)
        result = _viz(tmp_path, "trace", "NOPE-999")
        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_uninitialised_store_degrades(self, tmp_path: Path) -> None:
        _make_project(tmp_path)  # project root without a KG store
        result = _viz(tmp_path, "trace", "F-001")
        assert result.exit_code != 0
        assert "kg init" in result.output.lower()


class TestVizCoverage:
    def test_node_count_equals_feature_count(self, tmp_path: Path) -> None:
        _make_kg_project(tmp_path)
        result = _viz(tmp_path, "coverage", "--format", "json")
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        ids = {n["id"] for n in data["nodes"]}
        assert ids == {"F-001", "F-002"}

    def test_mermaid_styles_by_status(self, tmp_path: Path) -> None:
        _make_kg_project(tmp_path)
        result = _viz(tmp_path, "coverage")
        assert result.exit_code == 0, result.output
        assert "style" in result.output

    def test_under_covered_node_carries_remediation_hint(self, tmp_path: Path) -> None:
        # a Feature missing impl and/or test gets a data bag naming the gap plus
        # a ``run:`` drill-in — an action outlet, not just a red colour.
        _make_kg_project(tmp_path)
        result = _viz(tmp_path, "coverage", "--format", "json")
        nodes = {n["id"]: n for n in json.loads(result.output)["nodes"]}
        gap = nodes["F-001"]["data"]
        assert gap["issue"] in {"缺测试", "缺实现", "缺实现与测试"}
        assert gap["hint"] == "run: cataforge viz trace F-001"


class TestVizArch:
    def test_lists_modules(self, tmp_path: Path) -> None:
        _make_kg_project(tmp_path)
        result = _viz(tmp_path, "arch")
        assert result.exit_code == 0, result.output
        assert "M-001" in result.output
        assert "M-002" in result.output

    def test_json_kind_graph(self, tmp_path: Path) -> None:
        _make_kg_project(tmp_path)
        result = _viz(tmp_path, "arch", "--format", "json")
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["kind"] == "graph"
        labels = {n.get("label") for n in data["nodes"]}
        assert any(label and label.startswith("M-001") for label in labels)


def _make_arch_relations_project(tmp_path: Path) -> Path:
    """Graph-mode project with authored arch relations: an M-001 ⇄ M-002
    ``depends_on`` cycle, M-003 as an off-cycle dependant, and C-001
    ``part_of`` M-001 — the composition + cycle-marking fixture."""
    db = tmp_path / ".cataforge" / "kg" / "store"
    runner = CliRunner()
    init = runner.invoke(cli, ["kg", "init", "--db-path", str(db)])
    assert init.exit_code == 0, init.output
    (tmp_path / ".cataforge" / "framework.json").write_text(
        json.dumps({"context": {"mode": "graph"}}), encoding="utf-8"
    )
    spec = {
        "operations": [
            {"op": "add_entity", "entity_id": "M-001", "class": "Module", "title": "认证模块"},
            {"op": "add_entity", "entity_id": "M-002", "class": "Module", "title": "会话模块"},
            {"op": "add_entity", "entity_id": "M-003", "class": "Module", "title": "审计模块"},
            {
                "op": "add_entity",
                "entity_id": "C-001",
                "class": "Component",
                "title": "登录处理器",
                "relations": [["part_of", "M-001"]],
            },
            {
                "op": "add_relation",
                "subject": "M-001",
                "predicate": "depends_on",
                "object": "M-002",
            },
            {
                "op": "add_relation",
                "subject": "M-002",
                "predicate": "depends_on",
                "object": "M-001",
            },
            {
                "op": "add_relation",
                "subject": "M-003",
                "predicate": "depends_on",
                "object": "M-002",
            },
        ]
    }
    r = runner.invoke(
        cli, ["context", "transact", "--project-root", str(tmp_path)], input=json.dumps(spec)
    )
    assert r.exit_code == 0, r.output
    return tmp_path


class TestVizArchRelations:
    def test_part_of_edge_labelled(self, tmp_path: Path) -> None:
        # composition rides a labelled edge so the module hierarchy is visible
        # next to (and distinct from) the dependency edges
        _make_arch_relations_project(tmp_path)
        result = _viz(tmp_path, "arch")
        assert result.exit_code == 0, result.output
        assert "C-001 -->|part_of| M-001" in result.output
        assert "M-003 -->|depends_on| M-002" in result.output

    def test_dependency_cycle_nodes_flagged(self, tmp_path: Path) -> None:
        # the arch dependency graph must be a DAG — cycle members get the
        # CYCLE status (colour + textual marker), off-cycle nodes stay clean
        _make_arch_relations_project(tmp_path)
        result = _viz(tmp_path, "arch")
        assert result.exit_code == 0, result.output
        assert palette.mermaid_style(Status.CYCLE) in result.output
        assert palette.encoding(Status.CYCLE).marker in result.output

    def test_json_statuses_and_edge_labels(self, tmp_path: Path) -> None:
        _make_arch_relations_project(tmp_path)
        result = _viz(tmp_path, "arch", "--format", "json")
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        nodes = {n["id"]: n for n in data["nodes"]}
        assert nodes["M-001"]["status"] == "cycle"
        assert nodes["M-002"]["status"] == "cycle"
        assert nodes["M-003"]["status"] is None  # depends on the cycle, not in it
        assert nodes["C-001"]["status"] is None  # part_of edges never mark cycles
        labels = {(e["src"], e["dst"]): e.get("label") for e in data["edges"]}
        assert labels[("C-001", "M-001")] == "part_of"
        assert labels[("M-001", "M-002")] == "depends_on"

    def test_acyclic_arch_stays_unmarked(self, tmp_path: Path) -> None:
        # the vertical-slice fixture has no dependency edges at all — nothing
        # may carry a CYCLE marker on a healthy architecture
        _make_kg_project(tmp_path)
        result = _viz(tmp_path, "arch", "--format", "json")
        assert result.exit_code == 0, result.output
        assert all(n["status"] is None for n in json.loads(result.output)["nodes"])


# ------------------------------------------------------------------
# docs view — doc-index dependency graph with stale / xref styling
# ------------------------------------------------------------------


def _make_docs_project(tmp_path: Path) -> Path:
    """Project dir with a hand-built doc-index: one stale dep + one broken xref."""
    index = {
        "version": "1",
        "documents": {
            "prd-x": {
                "file_path": "docs/prd/prd-x.md",
                "doc_type": "prd",
                "content_hash": "h_prd",
                "deps": [],
                "dep_hashes": {},
            },
            "arch-x": {
                "file_path": "docs/arch/arch-x.md",
                "doc_type": "arch",
                "content_hash": "h_arch",
                "deps": ["ghost#§2"],
                "dep_hashes": {},
            },
            "dev-x": {
                "file_path": "docs/dev-plan/dev-x.md",
                "doc_type": "dev-plan",
                "content_hash": "h_dev",
                "deps": ["arch-x"],
                "dep_hashes": {"arch-x": "OLD_HASH"},
            },
        },
        "xref": {},
    }
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / ".doc-index.json").write_text(json.dumps(index), encoding="utf-8")
    return tmp_path


class TestVizDocs:
    def test_stale_dep_styled_and_labelled(self, tmp_path: Path) -> None:
        _make_docs_project(tmp_path)
        result = _viz(tmp_path, "docs")
        assert result.exit_code == 0, result.output
        assert "graph LR" in result.output
        # stale: dev-x pinned an old arch-x hash → coloured node + labelled edge
        assert "dev-x -->|stale| arch-x" in result.output
        assert "style dev-x" in result.output

    def test_broken_xref_marked(self, tmp_path: Path) -> None:
        _make_docs_project(tmp_path)
        result = _viz(tmp_path, "docs")
        assert result.exit_code == 0, result.output
        # arch-x depends on a doc absent from the index → xref-error edge
        assert "arch-x -->|xref-error| ghost" in result.output

    def test_json_kind_graph(self, tmp_path: Path) -> None:
        _make_docs_project(tmp_path)
        result = _viz(tmp_path, "docs", "--format", "json")
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["kind"] == "graph"
        labels = {(e["src"], e["dst"]): e.get("label") for e in data["edges"]}
        assert labels[("dev-x", "arch-x")] == "stale"
        assert labels[("arch-x", "ghost")] == "xref-error"

    def test_stale_and_xref_nodes_carry_remediation_hints(self, tmp_path: Path) -> None:
        # a data-present-but-wrong node guides like a missing-data one: the stale
        # downstream and the dangling xref target each carry a ``run:`` outlet.
        _make_docs_project(tmp_path)
        result = _viz(tmp_path, "docs", "--format", "json")
        nodes = {n["id"]: n for n in json.loads(result.output)["nodes"]}
        assert nodes["dev-x"]["data"] == {
            "type": "dev-plan",
            "issue": "stale",
            "hint": "run: cataforge context reconcile",
        }
        assert nodes["ghost"]["data"] == {
            "issue": "xref-error",
            "hint": "run: cataforge context validate",
        }

    def test_healthy_node_data_bag_carries_type_only(self, tmp_path: Path) -> None:
        # prd-x has no stale/xref problem → its bag holds the doc_type and
        # nothing else (no remediation hint on a healthy doc)
        _make_docs_project(tmp_path)
        result = _viz(tmp_path, "docs", "--format", "json")
        nodes = {n["id"]: n for n in json.loads(result.output)["nodes"]}
        assert nodes["prd-x"]["data"] == {"type": "prd"}
        assert nodes["prd-x"]["label"] == "prd-x"  # type moved off the label

    def test_dangling_xref_target_has_no_type(self, tmp_path: Path) -> None:
        # ghost is not in the index — nothing to type it with
        _make_docs_project(tmp_path)
        result = _viz(tmp_path, "docs", "--format", "json")
        nodes = {n["id"]: n for n in json.loads(result.output)["nodes"]}
        assert "type" not in (nodes["ghost"].get("data") or {})

    def test_healthy_doc_marked_ok(self, tmp_path: Path) -> None:
        # a doc that passed the stale/xref validators is verified fine — it
        # carries an explicit ok, so "no signal" stays a genuinely rare state
        _make_docs_project(tmp_path)
        result = _viz(tmp_path, "docs", "--format", "json")
        nodes = {n["id"]: n for n in json.loads(result.output)["nodes"]}
        assert nodes["prd-x"]["status"] == "ok"
        assert nodes["dev-x"]["status"] == "partial"  # stale keeps its anomaly status
        assert nodes["ghost"]["status"] == "broken"  # dangling xref target unchanged

    def test_missing_index_degrades(self, tmp_path: Path) -> None:
        result = _viz(tmp_path, "docs")
        assert result.exit_code != 0
        assert "context index" in result.output.lower()


# ------------------------------------------------------------------
# tasks view — DAG with critical-path / cycle styling (task-dep-analysis annex)
# ------------------------------------------------------------------

_TASK_EDGES = "T-001→T-002,T-002→T-003,T-001→T-004"
_KG_TASKS_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "kg-tasks"


def _make_kg_tasks_project(tmp_path: Path) -> Path:
    """Project dir with a KG store holding Task entities + depends_on edges."""
    db = tmp_path / ".cataforge" / "kg" / "store"
    runner = CliRunner()
    init = runner.invoke(cli, ["kg", "init", "--db-path", str(db)])
    assert init.exit_code == 0, init.output
    imp = runner.invoke(
        cli, ["kg", "import", "--project-root", str(_KG_TASKS_FIXTURE), "--db-path", str(db)]
    )
    assert imp.exit_code == 0, imp.output
    return tmp_path


class TestVizTasksFromEdges:
    def test_critical_path_highlighted(self, tmp_path: Path) -> None:
        result = _viz(tmp_path, "tasks", "--edges", _TASK_EDGES)
        assert result.exit_code == 0, result.output
        assert "graph LR" in result.output
        assert "T-001 --> T-002" in result.output
        assert _CP_STYLE in result.output  # critical-path nodes highlighted
        assert palette.encoding(Status.CRITICAL_PATH).marker in result.output

    def test_nodes_edges_match_task_dep_analysis(self, tmp_path: Path) -> None:
        from collections import defaultdict

        from cataforge.runtime.skill.builtins.task_dep_analysis.task_dep_analysis import (
            parse_edges,
            topological_sort,
        )

        parsed = parse_edges(_TASK_EDGES)
        graph: dict[str, list[str]] = defaultdict(list)
        all_nodes: set[str] = set()
        for u, v in parsed:
            graph[u].append(v)
            all_nodes.add(u)
            all_nodes.add(v)
        topo = topological_sort(graph, all_nodes)

        result = _viz(tmp_path, "tasks", "--edges", _TASK_EDGES, "--format", "json")
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["kind"] == "graph"
        seen = {n["id"] for n in data["nodes"]}
        seen |= {e["src"] for e in data["edges"]} | {e["dst"] for e in data["edges"]}
        assert seen == set(topo)
        assert {(e["src"], e["dst"]) for e in data["edges"]} == set(parsed)

    def test_cycle_nodes_flagged(self, tmp_path: Path) -> None:
        result = _viz(tmp_path, "tasks", "--edges", "T-001→T-002,T-002→T-001")
        assert result.exit_code == 0, result.output
        assert palette.mermaid_style(Status.CYCLE) in result.output
        assert palette.encoding(Status.CYCLE).marker in result.output  # textual channel

    def test_invalid_edges_render_empty_graph(self, tmp_path: Path) -> None:
        # non-empty edges that parse to nothing → empty graph + status nudge
        result = _viz(tmp_path, "tasks", "--edges", "garbage-no-arrow")
        assert result.exit_code == 0, result.output
        assert "graph LR" in result.output
        assert "无有效边" not in result.output
        assert "viz status" in result.output  # empty-view nudge (stderr)


class TestVizTasksFromKg:
    def test_reads_depends_on_chain(self, tmp_path: Path) -> None:
        _make_kg_tasks_project(tmp_path)
        result = _viz(tmp_path, "tasks")  # no --edges → KG source
        assert result.exit_code == 0, result.output
        assert "graph LR" in result.output
        assert "T-001 --> T-002" in result.output
        assert "T-002 --> T-003" in result.output

    def test_json_nodes_match_kg_tasks(self, tmp_path: Path) -> None:
        _make_kg_tasks_project(tmp_path)
        result = _viz(tmp_path, "tasks", "--format", "json")
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        edges = {(e["src"], e["dst"]) for e in data["edges"]}
        assert edges == {("T-001", "T-002"), ("T-002", "T-003")}

    def test_no_tasks_empty_graph(self, tmp_path: Path) -> None:
        _make_kg_project(tmp_path)  # KG with Features/Modules but no Tasks
        result = _viz(tmp_path, "tasks")
        assert result.exit_code == 0, result.output
        assert "无有效边" not in result.output
        assert "viz status" in result.output  # empty-view nudge (stderr)

    def test_uninitialised_store_degrades(self, tmp_path: Path) -> None:
        result = _viz(tmp_path, "tasks")  # no --edges, no KG store
        assert result.exit_code != 0
        assert "kg init" in result.output.lower()


# ------------------------------------------------------------------
# process views — phase / timeline / decay
# ------------------------------------------------------------------


def _make_phase_project(
    tmp_path: Path, phase: str, *, phase_start: str | None = None, mode: str | None = None
) -> Path:
    """Project with framework.json (all three execution modes) + an instruction
    file declaring 当前阶段 (and 执行模式 when *mode* is given); optionally a
    phase_start EVENT-LOG record."""
    cf = tmp_path / ".cataforge"
    cf.mkdir()
    framework = {
        "workflow": {
            "modes": {
                "standard": {
                    "phases": [
                        {"phase": "requirements", "role": "product-manager"},
                        {"phase": "architecture", "role": "architect"},
                        {"phase": "development", "role": "tdd-engine"},
                    ]
                },
                "agile-lite": {
                    "phases": [
                        {"phase": "planning", "role": "product-manager"},
                        {"phase": "development", "role": "tdd-engine"},
                    ]
                },
                "agile-prototype": {
                    "phases": [
                        {"phase": "brief", "role": "product-manager"},
                        {"phase": "development", "role": "tdd-engine"},
                    ]
                },
            }
        }
    }
    (cf / "framework.json").write_text(json.dumps(framework))
    mode_line = f"- 执行模式: {mode}\n" if mode else ""
    (tmp_path / "CLAUDE.md").write_text(
        f"# Proj\n## 项目状态\n- 当前阶段: {phase}\n{mode_line}- 文档状态:\n", encoding="utf-8"
    )
    if phase_start:
        docs = tmp_path / "docs"
        docs.mkdir(exist_ok=True)
        rec = {"ts": "2026-01-01T00:00:00+00:00", "event": "phase_start", "phase": phase_start}
        (docs / "EVENT-LOG.jsonl").write_text(json.dumps(rec) + "\n", encoding="utf-8")
    return tmp_path


class TestVizPhase:
    def test_blocked_phase_styled_missing(self, tmp_path: Path) -> None:
        _make_phase_project(tmp_path, "requirements")  # no prd doc/index/event → blocked
        result = _viz(tmp_path, "phase")
        assert result.exit_code == 0, result.output
        assert "graph LR" in result.output
        assert f"style requirements {palette.mermaid_style(Status.MISSING)}" in result.output

    def test_ok_phase_styled_ok(self, tmp_path: Path) -> None:
        # development carries no doc gate; with its phase_start it passes all checks
        _make_phase_project(tmp_path, "development", phase_start="development")
        result = _viz(tmp_path, "phase")
        assert result.exit_code == 0, result.output
        assert f"style development {palette.mermaid_style(Status.OK)}" in result.output

    def test_styling_tracks_phase_status_conclusion(self, tmp_path: Path) -> None:
        from cataforge.application.phase import evaluate_phase

        _make_phase_project(tmp_path, "development", phase_start="development")
        _, checks = evaluate_phase(tmp_path)
        blocked = any(not ok for _, ok, _ in checks)
        result = _viz(tmp_path, "phase")
        # the ok fill appears iff the gate is not blocked — same conclusion
        # that drives `cataforge phase status` exit code.
        assert (palette.encoding(Status.OK).fill in result.output) == (not blocked)

    def test_not_driven_degrades(self, tmp_path: Path) -> None:
        result = _viz(tmp_path, "phase")  # no instruction file
        assert result.exit_code != 0
        assert "claude.md" in result.output.lower()


class TestVizTimeline:
    def _write_log(self, tmp_path: Path, lines: list[str]) -> None:
        docs = tmp_path / "docs"
        docs.mkdir(exist_ok=True)
        (docs / "EVENT-LOG.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def test_events_rendered_malformed_skipped(self, tmp_path: Path) -> None:
        self._write_log(
            tmp_path,
            [
                json.dumps(
                    {
                        "ts": "2026-01-01T08:00:00+00:00",
                        "event": "phase_start",
                        "phase": "requirements",
                    }
                ),
                json.dumps(
                    {
                        "ts": "2026-01-01T09:00:00+00:00",
                        "event": "agent_dispatch",
                        "agent": "architect",
                    }
                ),
                "{ not valid json",  # skipped, must not drop the valid neighbours
                json.dumps(
                    {
                        "ts": "2026-01-02T00:00:00+00:00",
                        "event": "phase_end",
                        "phase": "requirements",
                    }
                ),
            ],
        )
        result = _viz(tmp_path, "timeline")
        assert result.exit_code == 0, result.output
        assert result.output.startswith("timeline")
        assert "phase_start requirements" in result.output
        assert "agent_dispatch architect" in result.output
        assert "phase_end requirements" in result.output

    def test_json_keeps_all_valid_events(self, tmp_path: Path) -> None:
        self._write_log(
            tmp_path,
            [
                json.dumps(
                    {"ts": "2026-01-01T08:00:00+00:00", "event": "phase_start", "phase": "x"}
                ),
                "garbage",
                json.dumps({"ts": "2026-01-02T00:00:00+00:00", "event": "phase_end"}),
            ],
        )
        result = _viz(tmp_path, "timeline", "--format", "json")
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["kind"] == "timeline"
        assert len(data["events"]) == 2

    def test_same_day_same_label_events_aggregate(self, tmp_path: Path) -> None:
        rec = {"ts": "2026-01-01T0{}:00:00+00:00", "event": "session_start", "status": "session"}
        self._write_log(
            tmp_path,
            [json.dumps(rec).replace("0{}", f"0{h}") for h in range(3)]
            + [json.dumps({"ts": "2026-01-01T09:00:00+00:00", "event": "correction"})],
        )
        result = _viz(tmp_path, "timeline", "--format", "json")
        assert result.exit_code == 0, result.output
        events = {e["label"]: e for e in json.loads(result.output)["events"]}
        assert len(events) == 2
        assert events["session_start"]["count"] == 3
        assert events["session_start"]["ts"] == "2026-01-01"  # day-precision after fold
        assert events["correction"]["count"] == 1

    def test_low_information_ctx_omitted_from_label(self, tmp_path: Path) -> None:
        # ctx contained in the event name ("session" ⊂ "session_start") adds
        # nothing — the label stays the bare event name.
        self._write_log(
            tmp_path,
            [
                json.dumps(
                    {
                        "ts": "2026-01-01T08:00:00+00:00",
                        "event": "session_start",
                        "status": "session",
                    }
                )
            ],
        )
        result = _viz(tmp_path, "timeline", "--format", "json")
        events = json.loads(result.output)["events"]
        assert events[0]["label"] == "session_start"

    def test_empty_when_no_log(self, tmp_path: Path) -> None:
        result = _viz(tmp_path, "timeline")
        assert result.exit_code == 0, result.output
        assert "no events" in result.output


class TestVizDecay:
    def test_corrections_become_timeline(self, tmp_path: Path) -> None:
        log_dir = tmp_path / "docs" / "reviews"
        log_dir.mkdir(parents=True)
        (log_dir / "CORRECTIONS-LOG.md").write_text(
            "# Corrections\n\n"
            "### 2026-01-01 | reviewer | development\n- 偏差类型: preference\n\n"
            "### 2026-01-02 | architect | architecture\n- 偏差类型: upstream-gap\n",
            encoding="utf-8",
        )
        result = _viz(tmp_path, "decay")
        assert result.exit_code == 0, result.output
        assert result.output.startswith("timeline")
        assert "preference" in result.output
        assert "upstream-gap" in result.output

    def test_same_day_same_deviation_corrections_aggregate(self, tmp_path: Path) -> None:
        log_dir = tmp_path / "docs" / "reviews"
        log_dir.mkdir(parents=True)
        (log_dir / "CORRECTIONS-LOG.md").write_text(
            "# C\n\n"
            "### 2026-01-01 | reviewer | development\n- 偏差类型: preference\n\n"
            "### 2026-01-01 | reviewer | development\n- 偏差类型: preference\n",
            encoding="utf-8",
        )
        result = _viz(tmp_path, "decay", "--format", "json")
        events = json.loads(result.output)["events"]
        assert len(events) == 1
        assert events[0]["count"] == 2

    def test_empty_when_no_log(self, tmp_path: Path) -> None:
        result = _viz(tmp_path, "decay")
        assert result.exit_code == 0, result.output
        assert "no events" in result.output


# ------------------------------------------------------------------
# assets view — agent / skill catalogue graph
# ------------------------------------------------------------------


def _make_assets_project(tmp_path: Path) -> Path:
    """_make_project plus a project skill (maintainer-only, full frontmatter)
    and a rules file — the catalogue-metadata fixture."""
    _make_project(tmp_path)
    cf = tmp_path / ".cataforge"
    (cf / "agents" / "product-manager" / "AGENT.md").write_text(
        "---\n"
        "description: 产品经理 — 需求分析\n"
        "tools: file_read, shell_exec\n"
        "skills: [research]\n"
        "---\nbody\n"
    )
    skill = cf / "skills" / "demo-skill"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\n"
        "name: demo-skill\n"
        'description: "演示 skill — 什么都不做"\n'
        "depends: [research]\n"
        "suggested-tools: shell_exec\n"
        "maintainer-only: true\n"
        "---\n\n# demo\n\nbody line\n"
    )
    rules = cf / "rules"
    rules.mkdir()
    (rules / "COMMON-RULES.md").write_text("# 通用规则\n\n- 一条规则\n")
    return tmp_path


def _assets_json_nodes(tmp_path: Path) -> dict[str, dict]:
    result = _viz(tmp_path, "assets", "--format", "json")
    assert result.exit_code == 0, result.output
    return {n["id"]: n for n in json.loads(result.output)["nodes"]}


class TestVizAssets:
    def test_agent_skill_graph_text(self, tmp_path: Path) -> None:
        _make_project(tmp_path)
        result = _viz(tmp_path, "assets")
        assert result.exit_code == 0, result.output
        assert "graph LR" in result.output
        assert "product-manager" in result.output
        assert "research" in result.output

    def test_json_has_agent_skill_edge(self, tmp_path: Path) -> None:
        _make_project(tmp_path)
        result = _viz(tmp_path, "assets", "--format", "json")
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["kind"] == "graph"
        labels = {n.get("label") for n in data["nodes"]}
        assert {"product-manager", "research"} <= labels
        edges = {(e["src"], e["dst"]) for e in data["edges"]}
        assert ("agent_product_manager", "skill_research") in edges

    def test_text_formats_unchanged_by_metadata_and_rules(self, tmp_path: Path) -> None:
        """Metadata rides in ``data`` only and rules are implicit nodes — the
        Mermaid/DOT output must not mention them."""
        _make_assets_project(tmp_path)
        for fmt in ("mermaid", "dot"):
            result = _viz(tmp_path, "assets", "--format", fmt)
            assert result.exit_code == 0, result.output
            assert "COMMON-RULES" not in result.output
            assert "描述" not in result.output and "演示" not in result.output
            assert "demo-skill" in result.output  # the skill node itself still renders

    def test_skill_node_carries_catalogue_metadata(self, tmp_path: Path) -> None:
        _make_assets_project(tmp_path)
        data = _assets_json_nodes(tmp_path)["skill_demo_skill"]["data"]
        assert data["type"] == "skill"
        assert data["description"] == "演示 skill — 什么都不做"
        assert data["depends"] == "research"
        assert data["tools"] == "shell_exec"
        assert data["maintainer_only"] is True
        assert data["path"].replace("\\", "/") == ".cataforge/skills/demo-skill/SKILL.md"
        assert data["lines"] > 0
        assert data["est_tokens"] > 0

    def test_agent_node_carries_catalogue_metadata(self, tmp_path: Path) -> None:
        _make_assets_project(tmp_path)
        data = _assets_json_nodes(tmp_path)["agent_product_manager"]["data"]
        assert data["type"] == "agent"
        assert data["description"] == "产品经理 — 需求分析"
        assert data["tools"] == "file_read, shell_exec"
        assert data["depends"] == "research"  # an agent depends on its skills
        assert data["path"].replace("\\", "/") == ".cataforge/agents/product-manager/AGENT.md"

    def test_rules_listed_as_implicit_nodes(self, tmp_path: Path) -> None:
        _make_assets_project(tmp_path)
        node = _assets_json_nodes(tmp_path)["rules_COMMON_RULES"]
        assert node["label"] is None  # invisible to text renderers
        assert node["status"] is None
        assert node["data"]["type"] == "rules"
        assert node["data"]["name"] == "COMMON-RULES"
        assert node["data"]["lines"] > 0

    def test_unreadable_asset_file_degrades_to_placeholder(self, tmp_path: Path) -> None:
        """One undecodable file must not sink the view — volume keys go None."""
        _make_assets_project(tmp_path)
        (tmp_path / ".cataforge" / "rules" / "BAD.md").write_bytes(b"\xff\xfe\x00 broken")
        node = _assets_json_nodes(tmp_path)["rules_BAD"]
        assert node["data"]["lines"] is None
        assert node["data"]["est_tokens"] is None
        assert node["data"]["path"].endswith("BAD.md")

    def test_assets_html_renders_catalogue(self, tmp_path: Path) -> None:
        _make_assets_project(tmp_path)
        result = _viz(tmp_path, "assets", "--html")
        assert result.exit_code == 0, result.output
        out = result.output
        assert 'class="cat"' in out and "initCatalogue(" in out
        assert 'class="csearch"' in out
        assert 'data-type="rules"' in out  # chips + rules row present
        assert 'data-maint="1"' in out  # demo-skill row flagged maintainer-only
        assert '<code class="path"' in out
        assert "_maint" in out  # the maintainer toggle renders when relevant

    def test_catalogue_graph_clusters_by_type(self, tmp_path: Path) -> None:
        # agents / skills / rules each fold into a compound parent so the graph
        # reads as grouped boxes instead of one flat node cloud
        _make_assets_project(tmp_path)
        out = _viz(tmp_path, "assets", "--html").output
        assert '"parent": "cluster_skill"' in out
        assert '"id": "cluster_skill"' in out  # the compound parent node itself
        assert '"id": "cluster_agent"' in out

    def _shrink_meta_threshold(self, tmp_path: Path, value: int) -> None:
        cf = tmp_path / ".cataforge" / "framework.json"
        data = json.loads(cf.read_text(encoding="utf-8"))
        data.setdefault("constants", {})["META_DOC_SPLIT_THRESHOLD_LINES"] = value
        cf.write_text(json.dumps(data), encoding="utf-8")

    def test_oversized_asset_flagged_in_data(self, tmp_path: Path) -> None:
        _make_assets_project(tmp_path)
        self._shrink_meta_threshold(tmp_path, 3)  # fixture files exceed 3 lines
        data = _assets_json_nodes(tmp_path)["skill_demo_skill"]["data"]
        assert data["lines_warn"] is True

    def test_within_threshold_asset_not_flagged(self, tmp_path: Path) -> None:
        _make_assets_project(tmp_path)  # default threshold 500 → fixtures are small
        data = _assets_json_nodes(tmp_path)["skill_demo_skill"]["data"]
        assert data["lines_warn"] is False

    def test_oversized_asset_warn_column_in_html(self, tmp_path: Path) -> None:
        _make_assets_project(tmp_path)
        self._shrink_meta_threshold(tmp_path, 3)
        out = _viz(tmp_path, "assets", "--html").output
        assert 'class="num vwarn"' in out  # the oversized lines cell carries the flag

    def test_assets_json_declares_catalogue_form(self, tmp_path: Path) -> None:
        # the collector states the presentation intent — renderers never sniff it
        _make_project(tmp_path)
        result = _viz(tmp_path, "assets", "--format", "json")
        assert result.exit_code == 0, result.output
        assert json.loads(result.output)["form"] == "catalogue"

    def test_asset_nodes_typed_not_statused(self, tmp_path: Path) -> None:
        # agent/skill is a kind, not a health state — colour rides the type
        # channel and the status field stays reserved for anomalies
        _make_project(tmp_path)
        result = _viz(tmp_path, "assets", "--format", "json")
        nodes = {n["id"]: n for n in json.loads(result.output)["nodes"]}
        assert nodes["agent_product_manager"]["status"] is None
        assert nodes["skill_research"]["status"] is None


# ------------------------------------------------------------------
# HTML renderer (tier 2) — self-contained offline output
# ------------------------------------------------------------------


def _assert_offline(html_text: str) -> None:
    """No external resource references — the page must open with no network."""
    assert "<script src" not in html_text
    assert "<link " not in html_text
    assert not re.search(r'(?:src|href)\s*=\s*["\']https?://', html_text)


_HTML_GRAPH = Graph(
    title="g",
    nodes=(Node("a", label="Alpha"), Node("b", label="Beta", status=Status.MISSING)),
    edges=(Edge("a", "b", label="rel"),),
)
_HINT_GRAPH = Graph(
    title="docs",
    nodes=(
        Node("a", label="Alpha"),
        Node(
            "b",
            label="Beta",
            status=Status.PARTIAL,
            data={"issue": "stale", "hint": "run: cataforge context reconcile"},
        ),
    ),
    edges=(Edge("a", "b", label="stale"),),
)
_HTML_TL = Timeline(title="t", events=(TimelineEvent("2026-01-01T00:00:00", "ev", "cat"),))
_HTML_MS = MetricSeries(title="m", points=(MetricPoint("F-001", 1.0, "impl"),))


class TestHtmlRenderer:
    def test_vendored_assets_resolve(self) -> None:
        cy = html._read_asset("cytoscape.min.js")
        ec = html._read_asset("echarts.min.js")
        assert "Cytoscape Consortium" in cy and len(cy) > 100_000
        assert "Apache Software Foundation" in ec and len(ec) > 500_000

    def test_graph_inlines_cytoscape_only(self) -> None:
        out = html.render(_HTML_GRAPH)
        assert "Cytoscape Consortium" in out
        assert "Apache Software Foundation" not in out
        assert "initGraph('view0'" in out
        _assert_offline(out)

    def test_graph_node_status_maps_to_data(self) -> None:
        out = html.render(_HTML_GRAPH)
        enc = palette.encoding(Status.MISSING)
        assert f'"bg": "{enc.fill}"' in out
        assert f'"border": "{enc.stroke}"' in out
        assert f'"label": "{enc.marker} Beta"' in out  # textual channel

    def test_graph_has_search_box(self) -> None:
        assert 'class="search"' in html.render(_HTML_GRAPH)

    def test_edged_graph_projects_node_tooltip(self) -> None:
        # a data-bearing (but non-catalogue) node hovers a details-on-demand
        # card: status + gap + the ``run:`` remediation, wired via the tip field
        out = html.render(_HINT_GRAPH)
        assert "initGraph('view0'" in out  # plain zoomable graph, not a catalogue
        assert 'class="cat"' not in out
        assert '"tip":' in out
        assert "run: cataforge context reconcile" in out
        assert "d.className = 'viztip'" in out  # hover-card element wired into initGraph

    def test_node_without_data_or_status_has_no_tip(self) -> None:
        plain = Graph(nodes=(Node("a", label="A"), Node("b", label="B")), edges=(Edge("a", "b"),))
        assert '"tip":' not in html.render(plain)

    def test_typed_node_colored_without_status(self) -> None:
        g = Graph(
            title="fw",
            nodes=(Node("a", label="A", data={"type": "agent"}), Node("b", label="B")),
            edges=(Edge("a", "b"),),
        )
        out = html.render(g)
        enc = palette.TYPE_ENCODINGS["agent"]
        assert f'"bg": "{enc.fill}"' in out
        assert f'"border": "{enc.stroke}"' in out
        assert "initGraph('view0'" in out  # typed nodes alone do not make a catalogue
        assert '"parent": "cluster_' not in out  # nor do they cluster outside the catalogue form

    def test_status_takes_precedence_over_type(self) -> None:
        g = Graph(
            title="fw",
            nodes=(
                Node("a", label="A", status=Status.MISSING, data={"type": "agent"}),
                Node("b", label="B"),
            ),
            edges=(Edge("a", "b"),),
        )
        out = html.render(g)
        assert f'"bg": "{palette.encoding(Status.MISSING).fill}"' in out
        assert f'"bg": "{palette.TYPE_ENCODINGS["agent"].fill}"' not in out

    def test_catalogue_form_is_explicit(self) -> None:
        nodes = (Node("a", label="A", data={"type": "agent", "name": "a", "path": "x"}),)
        edges = (Edge("a", "a"),)
        assert "initCatalogue('view0'" not in html.render(
            Graph(title="g", nodes=nodes, edges=edges)
        )
        assert "initCatalogue('view0'" in html.render(
            Graph(title="g", nodes=nodes, edges=edges, form="catalogue")
        )

    def test_graph_direction_passed_to_layout(self) -> None:
        g = Graph(
            title="chain",
            direction="LR",
            nodes=(Node("a", label="A"), Node("b", label="B")),
            edges=(Edge("a", "b"),),
        )
        out = html.render(g)
        assert '{"dir": "LR"}' in out
        assert "opts.dir" in out  # the transpose branch ships with the page

    def test_timeline_uses_time_axis(self) -> None:
        # real time distances — a 2-day gap must not render as wide as a 2-week one
        out = html.render(_HTML_TL)
        assert '"type": "time"' in out

    def test_timeline_scatter_series_named(self) -> None:
        out = html.render(_HTML_TL)
        assert '"name": "t"' in out  # series carries the view title

    def test_dark_scheme_supported(self) -> None:
        out = html.render(_HTML_GRAPH)
        assert "prefers-color-scheme: dark" in out  # chrome flips via media query
        out_chart = html.render(_HTML_TL)
        assert "matchMedia" in out_chart  # charts pick the echarts dark theme

    def test_node_data_bag_projected_for_inspector(self) -> None:
        # the full data bag travels with the element, so the side inspector can
        # project every field without a second lookup
        out = html.render(_HINT_GRAPH)
        assert '"meta": {"issue": "stale"' in out

    def test_graph_offers_table_mode(self) -> None:
        # every cytoscape view carries an equivalent table: screen readers, huge
        # graphs and table preference all get a degradation path
        out = html.render(_HTML_GRAPH)
        assert 'class="modeswitch"' in out
        assert 'class="alt-table"' in out
        assert "initFilterTable('view0');" in out

    def test_chart_views_offer_table_mode(self) -> None:
        # timeline / metric charts carry an equivalent data table + a text
        # summary — the canvas is never the only representation
        out = html.render(_HTML_TL)
        assert 'class="modeswitch"' in out
        assert 'class="alt-table" hidden' in out
        assert "initChartMode('view0');" in out

    def test_catalogue_has_table_graph_mode_switch(self) -> None:
        # catalogue defaults to the table; the graph is a full-height mode away
        g = Graph(
            title="assets",
            form="catalogue",
            nodes=(Node("a", data={"type": "skill", "name": "a"}),),
            edges=(),
        )
        out = html.render(g)
        assert 'class="modeswitch"' in out
        assert ">拓扑视图</button>" in out  # default label = switch-to-graph
        assert 'id="view0_gwrap" class="gwrap" hidden' in out  # graph starts hidden (table default)

    def test_catalogue_graph_offers_neighborhood_focus(self) -> None:
        # a dense catalogue graph is unreadable whole; the topology acts as a
        # neighborhood explorer — tap keeps one node + direct deps, and the
        # exit control (hidden until focused) restores the full graph
        g = Graph(
            title="assets",
            form="catalogue",
            nodes=(
                Node("a", data={"type": "agent", "name": "a"}),
                Node("s", data={"type": "skill", "name": "s"}),
            ),
            edges=(Edge("a", "s"),),
        )
        out = html.render(g)
        assert 'id="view0_unfocus"' in out
        assert "hidden>显示全图</button>" in out  # exit control hidden until focused

    def test_catalogue_focus_wiring_is_exitable_and_persisted(self) -> None:
        js = html._dashboard_js()
        assert "closedNeighborhood" in js  # focus = tapped node + direct deps
        assert ":fnode" in js  # focus survives reload like every other view state
        assert "offstage" in js  # out-of-neighborhood elements hide, not dim
        assert "laidOut" in js  # hidden-init layout re-runs at real size on first show

    def test_typed_graph_grows_layer_fold_chips(self) -> None:
        # type layers fold via count-badged chips — a hundreds-of-nodes trace
        # survives by hiding whole layers
        g = Graph(
            title="fw",
            nodes=(
                Node("a", label="A", data={"type": "agent"}),
                Node("b", label="B", data={"type": "agent"}),
                Node("c", label="C", data={"type": "skill"}),
            ),
            edges=(Edge("a", "c"),),
        )
        out = html.render(g)
        assert 'data-type="agent"' in out and "agent (2)" in out
        assert 'data-type="skill"' in out and "skill (1)" in out

    def test_untyped_graph_has_no_fold_chips(self) -> None:
        out = html.render(_HTML_GRAPH)
        assert 'class="fchip on" data-type=' not in out

    def test_status_table_toolbar_above_threshold(self) -> None:
        # >8 rows → the table grows a search + status-chip toolbar
        many = Graph(
            title="s",
            nodes=tuple(
                Node(f"n{i}", label=f"N{i}", status=Status.OK if i % 2 else Status.PARTIAL)
                for i in range(9)
            ),
        )
        out = html.render(many)
        assert 'id="view0_q"' in out
        assert 'class="fchip on" data-status="ok"' in out
        assert "initFilterTable('view0');" in out

    def test_status_table_small_exempt_from_toolbar(self) -> None:
        few = Graph(title="s", nodes=(Node("a", label="A", status=Status.OK),))
        out = html.render(few)
        assert 'id="view0_q"' not in out
        # the constituency bar still filters by click
        assert "initFilterTable('view0');" in out
        assert 'class="seg" data-status="ok"' in out

    def test_timeline_inlines_echarts_only(self) -> None:
        out = html.render(_HTML_TL)
        assert "Apache Software Foundation" in out
        assert "Cytoscape Consortium" not in out
        assert "initChart('view0'" in out
        _assert_offline(out)

    def test_timeline_count_scales_symbol_and_names_point(self) -> None:
        t = Timeline(
            title="t",
            events=(
                TimelineEvent("2026-01-01", "burst", "cat", count=9),
                TimelineEvent("2026-01-02", "single", "cat"),
            ),
        )
        out = html.render(t)
        assert '"name": "burst ×9"' in out
        assert '"name": "single"' in out
        sizes = [int(m) for m in re.findall(r'"symbolSize": (\d+)', out)]
        assert len(sizes) == 2
        assert max(sizes) > min(sizes)  # count drives point size

    def test_metrics_inlines_echarts(self) -> None:
        out = html.render(_HTML_MS)
        assert "Apache Software Foundation" in out
        assert "initChart('view0'" in out
        _assert_offline(out)

    def test_timeline_has_datazoom(self) -> None:
        # a long event log is scannable: a brushable x-axis window
        out = html.render(_HTML_TL)
        assert '"dataZoom"' in out
        assert '"slider"' in out


_EDGELESS_STATUS_GRAPH = Graph(
    title="coverage",
    nodes=(
        Node("F-001", label="F-001: done", status=Status.OK),
        Node("F-002", label="F-002: gap", status=Status.MISSING),
        Node("F-003", label="F-003: partial", status=Status.PARTIAL),
    ),
)


class TestStatusTableFallback:
    def test_edgeless_status_graph_renders_table_not_graph(self) -> None:
        out = html.render(_EDGELESS_STATUS_GRAPH)
        assert 'class="stat"' in out  # status table present
        assert "initGraph('view0'" not in out  # no node-rain graph init call
        assert 'class="cy"' not in out

    def test_edgeless_status_graph_needs_no_cytoscape(self) -> None:
        # a table-only page must not inline the graph library
        out = html.render(_EDGELESS_STATUS_GRAPH)
        assert "Cytoscape Consortium" not in out
        _assert_offline(out)

    def test_status_table_sorts_anomalies_first(self) -> None:
        out = html.render(_EDGELESS_STATUS_GRAPH)
        # MISSING row precedes PARTIAL precedes OK
        assert out.index("F-002") < out.index("F-003") < out.index("F-001")

    def test_status_table_has_constituency_bar(self) -> None:
        out = html.render(_EDGELESS_STATUS_GRAPH)
        assert 'class="cbar"' in out
        # one segment per present status, coloured from the palette
        assert palette.encoding(Status.MISSING).fill in out

    def test_edged_graph_still_renders_cytoscape(self) -> None:
        out = html.render(_HTML_GRAPH)  # has an a→b edge
        assert "initGraph('view0'" in out  # graph stays the primary mode
        # the equivalent status table exists only as the hidden alt mode
        assert out.index('class="alt-table" hidden') < out.index('class="stat"')

    def test_hint_bearing_edgeless_graph_is_table_not_catalogue(self) -> None:
        # a coverage/docs node's data bag holds only a remediation hint (no
        # ``type``) → it must not be mistaken for the asset catalogue
        g = Graph(
            title="coverage",
            nodes=(
                Node("F-001", label="F-001: done", status=Status.OK),
                Node(
                    "F-002",
                    label="F-002: gap",
                    status=Status.MISSING,
                    data={"issue": "缺实现与测试", "hint": "run: cataforge viz trace F-002"},
                ),
            ),
        )
        out = html.render(g)
        assert 'class="stat"' in out  # status table
        assert "initCatalogue('view0'" not in out  # not rendered as the asset catalogue
        assert 'class="cat-view"' not in out
        # the remediation outlet rides into the table row
        assert 'class="rhint"' in out
        assert "run: cataforge viz trace F-002" in out


def _make_dashboard_project(tmp_path: Path) -> Path:
    """Framework + agent (graphs) plus EVENT-LOG / CORRECTIONS (charts); KG,
    doc-index, instruction file all absent so several views degrade. A second
    agent shares the skill so the assets graph has a strict-subset
    neighborhood (needed to observe neighborhood focus)."""
    _make_project(tmp_path)
    rv = tmp_path / ".cataforge" / "agents" / "reviewer"
    rv.mkdir(parents=True)
    (rv / "AGENT.md").write_text("---\nskills: [research]\n---\nbody\n")
    docs = tmp_path / "docs"
    docs.mkdir(exist_ok=True)
    rec = {"ts": "2026-01-01T00:00:00+00:00", "event": "phase_start", "phase": "requirements"}
    (docs / "EVENT-LOG.jsonl").write_text(json.dumps(rec) + "\n", encoding="utf-8")
    reviews = docs / "reviews"
    reviews.mkdir()
    (reviews / "CORRECTIONS-LOG.md").write_text(
        "# C\n\n### 2026-01-01 | reviewer | development\n- 偏差类型: preference\n",
        encoding="utf-8",
    )
    return tmp_path


class TestDashboard:
    def test_aggregates_graph_and_chart_libs(self, tmp_path: Path) -> None:
        _make_dashboard_project(tmp_path)
        out = html.render_dashboard(tmp_path)
        assert "Cytoscape Consortium" in out  # framework / assets graphs
        assert "Apache Software Foundation" in out  # timeline / decay charts
        _assert_offline(out)

    def test_one_tab_per_view(self, tmp_path: Path) -> None:
        _make_dashboard_project(tmp_path)
        out = html.render_dashboard(tmp_path)
        for label in ("编排", "资产", "时间线", "腐化"):
            assert f">{label}<" in out
        # every tab keeps its CLI view name reachable via title=
        for name in ("framework", "assets", "timeline", "decay"):
            assert f'title="{name}"' in out
        assert 'data-panel="panel-phase"' not in out  # phase lives in the stepper
        assert out.count('<button class="tab') == 9

    def test_failed_views_degrade_to_error_panel(self, tmp_path: Path) -> None:
        # a structurally broken source (unparseable doc-index) degrades to an
        # inline error panel instead of failing the whole dashboard
        _make_dashboard_project(tmp_path)
        (tmp_path / "docs" / ".doc-index.json").write_text("{not json", encoding="utf-8")
        out = html.render_dashboard(tmp_path)
        assert 'class="error"' in out

    def test_cli_dashboard_writes_html(self, tmp_path: Path) -> None:
        _make_dashboard_project(tmp_path)
        out_file = tmp_path / "db.html"
        result = _viz(tmp_path, "dashboard", "-o", str(out_file))
        assert result.exit_code == 0, result.output
        assert "<!DOCTYPE html>" in out_file.read_text(encoding="utf-8")

    def test_kpi_strip_first_with_degraded_hints(self, tmp_path: Path) -> None:
        # no KG / doc-index → the coverage & docs tiles degrade to run-hints
        _make_dashboard_project(tmp_path)
        out = html.render_dashboard(tmp_path)
        assert out.index('class="kpis"') < out.index('class="tabs"')
        assert "run: cataforge kg init" in out
        assert "run: cataforge context index" in out
        assert out.count('<button class="kpi ') == 4
        assert out.count('<button class="tab') == 9  # the strip adds no tab

    def test_stepper_shows_phase_and_gate(self, tmp_path: Path) -> None:
        _make_phase_project(tmp_path, "development", phase_start="development")
        out = html.render_dashboard(tmp_path)
        assert 'class="stepper"' in out
        assert 'pchip cur">development' in out
        assert "门禁通过" in out
        assert "<details" not in out  # gate details only surface when blocked

    def test_stepper_na_for_non_driven_project(self, tmp_path: Path) -> None:
        # instruction file present but 当前阶段 unfilled → N/A strip, not a red
        # 门禁受阻 false alarm
        _make_phase_project(tmp_path, "{a|b|c}")
        out = html.render_dashboard(tmp_path)
        assert "门禁受阻" not in out
        assert "不适用" in out
        assert 'pchip na"' in out

    def test_stepper_blocked_gate_expands_details(self, tmp_path: Path) -> None:
        # requirements has doc gates and nothing satisfied → the current chip
        # flags blocked and the gate checklist is expanded by default
        _make_phase_project(tmp_path, "requirements")
        out = html.render_dashboard(tmp_path)
        assert "门禁受阻" in out
        assert '<details class="gates" open>' in out
        assert "phase_start logged" in out  # a failed check's label is listed
        assert 'pchip cur blocked">requirements' in out

    def test_stepper_carries_compact_phase_indicator(self, tmp_path: Path) -> None:
        # narrow viewports collapse the chip chain to the current chip plus a
        # 阶段 i/N counter (visibility switched in CSS)
        _make_phase_project(tmp_path, "development", phase_start="development")
        out = html.render_dashboard(tmp_path)
        assert re.search(r'<span class="pcompact">阶段 \d+/\d+</span>', out)

    def test_stepper_mode_aware_chip_count(self, tmp_path: Path) -> None:
        _make_phase_project(tmp_path, "planning", mode="agile-lite")
        out = html.render_dashboard(tmp_path)
        assert out.count('class="pchip') == 2  # agile-lite runs a 2-phase sequence

    def test_stepper_survives_phase_outside_mode_sequence(self, tmp_path: Path) -> None:
        # a recognised phase absent from the declared mode's own backbone
        # (mid-project mode switch / hand-edited instruction file) must render,
        # not crash the whole dashboard
        _make_phase_project(tmp_path, "architecture", mode="agile-lite")
        out = html.render_dashboard(tmp_path)
        # appended as the current chip (blocked: no arch doc gates satisfied)
        assert 'pchip cur blocked">architecture' in out

    def test_sdlc_na_propagates_to_kg_views(self, tmp_path: Path) -> None:
        # a non-driven project gets 不适用 guidance in the SDLC-gated views
        # instead of a misleading kg-init run-hint, and their tabs grey out
        _make_phase_project(tmp_path, "{a|b|c}")
        out = html.render_dashboard(tmp_path)
        assert "run: <code>cataforge kg init</code>" not in out
        assert out.count("SDLC 数据管线对本项目不适用") == 4  # trace/coverage/arch/tasks
        assert out.count('class="tab na"') == 4
        # docs is not SDLC-gated: its run-hint guidance stays
        assert "run: <code>cataforge context index</code>" in out

    def test_kpi_tiles_carry_explanations(self, tmp_path: Path) -> None:
        _make_dashboard_project(tmp_path)
        out = html.render_dashboard(tmp_path)
        tiles = out.split('<button class="kpi ')[1:]
        assert len(tiles) == 4
        for tile in tiles:  # metric meaning + threshold provenance on every tile
            assert 'title="' in tile.split(">", 1)[0]
        assert "RETRO_TRIGGER_SELF_CAUSED" in out  # decay threshold provenance

    def test_links_tile_presets_docs_filter(self, tmp_path: Path) -> None:
        # tapping the broken-links tile lands on docs with anomalies isolated
        _make_docs_project(tmp_path)
        out = html.render_dashboard(tmp_path)
        assert 'data-filter="anomaly"' in out
        assert "filterAnomalies" in out

    def test_legend_present(self, tmp_path: Path) -> None:
        _make_dashboard_project(tmp_path)
        out = html.render_dashboard(tmp_path)
        assert 'class="legend"' in out
        for hexv, label in palette.LEGEND:
            assert hexv in out and label in out

    def _panel_id(self, name: str) -> str:
        return f"panel-{name}"

    def test_omnibox_in_header(self, tmp_path: Path) -> None:
        # one global search: any entity id/label → jump to its tab and focus it
        _make_dashboard_project(tmp_path)
        out = html.render_dashboard(tmp_path)
        assert 'id="omni"' in out
        assert "__viz.setIndex(" in out
        assert "window.__viz.focus = function" in out

    def test_omnibox_index_maps_entities_to_panels(self, tmp_path: Path) -> None:
        # every graph/table panel's entities are findable: id + label + panel
        _make_kg_project(tmp_path)
        out = html.render_dashboard(tmp_path)
        idx = out.index("__viz.setIndex(")
        assert '"p": "panel-coverage"' in out[idx:]
        assert '"p": "panel-trace"' in out[idx:]

    def test_cross_links_replaced_by_generic_navigation(self, tmp_path: Path) -> None:
        # the two hard-coded cross-view pairs are gone — navigation flows
        # through the omnibox index and the inspector's cross-appearance links
        _make_kg_tasks_project(tmp_path)
        out = html.render_dashboard(tmp_path)
        assert "linkGraph('" not in out and "linkTable('" not in out
        assert not hasattr(html, "_CROSS_LINKS")

    def test_inspector_shell_present(self, tmp_path: Path) -> None:
        # tapping a node pins its full detail into a side inspector; the hover
        # tooltip stays as the lightweight preview
        _make_dashboard_project(tmp_path)
        out = html.render_dashboard(tmp_path)
        assert 'id="inspector"' in out
        assert "__viz.inspect =" in out

    def test_degraded_panel_reuses_status_guidance(self, tmp_path: Path) -> None:
        _make_dashboard_project(tmp_path)
        out = html.render_dashboard(tmp_path)
        assert "此视图需要的数据还未生成" in out
        assert "run: <code>cataforge kg init</code>" in out
        assert "run: <code>cataforge context index</code>" in out

    def test_empty_views_show_guidance(self, tmp_path: Path) -> None:
        _make_project(tmp_path)  # no EVENT-LOG / CORRECTIONS → both views empty
        out = html.render_dashboard(tmp_path)
        assert "暂无事件" in out
        assert "暂无纠偏记录" in out

    def test_empty_tasks_panel_shows_guidance(self, tmp_path: Path) -> None:
        _make_kg_project(tmp_path)  # KG present, no Task entities → tasks EMPTY
        out = html.render_dashboard(tmp_path)
        assert "暂无任务依赖" in out

    def _write_corrections(self, tmp_path: Path, body: str) -> None:
        reviews = tmp_path / "docs" / "reviews"
        reviews.mkdir(parents=True, exist_ok=True)
        (reviews / "CORRECTIONS-LOG.md").write_text(f"# C\n\n{body}", encoding="utf-8")

    def _set_constant(self, tmp_path: Path, name: str, value: int) -> None:
        cf = tmp_path / ".cataforge" / "framework.json"
        data = json.loads(cf.read_text(encoding="utf-8"))
        data.setdefault("constants", {})[name] = value
        cf.write_text(json.dumps(data), encoding="utf-8")

    def test_decay_tile_threshold_read_from_framework_json(self, tmp_path: Path) -> None:
        # the retro line is not hardcoded: overriding the framework.json constant
        # moves the denominator the decay tile shows
        _make_project(tmp_path)
        self._set_constant(tmp_path, "RETRO_TRIGGER_SELF_CAUSED", 2)
        self._write_corrections(
            tmp_path, "### 2026-01-01 | reviewer | development\n- 偏差类型: self-caused\n"
        )
        out = html.render_dashboard(tmp_path)
        assert "1/2" in out  # 1 self-caused over the overridden threshold 2
        assert "self-caused → retro" in out

    def test_decay_tile_default_threshold_is_five(self, tmp_path: Path) -> None:
        _make_project(tmp_path)  # no constants override → framework default 5
        self._write_corrections(
            tmp_path, "### 2026-01-01 | reviewer | development\n- 偏差类型: self-caused\n"
        )
        out = html.render_dashboard(tmp_path)
        assert "1/5" in out

    def test_decay_tile_goes_bad_at_threshold(self, tmp_path: Path) -> None:
        _make_project(tmp_path)
        self._set_constant(tmp_path, "RETRO_TRIGGER_SELF_CAUSED", 2)
        self._write_corrections(
            tmp_path,
            "### 2026-01-01 | reviewer | development\n- 偏差类型: self-caused\n\n"
            "### 2026-01-02 | reviewer | development\n- 偏差类型: self-caused\n",
        )
        out = html.render_dashboard(tmp_path)
        assert "2/2" in out
        # the decay tile (last of the 5) carries the bad accent once the line is hit
        assert out.rindex('<button class="kpi bad"') > out.index('class="kpis"')

    def test_decay_tile_month_over_month_arrow(self, tmp_path: Path) -> None:
        _make_project(tmp_path)
        self._write_corrections(
            tmp_path,
            "### 2026-01-01 | reviewer | development\n- 偏差类型: preference\n\n"
            "### 2026-02-01 | reviewer | development\n- 偏差类型: preference\n\n"
            "### 2026-02-02 | reviewer | development\n- 偏差类型: preference\n",
        )
        out = html.render_dashboard(tmp_path)
        assert "环比↑" in out  # Feb (2) exceeds Jan (1)

    def test_coverage_tile_shows_gap_to_target(self, tmp_path: Path) -> None:
        _make_kg_project(tmp_path)  # both Features partial → full 0 / total 2
        out = html.render_dashboard(tmp_path)
        assert "缺口 2 → 100%" in out

    def test_tabs_grouped_by_domain(self, tmp_path: Path) -> None:
        _make_dashboard_project(tmp_path)
        out = html.render_dashboard(tmp_path)
        assert 'class="tabgroup"' in out
        assert "项目交付" in out and "文档与过程" in out and "框架资产" in out
        # one labelled tablist per group; the group label sits outside the
        # tablist so its only children are tabs (ARIA required-children)
        assert out.count('<div class="tabrow" role="tablist"') == 3
        assert out.count('aria-labelledby="tg-') == 3
        assert out.count('<button class="tab') == 9  # every view still has a tab

    def test_default_tab_follows_worst_kpi(self, tmp_path: Path) -> None:
        # a stale + xref doc-index makes the links KPI red → the docs tab opens
        # first, instead of the (index-0) framework tab
        _make_docs_project(tmp_path)
        out = html.render_dashboard(tmp_path)
        assert f'id="{self._panel_id("docs")}" class="panel active"' in out
        assert 'id="panel-framework" class="panel active"' not in out  # framework not default

    def test_default_tab_first_health_view_when_all_ok(self, tmp_path: Path) -> None:
        # no red/amber KPI, but a health view (timeline) has data → open it, never
        # leaving the framework tab as an arbitrary default
        _make_dashboard_project(tmp_path)
        out = html.render_dashboard(tmp_path)
        assert f'id="{self._panel_id("timeline")}" class="panel active"' in out
        assert 'id="panel-framework" class="panel active"' not in out

    def test_panels_use_named_ids(self, tmp_path: Path) -> None:
        # panel anchors are view names, not positional indexes: reordering or
        # removing a view never shifts every other panel's id
        _make_dashboard_project(tmp_path)
        out = html.render_dashboard(tmp_path)
        assert 'id="panel-framework"' in out
        assert 'id="panel-timeline"' in out
        assert 'id="panel0"' not in out

    def test_panel_inits_registered_for_lazy_activation(self, tmp_path: Path) -> None:
        # inits queue behind __viz.register(pid, fn); showPanel flushes a
        # panel's queue on first activation, so load renders one panel only
        _make_dashboard_project(tmp_path)
        out = html.render_dashboard(tmp_path)
        assert "__viz.register('panel-framework', function(){" in out
        assert "__viz.register('panel-timeline', function(){" in out
        reg = out.index("__viz.register('panel-framework'")
        assert reg < out.index("initGraph('panel-framework_v'")

    def test_tabs_carry_aria_roles(self, tmp_path: Path) -> None:
        _make_dashboard_project(tmp_path)
        out = html.render_dashboard(tmp_path)
        assert 'role="tablist"' in out
        assert out.count('role="tab" aria-selected') == 9
        assert out.count('aria-selected="true"') == 1
        assert out.count('role="tabpanel"') == 9
        # tab ↔ panel wiring: ids, aria-controls, aria-labelledby all pair up
        for name, _label in html._DASHBOARD_VIEWS:
            assert f'id="tab-{name}"' in out
            assert f'aria-controls="panel-{name}"' in out
            assert f'aria-labelledby="tab-{name}"' in out
        # roving tabindex: exactly the selected tab is tabbable at render time
        assert out.count('role="tab" aria-selected="true"') == 1
        assert 'aria-selected="true" aria-controls' in out

    def test_tab_keyboard_model_wired(self, tmp_path: Path) -> None:
        _make_dashboard_project(tmp_path)
        out = html.render_dashboard(tmp_path)
        assert "ArrowRight" in out and "ArrowLeft" in out
        assert "'Home'" in out and "'End'" in out
        assert "syncTablists" in out

    def test_omnibox_is_combobox(self, tmp_path: Path) -> None:
        _make_dashboard_project(tmp_path)
        out = html.render_dashboard(tmp_path)
        assert 'role="combobox"' in out
        assert 'aria-expanded="false"' in out
        assert 'aria-controls="omni_list"' in out
        assert 'role="listbox"' in out
        assert 'id="omni_status"' in out and 'aria-live="polite"' in out
        assert "无匹配实体" in out  # zero-hit feedback text
        assert "aria-activedescendant" in out

    def test_inspector_is_focus_managed_dialog(self, tmp_path: Path) -> None:
        _make_dashboard_project(tmp_path)
        out = html.render_dashboard(tmp_path)
        assert 'id="inspector" role="dialog"' in out
        assert 'aria-label="实体详情"' in out
        assert 'tabindex="-1"' in out
        assert "closeInspector" in out
        assert "'Escape'" in out

    def test_document_structure_landmarks(self, tmp_path: Path) -> None:
        _make_dashboard_project(tmp_path)
        out = html.render_dashboard(tmp_path)
        assert '<html lang="zh-CN">' in out
        assert out.count("<h1>") == 1
        assert "<main>" in out and "</main>" in out

    def test_sdlc_na_project_gets_consistent_guidance(self, tmp_path: Path) -> None:
        # a non-workflow-driven project: SDLC-gated tiles and tabs both say
        # N/A instead of steering toward kg-init commands that don't apply
        _make_project(tmp_path)
        (tmp_path / "CLAUDE.md").write_text(
            "# P\n## 项目状态\n- 当前阶段: none\n", encoding="utf-8"
        )
        out = html.render_dashboard(tmp_path)
        assert "SDLC 数据管线对本项目不适用" in out
        assert 'class="nabadge"' in out
        assert "核心文档 · SDLC 不适用" in out
        assert "Feature 覆盖 · SDLC 不适用" in out
        # the links tile still guides toward the doc index (not SDLC-gated)
        assert "断链 / stale · run: cataforge context index" in out

    def test_active_tab_enters_url_hash(self, tmp_path: Path) -> None:
        # tab switches record #panel-{name}; load replays a valid hash → the
        # dashboard is deep-linkable per view
        _make_dashboard_project(tmp_path)
        out = html.render_dashboard(tmp_path)
        assert "history.replaceState" in out
        assert "location.hash" in out
        assert "addEventListener('hashchange'" in out  # manual hash edits / back-forward

    def test_ui_state_persisted_to_local_storage(self, tmp_path: Path) -> None:
        # filters / sort / viewport survive a reload (serve-mode regenerate)
        _make_dashboard_project(tmp_path)
        out = html.render_dashboard(tmp_path)
        assert "localStorage.setItem" in out
        assert "cataforge-viz:" in out
        # a corrupted persisted value must not crash a panel's init
        assert "__viz.stateArr" in out

    def test_focus_row_lookup_never_builds_dynamic_selector(self, tmp_path: Path) -> None:
        # entity ids are data, not selector syntax: a quote in an id must not
        # throw a DOMException out of __viz.focus
        _make_dashboard_project(tmp_path)
        out = html.render_dashboard(tmp_path)
        assert "'tr[data-node=\"'+nid" not in out

    def test_window_resize_handler_debounced(self, tmp_path: Path) -> None:
        _make_dashboard_project(tmp_path)
        out = html.render_dashboard(tmp_path)
        assert "addEventListener('resize'" in out
        assert "setTimeout" in out


class TestVizSnapshot:
    def test_snapshot_appends_jsonl(self, tmp_path: Path) -> None:
        # each run appends one record: the overview points frozen with a ts
        _make_phase_project(tmp_path, "development", phase_start="development")
        for _ in range(2):
            result = _viz(tmp_path, "snapshot")
            assert result.exit_code == 0, result.output
        lines = (
            (tmp_path / "docs" / "VIZ-SNAPSHOTS.jsonl")
            .read_text(encoding="utf-8")
            .strip()
            .splitlines()
        )
        assert len(lines) == 2
        rec = json.loads(lines[0])
        assert rec["ts"] and isinstance(rec["points"], list)
        assert any(p["series"] == "phase" for p in rec["points"])

    def test_snapshot_read_tolerates_malformed_lines(self, tmp_path: Path) -> None:
        from cataforge.application.viz.snapshots import read_snapshots

        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "VIZ-SNAPSHOTS.jsonl").write_text(
            '{"ts": "2026-01-01T00:00:00", "points": []}\n{oops\n', encoding="utf-8"
        )
        assert len(read_snapshots(tmp_path)) == 1

    def _write_history(self, tmp_path: Path, counts: list[int]) -> None:
        docs = tmp_path / "docs"
        docs.mkdir(exist_ok=True)
        lines = [
            json.dumps(
                {
                    "ts": f"2026-01-0{i + 1}T00:00:00",
                    "points": [{"series": "links", "label": "stale", "value": float(c)}],
                }
            )
            for i, c in enumerate(counts)
        ]
        (docs / "VIZ-SNAPSHOTS.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def test_tiles_grow_sparkline_with_history(self, tmp_path: Path) -> None:
        # ≥2 snapshots → a live tile carries an inline SVG trend line; a
        # degraded (数据未就绪) tile deliberately stays trendless
        _make_docs_project(tmp_path)  # live doc-index → the links tile has data
        _make_dashboard_project(tmp_path)
        self._write_history(tmp_path, [3, 1])
        out = html.render_dashboard(tmp_path)
        assert '<svg class="spark"' in out
        assert "polyline" in out

    def test_no_sparkline_without_history(self, tmp_path: Path) -> None:
        _make_dashboard_project(tmp_path)
        out = html.render_dashboard(tmp_path)
        assert '<svg class="spark"' not in out


class TestVizPortfolio:
    def test_rows_per_project(self, tmp_path: Path) -> None:
        # one row per root: name + stepper + links/decay counts; a driven and a
        # non-driven project aggregate side by side
        driven = tmp_path / "proj-driven"
        driven.mkdir()
        _make_phase_project(driven, "development", phase_start="development")
        idle = tmp_path / "proj-idle"
        idle.mkdir()
        _make_phase_project(idle, "{a|b|c}")
        out_file = tmp_path / "portfolio.html"
        result = CliRunner().invoke(
            cli,
            ["viz", "portfolio", str(driven), str(idle), "-o", str(out_file)],
        )
        assert result.exit_code == 0, result.output
        out = out_file.read_text(encoding="utf-8")
        assert "proj-driven" in out and "proj-idle" in out
        assert out.count('class="stepper"') == 2
        assert 'pchip cur">development' in out  # driven project's current phase
        assert "不适用" in out  # non-driven row says so
        assert "断链" in out and "self-caused" in out

    def test_portfolio_requires_roots(self) -> None:
        result = CliRunner().invoke(cli, ["viz", "portfolio"])
        assert result.exit_code != 0

    def test_one_misconfigured_root_does_not_abort_the_sweep(self, tmp_path: Path) -> None:
        # a root whose 当前阶段 falls outside its mode's sequence still gets a
        # row — the aggregation's whole point is surviving messy projects
        odd = tmp_path / "proj-odd"
        odd.mkdir()
        _make_phase_project(odd, "architecture", mode="agile-lite")
        from cataforge.application.viz.portfolio import render_portfolio

        out = render_portfolio([odd])
        assert "proj-odd" in out


class TestVizHtmlCli:
    def test_single_view_inits_immediately(self, tmp_path: Path) -> None:
        # a single-view page has no tabs: its init runs directly instead of
        # queueing behind a panel registration
        _make_project(tmp_path)
        result = _viz(tmp_path, "framework", "--html")
        assert "initGraph('view0'" in result.output
        assert "__viz.register('panel-" not in result.output
        assert 'id="omni"' not in result.output  # cross-view search needs views

    def test_framework_html_inlines_cytoscape(self, tmp_path: Path) -> None:
        _make_project(tmp_path)
        result = _viz(tmp_path, "framework", "--html")
        assert result.exit_code == 0, result.output
        assert "Cytoscape Consortium" in result.output
        _assert_offline(result.output)

    def test_html_overrides_format(self, tmp_path: Path) -> None:
        _make_project(tmp_path)
        result = _viz(tmp_path, "framework", "--format", "dot", "--html")
        assert result.exit_code == 0, result.output
        assert "<!DOCTYPE html>" in result.output
        assert "digraph G" not in result.output

    def test_assets_html_inlines_cytoscape(self, tmp_path: Path) -> None:
        _make_project(tmp_path)
        result = _viz(tmp_path, "assets", "--html")
        assert result.exit_code == 0, result.output
        assert "Cytoscape Consortium" in result.output


# ------------------------------------------------------------------
# serve (tier 3) — stdlib static server + watch, no third-party deps
# ------------------------------------------------------------------


# A date that cannot appear in the vendored JS — the decay timeline exposes it
# as an ECharts x-axis category, so its presence in index.html proves a rebuild.
_SENTINEL_DATE = "2099-12-31"


def _write_correction(root: Path, date: str = _SENTINEL_DATE) -> None:
    reviews = root / "docs" / "reviews"
    reviews.mkdir(parents=True, exist_ok=True)
    (reviews / "CORRECTIONS-LOG.md").write_text(
        f"# C\n\n### {date} | reviewer | development\n- 偏差类型: preference\n",
        encoding="utf-8",
    )


class TestVizServe:
    def test_serve_help(self) -> None:
        result = CliRunner().invoke(cli, ["viz", "serve", "--help"])
        assert result.exit_code == 0, result.output
        assert "--watch" in result.output

    def test_service_imports_no_third_party(self) -> None:
        """serve must not pull in any non-stdlib runtime dependency."""
        source = Path(service.__file__).read_text(encoding="utf-8")
        roots: set[str] = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                roots.update(n.name.split(".")[0] for n in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                roots.add(node.module.split(".")[0])
        third_party = [r for r in roots if r != "cataforge" and r not in sys.stdlib_module_names]
        assert not third_party, third_party

    def test_regenerate_writes_dashboard_index(self, tmp_path: Path) -> None:
        _make_project(tmp_path)
        serve_dir = tmp_path / "out"
        index = service.regenerate(tmp_path, serve_dir)
        assert index == serve_dir / "index.html"
        text = index.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in text
        _assert_offline(text)

    def test_fingerprint_changes_on_source_write(self, tmp_path: Path) -> None:
        _make_project(tmp_path)
        before = service._fingerprint(tmp_path)
        docs = tmp_path / "docs"
        docs.mkdir(exist_ok=True)
        (docs / "EVENT-LOG.jsonl").write_text(
            '{"ts":"2026-01-01T00:00:00+00:00","event":"phase_start"}\n', encoding="utf-8"
        )
        assert service._fingerprint(tmp_path) != before

    def test_regenerate_if_changed_only_on_change(self, tmp_path: Path) -> None:
        _make_project(tmp_path)
        serve_dir = tmp_path / "out"
        fp = service._fingerprint(tmp_path)
        # unchanged sources → nothing written
        assert service._regenerate_if_changed(tmp_path, serve_dir, fp) == fp
        assert not (serve_dir / "index.html").exists()
        # a watched source changes → index written, fingerprint advances
        _write_correction(tmp_path)
        advanced = service._regenerate_if_changed(tmp_path, serve_dir, fp)
        assert advanced != fp
        assert (serve_dir / "index.html").is_file()

    def test_build_server_serves_file_and_shuts_down(self, tmp_path: Path) -> None:
        serve_dir = tmp_path / "viz"
        serve_dir.mkdir()
        (serve_dir / "index.html").write_text("<html>hello-viz</html>", encoding="utf-8")
        httpd = service._build_server(serve_dir, "127.0.0.1", 0)
        port = httpd.server_address[1]
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/index.html", timeout=5) as resp:
                assert b"hello-viz" in resp.read()
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=5)
        assert not thread.is_alive()  # clean interruption

    def test_regenerate_injects_http_only_autoreload(self, tmp_path: Path) -> None:
        # serve 路径的产物带轮询自刷新脚本（仅 http 协议激活；file:// 双击打开保持惰性）
        _make_project(tmp_path)
        text = service.regenerate(tmp_path, tmp_path / "out").read_text(encoding="utf-8")
        assert 'id="viz-autoreload"' in text
        assert "Last-Modified" in text
        assert "location.protocol.indexOf('http')" in text
        _assert_offline(text)

    def test_static_cli_output_has_no_autoreload(self, tmp_path: Path) -> None:
        _make_project(tmp_path)
        static = html.render_dashboard(tmp_path)
        assert "viz-autoreload" not in static

    def test_dashboard_footer_marks_snapshot_mode(self, tmp_path: Path) -> None:
        _make_project(tmp_path)
        out = html.render_dashboard(tmp_path)
        assert "数据截至" in out  # 生成时间戳
        assert 'id="viewmode">快照模式' in out  # serve 注入脚本会改写为服务模式

    def test_serve_watch_regenerates_and_stops(self, tmp_path: Path) -> None:
        _make_project(tmp_path)
        serve_dir = tmp_path / "out"
        ready = threading.Event()
        stop = threading.Event()
        captured: dict[str, int] = {}

        def on_ready(httpd: object) -> None:
            captured["port"] = httpd.server_address[1]  # type: ignore[attr-defined]
            ready.set()

        worker = threading.Thread(
            target=service.serve,
            args=(tmp_path,),
            kwargs={
                "directory": serve_dir,
                "port": 0,
                "watch": True,
                "poll_interval": 0.05,
                "stop": stop,
                "on_ready": on_ready,
            },
            daemon=True,
        )
        worker.start()
        try:
            assert ready.wait(5)
            index = serve_dir / "index.html"
            assert index.is_file()  # initial render present before any change
            assert _SENTINEL_DATE not in index.read_text(encoding="utf-8")
            # serve the freshly-written index over HTTP
            port = captured["port"]
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/index.html", timeout=5) as resp:
                assert b"<!DOCTYPE html>" in resp.read()
            # mutate a watched source → watcher must regenerate the dashboard
            _write_correction(tmp_path)
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if _SENTINEL_DATE in index.read_text(encoding="utf-8"):
                    break
                time.sleep(0.05)
            assert _SENTINEL_DATE in index.read_text(encoding="utf-8")
        finally:
            stop.set()
            worker.join(timeout=5)
        assert not worker.is_alive()  # clean shutdown via stop event


# ------------------------------------------------------------------
# UX: status readiness probe + quickstart / --open / help
# ------------------------------------------------------------------


class TestVizStatus:
    def test_probe_all_classifies_states(self, tmp_path: Path) -> None:
        _make_project(tmp_path)  # framework/assets only — no KG / index / log
        by_name = {s.name: s for s in service.probe_all(tmp_path)}
        assert by_name["framework"].state == service.READY
        assert by_name["assets"].state == service.READY
        assert by_name["trace"].state == service.NEEDS_SETUP
        assert "kg init" in by_name["trace"].detail  # raw hint preserved
        assert by_name["docs"].state == service.NEEDS_SETUP
        assert by_name["timeline"].state == service.EMPTY

    def test_status_table_surfaces_setup_commands(self, tmp_path: Path) -> None:
        _make_project(tmp_path)
        result = _viz(tmp_path, "status")
        assert result.exit_code == 0, result.output
        assert "framework" in result.output
        assert "needs setup" in result.output
        # the actionable command is extracted from the collector's own hint
        assert "cataforge kg init" in result.output
        assert "cataforge context index" in result.output

    def test_status_marks_kg_views_ready(self, tmp_path: Path) -> None:
        _make_kg_project(tmp_path)
        by_name = {s.name: s for s in service.probe_all(tmp_path)}
        assert by_name["trace"].state == service.READY
        assert by_name["coverage"].state == service.READY
        assert by_name["arch"].state == service.READY

    def test_status_marks_edgeless_task_graph_empty(self, tmp_path: Path) -> None:
        _make_kg_project(tmp_path)  # Features present, no Task entities
        by_name = {s.name: s for s in service.probe_all(tmp_path)}
        assert by_name["tasks"].state == service.EMPTY


class TestVizDiscovery:
    def test_group_help_has_quickstart_epilog(self) -> None:
        result = CliRunner().invoke(cli, ["viz", "--help"])
        assert result.exit_code == 0, result.output
        assert "quickstart" in result.output.lower()
        assert "status" in result.output.lower()

    def test_file_write_nudges_quickstart(self, tmp_path: Path) -> None:
        _make_project(tmp_path)
        out = tmp_path / "fw.mmd"
        result = _viz(tmp_path, "framework", "-o", str(out))
        assert result.exit_code == 0, result.output
        assert "quickstart" in result.output  # next_steps nudge after -o write

    def test_piped_stdout_stays_clean(self, tmp_path: Path) -> None:
        _make_project(tmp_path)
        result = _viz(tmp_path, "framework")  # no -o → raw diagram on stdout
        assert result.exit_code == 0, result.output
        assert "下一步" not in result.output  # no guidance polluting the diagram


class TestVizOpenAndQuickstart:
    def test_browser_opener_maps_wildcard_host(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from cataforge.interface.cli import viz_cmd

        captured: list[str] = []
        monkeypatch.setattr(viz_cmd.webbrowser, "open", lambda url: captured.append(url) or True)

        class _FakeServer:
            server_address = ("0.0.0.0", 9999)

        viz_cmd._browser_opener("0.0.0.0")(_FakeServer())
        assert captured == ["http://127.0.0.1:9999/"]

    def test_serve_cli_wires_open_and_watch(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from cataforge.interface.cli import viz_cmd

        captured: dict[str, object] = {}
        monkeypatch.setattr(viz_cmd.service, "serve", lambda root, /, **kw: captured.update(kw))
        result = _viz(tmp_path, "serve", "--watch", "--open", "--port", "0")
        assert result.exit_code == 0, result.output
        assert captured["watch"] is True
        assert captured["on_ready"] is not None

    def test_quickstart_forces_watch_and_open(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from cataforge.interface.cli import viz_cmd

        captured: dict[str, object] = {}
        monkeypatch.setattr(viz_cmd.service, "serve", lambda root, /, **kw: captured.update(kw))
        result = _viz(tmp_path, "quickstart", "--port", "0")
        assert result.exit_code == 0, result.output
        assert captured["watch"] is True
        assert captured["on_ready"] is not None

    def test_dashboard_open_writes_default_and_opens(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _make_project(tmp_path)
        from cataforge.interface.cli import viz_cmd

        opened: list[str] = []
        monkeypatch.setattr(viz_cmd.webbrowser, "open", lambda url: opened.append(url) or True)
        result = _viz(tmp_path, "dashboard", "--open")
        assert result.exit_code == 0, result.output
        default = tmp_path / "docs" / "viz" / "dashboard.html"
        assert default.is_file()
        assert opened and opened[0].startswith("file:")
        assert "dashboard.html" in opened[0]


# ------------------------------------------------------------------
# overview view — project-health KPI series
# ------------------------------------------------------------------


def _overview_groups(tmp_path: Path) -> dict[str, dict[str, float]]:
    """Run ``viz overview`` (json is the default) and index points by
    series → label → value."""
    result = _viz(tmp_path, "overview")
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["kind"] == "metrics"
    groups: dict[str, dict[str, float]] = {}
    for point in data["points"]:
        groups.setdefault(point["series"], {})[point["label"]] = point["value"]
    return groups


class TestVizOverview:
    def test_phase_group_tracks_sequence_and_gate(self, tmp_path: Path) -> None:
        _make_phase_project(tmp_path, "development", phase_start="development")
        groups = _overview_groups(tmp_path)
        assert groups["phase"] == {
            "applicable": 1.0,
            "current:development": 3.0,
            "gate_ok": 1.0,
            "total": 3.0,
        }

    def test_unrecognised_phase_marked_not_applicable(self, tmp_path: Path) -> None:
        # a 当前阶段 that is not a known phase → the project isn't workflow-driven
        _make_phase_project(tmp_path, "total")
        groups = _overview_groups(tmp_path)
        assert groups["phase"] == {"applicable": 0.0}

    def test_placeholder_phase_marks_pipeline_not_applicable(self, tmp_path: Path) -> None:
        # instruction file present but 当前阶段 unfilled (a meta project) → N/A,
        # not a blocked-gate false alarm; core-doc completion group is dropped
        _make_phase_project(tmp_path, "{a|b|c}")
        (tmp_path / "docs").mkdir(exist_ok=True)
        (tmp_path / "docs" / ".doc-index.json").write_text(
            json.dumps({"documents": {}}), encoding="utf-8"
        )
        groups = _overview_groups(tmp_path)
        assert groups["phase"] == {"applicable": 0.0}
        assert "docs" not in groups  # SDLC core docs N/A for a non-driven project

    def test_mode_aware_phase_sequence_and_docs(self, tmp_path: Path) -> None:
        # an agile-lite project gates on its own 2-phase sequence, not standard's
        _make_phase_project(tmp_path, "planning", mode="agile-lite")
        groups = _overview_groups(tmp_path)
        assert groups["phase"]["total"] == 2.0  # agile-lite has 2 phases
        assert groups["phase"]["current:planning"] == 1.0

    def test_blocked_gate_reported(self, tmp_path: Path) -> None:
        _make_phase_project(tmp_path, "requirements")  # no prd doc/index → blocked
        groups = _overview_groups(tmp_path)
        assert groups["phase"]["gate_ok"] == 0.0
        assert groups["phase"]["applicable"] == 1.0

    def test_docs_and_links_groups(self, tmp_path: Path) -> None:
        # doc-index has prd/arch/dev-plan drafts, one stale dep, one broken xref
        _make_docs_project(tmp_path)
        cf = tmp_path / ".cataforge"
        cf.mkdir()
        framework = {
            "workflow": {
                "modes": {
                    "standard": {
                        "phases": [
                            {"phase": "requirements", "role": "product-manager"},
                            {"phase": "architecture", "role": "architect"},
                        ]
                    }
                }
            }
        }
        (cf / "framework.json").write_text(json.dumps(framework))
        groups = _overview_groups(tmp_path)
        assert groups["docs"] == {"prd": 0.5, "arch": 0.5}  # present, not approved
        assert groups["links"] == {"stale": 1.0, "xref_error": 1.0}

    def test_coverage_group_matches_kg(self, tmp_path: Path) -> None:
        _make_kg_project(tmp_path)
        cov = _overview_groups(tmp_path)["coverage"]
        result = _viz(tmp_path, "coverage", "--format", "json")
        n_features = len(json.loads(result.output)["nodes"])
        assert cov["full"] + cov["partial"] + cov["none"] == n_features

    def test_decay_group_recent_and_monthly(self, tmp_path: Path) -> None:
        log_dir = tmp_path / "docs" / "reviews"
        log_dir.mkdir(parents=True)
        (log_dir / "CORRECTIONS-LOG.md").write_text(
            "# C\n\n"
            "### 2026-01-01 | reviewer | development\n- 偏差类型: preference\n\n"
            "### 2026-01-02 | architect | architecture\n- 偏差类型: upstream-gap\n",
            encoding="utf-8",
        )
        groups = _overview_groups(tmp_path)
        assert groups["decay"]["2026-01"] == 2.0
        assert groups["decay"]["recent_30d"] == 0.0  # entries far in the past

    def test_decay_group_counts_self_caused_only(self, tmp_path: Path) -> None:
        # the retro gate counts self-caused corrections; preference / upstream-gap
        # entries live in the log but do not push toward a retrospective
        log_dir = tmp_path / "docs" / "reviews"
        log_dir.mkdir(parents=True)
        (log_dir / "CORRECTIONS-LOG.md").write_text(
            "# C\n\n"
            "### 2026-01-01 | reviewer | development\n- 偏差类型: self-caused\n\n"
            "### 2026-01-02 | reviewer | development\n- 偏差类型: self-caused\n\n"
            "### 2026-01-03 | architect | architecture\n- 偏差类型: preference\n",
            encoding="utf-8",
        )
        groups = _overview_groups(tmp_path)
        assert groups["decay"]["self_caused"] == 2.0  # not 3 — preference excluded

    def test_empty_project_is_empty_not_error(self, tmp_path: Path) -> None:
        # every source unreachable → EMPTY, never NEEDS_SETUP; listed first
        first = service.probe_all(tmp_path)[0]
        assert first.name == "overview"
        assert first.state == service.EMPTY

    def test_structurally_damaged_doc_index_tolerated(self, tmp_path: Path) -> None:
        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / ".doc-index.json").write_text(
            json.dumps({"documents": {"x": None}}), encoding="utf-8"
        )
        result = _viz(tmp_path, "overview")
        assert result.exit_code == 0, result.output  # damaged entry skipped, no traceback

    def test_help_notes_json_default(self) -> None:
        result = CliRunner().invoke(cli, ["viz", "overview", "--help"])
        assert result.exit_code == 0, result.output
        assert "json" in result.output


# ------------------------------------------------------------------
# consistency — palette SSOT + dashboard/registry sync + legend
# ------------------------------------------------------------------


class TestVizConsistency:
    def test_collectors_carry_no_inline_hex(self) -> None:
        """Semantic colours live in palette.py only — a collector hardcoding a
        hex drifts out of the shared legend."""
        import cataforge.application.viz.collectors as pkg

        for py in Path(pkg.__file__).parent.glob("*.py"):
            text = py.read_text(encoding="utf-8")
            assert "fill:#" not in text and "#f96" not in text and "#9f6" not in text, py.name

    def test_every_status_has_an_encoding(self) -> None:
        assert set(palette.ENCODINGS) == set(Status)

    def test_status_enum_is_pure_health(self) -> None:
        """Status carries health semantics only; asset kinds ride data.type."""
        assert {s.value for s in Status} == {
            "ok",
            "partial",
            "missing",
            "broken",
            "cycle",
            "critical-path",
        }

    def test_every_type_has_an_encoding(self) -> None:
        assert set(palette.TYPE_ENCODINGS) == {"orchestrator", "phase", "agent", "skill", "rules"}
        for enc in palette.TYPE_ENCODINGS.values():
            assert enc.fill and enc.stroke

    def test_type_fill_consistent_across_formats(self) -> None:
        """One type renders as one colour in every output format."""
        g = Graph(
            nodes=(Node("x", label="X", data={"type": "skill"}), Node("y", label="Y")),
            edges=(Edge("x", "y"),),
        )
        enc = palette.TYPE_ENCODINGS["skill"]
        assert f"fill:{enc.fill}" in mermaid.render(g)
        assert f'fillcolor="{enc.fill}"' in dot.render(g)
        assert f'"bg": "{enc.fill}"' in html.render(g)

    def test_implicit_typed_nodes_not_styled_in_text(self) -> None:
        """An implicit node (label=None) is invisible to text renderers — a type
        style line would conjure it into the Mermaid graph."""
        g = Graph(
            title="t",
            nodes=(Node("a", label="A"), Node("rules_X", data={"type": "rules"})),
        )
        out = mermaid.render(g)
        assert "rules_X" not in out

    def test_status_fill_consistent_across_formats(self) -> None:
        """One status renders as one colour in every output format."""
        g = Graph(nodes=(Node("x", label="X", status=Status.PARTIAL),))
        enc = palette.encoding(Status.PARTIAL)
        assert enc.fill in mermaid.render(g)
        assert enc.fill in dot.render(g)
        assert enc.fill in html.render(g)

    def test_dashboard_tabs_stay_in_sync_with_collectors(self) -> None:
        """Every registered view is on the dashboard — as a tab, except
        overview which renders as the KPI strip."""
        from cataforge.application.viz.registry import COLLECTORS

        tab_names = {name for name, _ in html._DASHBOARD_VIEWS}
        # overview feeds the KPI strip, phase feeds the stepper — neither is a tab
        assert tab_names == set(COLLECTORS) - {"overview", "phase"}

    def test_view_classification_sets_are_subsets_of_dashboard_views(self) -> None:
        # the grouping / SDLC-gating sets are hand-maintained: a rename or a
        # new view must not silently misclassify
        from cataforge.application.viz.html.page import _SDLC_VIEWS, _VIEW_GROUPS

        tab_names = {name for name, _ in html._DASHBOARD_VIEWS}
        grouped = {name for views in _VIEW_GROUPS.values() for name in views}
        assert grouped == tab_names  # groups exactly partition the tab set
        assert tab_names >= _SDLC_VIEWS
        # project views (arch / tasks included) live outside the framework group
        assert {"arch", "tasks", "coverage", "trace"} <= set(_VIEW_GROUPS["delivery"])

    def test_single_view_has_legend(self) -> None:
        assert 'class="legend"' in html.render(_HTML_GRAPH)

    def test_plain_graph_keeps_simple_search_layout(self) -> None:
        out = html.render(_HTML_GRAPH)  # no node data → no catalogue table
        assert 'class="cat"' not in out
        assert 'class="search"' in out

    def test_script_embedded_json_escapes_closing_tag(self) -> None:
        """A label containing </script> must not terminate the init block."""
        t = Timeline(title="t", events=(TimelineEvent("2026-01-01", "</script><script>x", "c"),))
        out = html.render(t)
        assert "<\\/script>" in out
        assert "</script><script>x" not in out

    def test_catalogue_offline_and_implicit_label_fallback(self) -> None:
        g = Graph(
            title="assets",
            form="catalogue",
            nodes=(
                Node("skill_x", label="x", data={"type": "skill", "name": "x", "path": "p"}),
                Node("rules_r", data={"type": "rules", "name": "R-RULES"}),
            ),
        )
        out = html.render(g)
        assert 'class="cat"' in out and "initCatalogue(" in out
        assert '"label": "R-RULES"' in out or '"label":"R-RULES"' in out  # data.name fallback
        assert "<script src" not in out and "<link " not in out


# ------------------------------------------------------------------
# Artifact encoding — UTF-8 bytes on every locale (UTF-8 Mode contract)
# ------------------------------------------------------------------


class TestVizEncoding:
    def test_dashboard_output_file_is_utf8(self, tmp_path: Path) -> None:
        _make_project(tmp_path)
        out = tmp_path / "dash.html"
        result = CliRunner().invoke(
            cli, ["--project-dir", str(tmp_path), "viz", "dashboard", "-o", str(out)]
        )
        assert result.exit_code == 0, result.output
        text = out.read_bytes().decode("utf-8")  # GBK-written bytes would fail here
        assert "全局检索实体" in text
        assert "已复制" in text


_ROOT_BLOCK_RE = re.compile(r":root\{([^}]*)\}")


def _css_theme_vars(css: str) -> list[dict[str, str]]:
    """Every ``:root{…}`` custom-property block as a name→value dict."""
    themes: list[dict[str, str]] = []
    for body in _ROOT_BLOCK_RE.findall(css):
        pairs: dict[str, str] = {}
        for decl in body.split(";"):
            name, _, value = decl.partition(":")
            if name.strip().startswith("--"):
                pairs[name.strip()] = value.strip()
        themes.append(pairs)
    return themes


def _srgb_channel(v: float) -> float:
    return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4


def _luminance(hexv: str) -> float:
    hexv = hexv.lstrip("#")
    if len(hexv) == 3:
        hexv = "".join(c * 2 for c in hexv)
    r, g, b = (int(hexv[i : i + 2], 16) / 255 for i in (0, 2, 4))
    return 0.2126 * _srgb_channel(r) + 0.7152 * _srgb_channel(g) + 0.0722 * _srgb_channel(b)


def _contrast(a: str, b: str) -> float:
    la, lb = _luminance(a), _luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


_DERIVED_TOKENS = (
    "--viz-node-fill",
    "--viz-node-border",
    "--viz-node-label",
    "--viz-edge",
    "--tip-bg",
    "--tip-fg",
)

# (foreground, surface) pairs as actually composited in dashboard.css rules.
_TEXT_PAIRS = (  # body/small text — WCAG AA 4.5:1
    ("--fg", "--bg"),
    ("--muted", "--bg"),
    ("--muted", "--panel"),
    ("--faint", "--bg"),
    ("--faint", "--panel"),
    ("--faint", "--code-bg"),
    ("--warn-fg", "--bg"),
    ("--error", "--bg"),
    ("--accent", "--code-bg"),
    ("--accent-fg", "--accent"),
    ("--viz-node-label", "--viz-node-fill"),
    ("--tip-fg", "--tip-bg"),
)
_GRAPHIC_PAIRS = (  # non-text graphical elements — WCAG AA 3:1
    ("--viz-edge", "--canvas"),
    ("--viz-node-border", "--canvas"),
    ("--muted", "--bg"),  # legend swatch border
    ("--accent", "--bg"),  # :focus-visible outline
)


class TestVizContrast:
    def test_theme_tokens_meet_wcag_aa(self) -> None:
        themes = _css_theme_vars(html._read_asset("dashboard.css"))
        assert len(themes) == 2  # light + dark
        for theme in themes:
            for fg, bg in _TEXT_PAIRS:
                ratio = _contrast(theme[fg], theme[bg])
                assert ratio >= 4.5, f"{fg} on {bg}: {ratio:.2f} < 4.5 in {theme['--bg']} theme"
            for fg, bg in _GRAPHIC_PAIRS:
                ratio = _contrast(theme[fg], theme[bg])
                assert ratio >= 3.0, f"{fg} on {bg}: {ratio:.2f} < 3.0 in {theme['--bg']} theme"

    def test_legend_swatch_border_follows_theme(self) -> None:
        # a hardcoded near-black border is invisible on the dark panel
        assert "#333" not in html._read_asset("dashboard.css")


class TestVizThemeTokens:
    def test_both_themes_define_derived_graph_tokens(self) -> None:
        themes = _css_theme_vars(html._read_asset("dashboard.css"))
        assert len(themes) == 2
        for theme in themes:
            for token in _DERIVED_TOKENS:
                assert token in theme, f"{token} missing in {theme.get('--bg')} theme"

    def test_graph_style_reads_tokens_with_static_fallback(self) -> None:
        js = html._dashboard_js()
        assert "getComputedStyle" in js
        for token in ("--viz-node-fill", "--viz-node-border", "--viz-edge"):
            assert token in js
        # the old literal style values must not remain baked into initGraph
        assert "'background-color':'#dfe6ee'" not in js
        assert "'line-color':'#aab2bd'" not in js

    def test_theme_switch_and_reduced_motion_wired(self) -> None:
        js = html._dashboard_js()
        assert "prefers-reduced-motion" in js
        # once for chart init, once for the live theme-change re-skin
        assert js.count("prefers-color-scheme") >= 2

    def test_css_has_narrow_viewport_breakpoints(self) -> None:
        css = html._read_asset("dashboard.css")
        assert "@media (max-width:1023px)" in css
        assert "@media (max-width:719px)" in css


_CAT_GRAPH = Graph(
    title="assets",
    form="catalogue",
    nodes=(
        Node(
            "a1",
            label="A1",
            data={"type": "agent", "name": "A1", "est_tokens": 10, "path": "a/A1.md"},
        ),
        Node(
            "s1",
            label="S1",
            data={"type": "skill", "name": "S1", "est_tokens": 20, "path": "s/S1.md"},
        ),
    ),
)


class TestVizHonestAffordances:
    def test_catalogue_sort_header_is_accessible_button(self) -> None:
        out = html.render(_CAT_GRAPH)
        assert 'aria-sort="none"' in out
        assert '<button class="thsort" id="view0_tok" data-key="est_tokens"' in out
        assert 'class="num sortable"' not in out  # a th is not focusable

    def test_sorter_uses_own_column_not_hardcoded_cell(self) -> None:
        js = html._dashboard_js()
        assert "cells[7]" not in js
        assert "aria-sort" in js  # sort state is announced, not visual-only

    def test_copy_waits_for_clipboard_promise_with_fallback(self) -> None:
        js = html._dashboard_js()
        assert "writeText(text).then(" in js  # success is confirmed, not assumed
        assert "按 Ctrl+C 复制" in js  # file:// / denied-permission manual path
        assert "已复制" in js

    def test_row_hint_is_copyable_button(self) -> None:
        g = Graph(
            title="c",
            nodes=(Node("F-1", label="F gap", status=Status.MISSING, data={"hint": "run: x"}),),
        )
        out = html.render(g)
        assert '<button class="rhint"' in out

    def test_toolbars_carry_hitcount_and_reset(self) -> None:
        out = html.render(_HTML_GRAPH)  # edged graph → graph toolbar
        assert 'id="view0_count" aria-live="polite"' in out
        assert 'class="vreset" data-target="view0"' in out
        cat = html.render(_CAT_GRAPH)
        assert 'id="view0_count" aria-live="polite"' in cat
        assert 'class="vreset" data-target="view0"' in cat

    def test_filter_chips_and_segments_carry_aria_pressed(self) -> None:
        out = html.render(_EDGELESS_STATUS_GRAPH)
        assert '<button class="seg"' in out  # keyboard-operable segments
        assert 'aria-pressed="false"' in out
        cat = html.render(_CAT_GRAPH)
        assert cat.count('aria-pressed="true"') >= 2  # type chips start on

    def test_dead_status_row_pointer_removed(self) -> None:
        css = html._read_asset("dashboard.css")
        assert ".stat tbody tr{cursor:pointer}" not in css

    def test_zero_hit_search_keeps_graph_undimmed(self) -> None:
        js = html._dashboard_js()
        assert "命中 0 / " in js  # explicit zero-hit message instead of a ghost graph


_TAGGED_MS = MetricSeries(
    title="overview",
    points=(
        MetricPoint("applicable", 1.0, series="phase", unit="flag"),
        MetricPoint("current:dev", 5.0, series="phase", unit="index"),
        MetricPoint("full", 3.0, series="coverage", unit="count"),
        MetricPoint("partial", 1.0, series="coverage", unit="count"),
        MetricPoint("prd", 0.5, series="docs", unit="ratio"),
        MetricPoint("arch", 1.0, series="docs", unit="ratio"),
    ),
)


class TestVizMetricSemantics:
    def test_json_serializes_unit_only_when_set(self) -> None:
        tagged = json_.render(_TAGGED_MS)
        assert '"unit": "count"' in tagged
        plain = json_.render(_HTML_MS)  # untagged points stay byte-stable
        assert '"unit"' not in plain
        assert '"meta"' not in plain

    def test_overview_points_carry_units(self, tmp_path: Path) -> None:
        from cataforge.application.viz.collectors.overview import collect

        _make_phase_project(tmp_path, "development", phase_start="development")
        view = collect(tmp_path)
        assert isinstance(view, MetricSeries)
        units = {p.unit for p in view.points if p.series == "phase"}
        assert units == {"flag", "index", "count"}

    def test_tagged_metrics_render_cards_and_grid(self) -> None:
        out = html.render(_TAGGED_MS)
        assert 'class="mcards"' in out  # flag/index → text KPI cards
        assert 'class="metric-grid"' in out  # per-series small multiples
        assert out.count("initChart('") == 2  # coverage + docs, one axis each
        assert "✓" in out  # a flag reads as a check, not a bar of height 1

    def test_ratio_series_pins_axis_domain(self) -> None:
        ms = MetricSeries(
            points=(
                MetricPoint("prd", 0.5, series="docs", unit="ratio"),
                MetricPoint("arch", 1.0, series="docs", unit="ratio"),
            )
        )
        out = html.render(ms)
        assert '"max": 1' in out

    def test_single_point_series_becomes_card_not_one_bar_chart(self) -> None:
        ms = MetricSeries(points=(MetricPoint("total", 3.0, series="phase", unit="count"),))
        out = html.render(ms)
        assert 'class="mcards"' in out
        assert "initChart('" not in out

    def test_untagged_metrics_keep_single_chart(self) -> None:
        out = html.render(_HTML_MS)
        assert out.count("initChart('") == 1
        assert 'class="metric-grid"' not in out

    def test_card_only_series_needs_no_echarts(self) -> None:
        ms = MetricSeries(points=(MetricPoint("gate_ok", 1.0, series="phase", unit="flag"),))
        out = html.render(ms)
        assert "Apache Software Foundation" not in out
        _assert_offline(out)

    def test_text_renderers_unaffected_by_unit(self) -> None:
        # mermaid/dot never accepted MetricSeries; the unit field must not
        # change that contract in either direction
        tagged = MetricSeries(points=(MetricPoint("a", 1.0, series="s", unit="count"),))
        with pytest.raises(CataforgeError):
            mermaid.render(tagged)
        with pytest.raises(CataforgeError):
            dot.render(tagged)


class TestVizChartAlternatives:
    def test_timeline_table_and_summary(self) -> None:
        out = html.render(_HTML_TL)
        assert "个事件" in out  # 文本摘要（事件数 + 跨度）
        assert "<th>时间</th>" in out  # 数据表替代含全部事件字段
        assert "<th>事件</th>" in out

    def test_metric_view_table_and_summary(self) -> None:
        out = html.render(_TAGGED_MS)
        assert 'class="alt-table" hidden' in out
        assert "<th>系列</th>" in out
        assert "个指标点" in out

    def test_echarts_aria_enabled(self) -> None:
        for view in (_HTML_TL, _TAGGED_MS):
            out = html.render(view)
            assert '"aria": {"enabled": true}' in out

    def test_graph_alt_table_carries_relations(self) -> None:
        out = html.render(_HTML_GRAPH)  # Alpha → Beta
        assert "<th>上游</th>" in out
        assert "<th>下游</th>" in out
        beta_row = out[out.index('data-node="b"') : out.index("</tr>", out.index('data-node="b"'))]
        assert "Alpha" in beta_row  # Beta 的上游列列出 Alpha

    def test_edgeless_status_table_keeps_two_columns(self) -> None:
        out = html.render(_EDGELESS_STATUS_GRAPH)
        assert "<th>上游</th>" not in out

    def test_timeline_symbol_size_area_proportional(self) -> None:
        t = Timeline(
            title="t",
            events=(
                TimelineEvent("2026-01-01", "a", "c", count=4),
                TimelineEvent("2026-01-02", "b", "c"),
            ),
        )
        out = html.render(t)
        sizes = sorted(int(m) for m in re.findall(r'"symbolSize": (\d+)', out))
        assert sizes == [9, 18]  # 直径 ∝ √count，面积正比；线性公式会给 [12, 21]

    def test_graph_toolbar_has_fit_button(self) -> None:
        out = html.render(_HTML_GRAPH)
        assert 'class="vfit" data-target="view0"' in out
        assert ".vfit" in html._dashboard_js()


class TestVizSparkline:
    def test_percent_domain_is_stable(self) -> None:
        from cataforge.application.viz.html.kpi import _sparkline

        svg = _sparkline([97.0, 98.0], domain="percent")
        assert 'role="img"' in svg
        assert "aria-hidden" not in svg  # 趋势对读屏可及
        assert "Δ+1" in svg
        pts = re.search(r'points="([^"]+)"', svg)
        assert pts is not None
        ys = [float(p.split(",")[1]) for p in pts.group(1).split()]
        # 0-100 稳定域下 97→98 只允许微小波动，而非满幅陡坡
        assert max(ys) - min(ys) < 1.0

    def test_count_domain_zero_anchored(self) -> None:
        from cataforge.application.viz.html.kpi import _sparkline

        svg = _sparkline([1.0, 2.0], domain="count")
        pts = re.search(r'points="([^"]+)"', svg)
        assert pts is not None
        ys = [float(p.split(",")[1]) for p in pts.group(1).split()]
        # 0-max 域：1 落半高、2 触顶，而非 min/max 归一的满幅
        assert ys[0] == pytest.approx(8.0)
        assert ys[1] == pytest.approx(2.0)
