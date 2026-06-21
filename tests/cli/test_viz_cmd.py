"""Tests for ``cataforge viz`` + the shared core.viz IR / renderers."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from click.testing import CliRunner

from cataforge.application.viz import html, service
from cataforge.core.errors import CataforgeError
from cataforge.core.viz.model import (
    Edge,
    Graph,
    MetricPoint,
    MetricSeries,
    Node,
    Timeline,
    TimelineEvent,
)
from cataforge.core.viz.render import dot, json_, mermaid
from cataforge.interface.cli.main import cli

_CP_STYLE = "fill:#f96,stroke:#333,stroke-width:2px"


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
            nodes=(Node("T-001", style=_CP_STYLE), Node("T-003", style=_CP_STYLE)),
        )
        assert mermaid.render(g) == (
            f"graph LR\n    T-001 --> T-002\n    T-002 --> T-003\n    style T-001,T-003 {_CP_STYLE}"
        )

    def test_cjk_label_stays_unquoted(self) -> None:
        g = Graph(direction="LR", nodes=(Node("empty", label="无有效边"),))
        assert mermaid.render(g) == "graph LR\n    empty[无有效边]"

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
        assert "style" in result.output  # critical-path nodes highlighted

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

    def test_cycle_nodes_flagged_red(self, tmp_path: Path) -> None:
        result = _viz(tmp_path, "tasks", "--edges", "T-001→T-002,T-002→T-001")
        assert result.exit_code == 0, result.output
        assert "#f00" in result.output  # cycle style

    def test_invalid_edges_placeholder(self, tmp_path: Path) -> None:
        # non-empty edges that parse to nothing → empty-graph placeholder
        result = _viz(tmp_path, "tasks", "--edges", "garbage-no-arrow")
        assert result.exit_code == 0, result.output
        assert "无有效边" in result.output


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

    def test_no_tasks_placeholder(self, tmp_path: Path) -> None:
        _make_kg_project(tmp_path)  # KG with Features/Modules but no Tasks
        result = _viz(tmp_path, "tasks")
        assert result.exit_code == 0, result.output
        assert "无有效边" in result.output

    def test_uninitialised_store_degrades(self, tmp_path: Path) -> None:
        result = _viz(tmp_path, "tasks")  # no --edges, no KG store
        assert result.exit_code != 0
        assert "kg init" in result.output.lower()


# ------------------------------------------------------------------
# process views — phase / timeline / decay
# ------------------------------------------------------------------


def _make_phase_project(tmp_path: Path, phase: str, *, phase_start: str | None = None) -> Path:
    """Project with framework.json (standard phases) + an instruction file
    declaring 当前阶段; optionally a phase_start EVENT-LOG record."""
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
                }
            }
        }
    }
    (cf / "framework.json").write_text(json.dumps(framework))
    (tmp_path / "CLAUDE.md").write_text(
        f"# Proj\n## 项目状态\n- 当前阶段: {phase}\n- 文档状态:\n", encoding="utf-8"
    )
    if phase_start:
        docs = tmp_path / "docs"
        docs.mkdir(exist_ok=True)
        rec = {"ts": "2026-01-01T00:00:00+00:00", "event": "phase_start", "phase": phase_start}
        (docs / "EVENT-LOG.jsonl").write_text(json.dumps(rec) + "\n", encoding="utf-8")
    return tmp_path


class TestVizPhase:
    def test_blocked_phase_styled_red(self, tmp_path: Path) -> None:
        _make_phase_project(tmp_path, "requirements")  # no prd doc/index/event → blocked
        result = _viz(tmp_path, "phase")
        assert result.exit_code == 0, result.output
        assert "graph LR" in result.output
        assert "style requirements fill:#f96" in result.output

    def test_ok_phase_styled_green(self, tmp_path: Path) -> None:
        # development carries no doc gate; with its phase_start it passes all checks
        _make_phase_project(tmp_path, "development", phase_start="development")
        result = _viz(tmp_path, "phase")
        assert result.exit_code == 0, result.output
        assert "style development fill:#9f6" in result.output

    def test_styling_tracks_phase_status_conclusion(self, tmp_path: Path) -> None:
        from cataforge.application.phase import evaluate_phase

        _make_phase_project(tmp_path, "development", phase_start="development")
        _, checks = evaluate_phase(tmp_path)
        blocked = any(not ok for _, ok, _ in checks)
        result = _viz(tmp_path, "phase")
        # green (ok) appears iff the gate is not blocked — same conclusion that
        # drives `cataforge phase status` exit code.
        assert ("#9f6" in result.output) == (not blocked)

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

    def test_empty_when_no_log(self, tmp_path: Path) -> None:
        result = _viz(tmp_path, "decay")
        assert result.exit_code == 0, result.output
        assert "no events" in result.output


# ------------------------------------------------------------------
# assets view — agent / skill catalogue graph
# ------------------------------------------------------------------


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
    nodes=(Node("a", label="Alpha"), Node("b", label="Beta", style="fill:#f96,stroke:#333")),
    edges=(Edge("a", "b", label="rel"),),
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

    def test_graph_node_style_maps_to_data(self) -> None:
        out = html.render(_HTML_GRAPH)
        assert '"bg": "#f96"' in out
        assert '"border": "#333"' in out

    def test_graph_has_search_box(self) -> None:
        assert 'class="search"' in html.render(_HTML_GRAPH)

    def test_timeline_inlines_echarts_only(self) -> None:
        out = html.render(_HTML_TL)
        assert "Apache Software Foundation" in out
        assert "Cytoscape Consortium" not in out
        assert "initChart('view0'" in out
        _assert_offline(out)

    def test_metrics_inlines_echarts(self) -> None:
        out = html.render(_HTML_MS)
        assert "Apache Software Foundation" in out
        assert "initChart('view0'" in out
        _assert_offline(out)


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


class TestVizHtmlCli:
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
