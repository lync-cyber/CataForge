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
            "issue": "stale",
            "hint": "run: cataforge context reconcile",
        }
        assert nodes["ghost"]["data"] == {
            "issue": "xref-error",
            "hint": "run: cataforge context validate",
        }

    def test_healthy_node_has_no_data_bag(self, tmp_path: Path) -> None:
        # prd-x has no stale/xref problem → no hint bag (JSON stays lean)
        _make_docs_project(tmp_path)
        result = _viz(tmp_path, "docs", "--format", "json")
        nodes = {n["id"]: n for n in json.loads(result.output)["nodes"]}
        assert "data" not in nodes["prd-x"]

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
        assert "d.className='viztip'" in out  # hover-card element wired into initGraph

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
        assert 'class="stat"' not in out
        assert "initGraph('view0'" in out

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
    doc-index, instruction file all absent so several views degrade."""
    _make_project(tmp_path)
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
        for label in ("Framework", "Assets", "Timeline", "Decay"):
            assert f">{label}<" in out
        assert out.count('<button class="tab') == 10

    def test_failed_views_degrade_to_error_panel(self, tmp_path: Path) -> None:
        # no KG / doc-index / instruction file → trace/coverage/arch/docs/tasks/phase fail
        _make_dashboard_project(tmp_path)
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
        assert out.count('<button class="kpi ') == 5
        assert out.count('<button class="tab') == 10  # the strip adds no tab

    def test_kpi_strip_shows_phase_and_gate(self, tmp_path: Path) -> None:
        _make_phase_project(tmp_path, "development", phase_start="development")
        out = html.render_dashboard(tmp_path)
        assert "development 3/3" in out
        assert "门禁通过" in out

    def test_kpi_phase_tile_shows_na_for_non_driven_project(self, tmp_path: Path) -> None:
        # instruction file present but 当前阶段 unfilled → N/A tile, not a red
        # 门禁受阻 false alarm
        _make_phase_project(tmp_path, "{a|b|c}")
        out = html.render_dashboard(tmp_path)
        assert "门禁受阻" not in out
        assert "不适用" in out
        assert '<button class="kpi na"' in out

    def test_legend_present(self, tmp_path: Path) -> None:
        _make_dashboard_project(tmp_path)
        out = html.render_dashboard(tmp_path)
        assert 'class="legend"' in out
        for hexv, label in palette.LEGEND:
            assert hexv in out and label in out

    def _panel_id(self, name: str) -> str:
        return f"panel-{name}"

    def test_coverage_to_trace_link_wired_when_ready(self, tmp_path: Path) -> None:
        # coverage is edgeless → renders as a status table, so its row clicks
        # wire to trace via linkTable (not linkGraph)
        _make_kg_project(tmp_path)
        out = html.render_dashboard(tmp_path)
        cov, trace = self._panel_id("coverage"), self._panel_id("trace")
        assert f"linkTable('{cov}_v', '{trace}');" in out
        assert "window.__viz.focus=function" in out

    def test_cross_view_link_absent_when_coverage_degraded(self, tmp_path: Path) -> None:
        _make_dashboard_project(tmp_path)  # no KG → coverage panel degrades
        out = html.render_dashboard(tmp_path)
        assert "linkTable('" not in out and "linkGraph('" not in out  # no wiring call

    def test_tasks_to_trace_link_wired_when_ready(self, tmp_path: Path) -> None:
        # a task id reappears in the traceability chain → tapping a task node
        # focuses it in the trace tab; tasks has edges so it wires via linkGraph
        _make_kg_tasks_project(tmp_path)
        out = html.render_dashboard(tmp_path)
        tasks, trace = self._panel_id("tasks"), self._panel_id("trace")
        assert f"linkGraph('{tasks}_v', '{trace}');" in out

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
        assert "项目健康" in out and "框架资产" in out
        assert out.count('<button class="tab') == 10  # every view still has a tab

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

    def test_cross_link_wired_inside_source_panel_register(self, tmp_path: Path) -> None:
        # wiring shares the source panel's register closure, so it can never
        # run before its own graph/table instances exist
        _make_kg_project(tmp_path)
        out = html.render_dashboard(tmp_path)
        cov, trace = self._panel_id("coverage"), self._panel_id("trace")
        assert out.index(f"__viz.register('{cov}'") < out.index(f"linkTable('{cov}_v', '{trace}');")

    def test_tabs_carry_aria_roles(self, tmp_path: Path) -> None:
        _make_dashboard_project(tmp_path)
        out = html.render_dashboard(tmp_path)
        assert 'role="tablist"' in out
        assert out.count('role="tab" aria-selected') == 10
        assert out.count('aria-selected="true"') == 1
        assert out.count('role="tabpanel"') == 10

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

    def test_window_resize_handler_debounced(self, tmp_path: Path) -> None:
        _make_dashboard_project(tmp_path)
        out = html.render_dashboard(tmp_path)
        assert "addEventListener('resize'" in out
        assert "setTimeout" in out


class TestVizHtmlCli:
    def test_single_view_inits_immediately(self, tmp_path: Path) -> None:
        # a single-view page has no tabs: its init runs directly instead of
        # queueing behind a panel registration
        _make_project(tmp_path)
        result = _viz(tmp_path, "framework", "--html")
        assert "initGraph('view0'" in result.output
        assert "__viz.register('panel-" not in result.output

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
        assert tab_names == set(COLLECTORS) - {"overview"}

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
