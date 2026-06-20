"""Tests for ``cataforge viz`` + the shared core.viz IR / renderers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from cataforge.application.viz import service
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

    def test_rejects_non_graph(self) -> None:
        with pytest.raises(CataforgeError):
            mermaid.render(Timeline())


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
