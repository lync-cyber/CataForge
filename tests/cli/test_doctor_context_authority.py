"""Doctor gate for the context.strategy / context.authoring pair."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from cataforge.interface.cli.doctor.context_authority import check_context_authority_config


@dataclass
class _Paths:
    root: Path

    @property
    def framework_json(self) -> Path:
        return self.root / ".cataforge" / "framework.json"


@dataclass
class _Cfg:
    paths: _Paths


def _cfg(tmp_path: Path, context: dict | None) -> _Cfg:
    cf = tmp_path / ".cataforge"
    cf.mkdir(parents=True, exist_ok=True)
    payload: dict = {"version": "0.1.0"}
    if context is not None:
        payload["context"] = context
    (cf / "framework.json").write_text(json.dumps(payload), encoding="utf-8")
    return _Cfg(paths=_Paths(root=tmp_path))


def test_passes_on_graph_authoring_under_kg_first(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path, {"strategy": "kg-first", "authoring": "graph"})
    assert check_context_authority_config(cfg) == 0


def test_passes_on_md_authoring_under_doc_only(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path, {"strategy": "doc-only", "authoring": "md"})
    assert check_context_authority_config(cfg) == 0


def test_fails_on_graph_authoring_without_kg_first(tmp_path: Path, capsys) -> None:
    cfg = _cfg(tmp_path, {"strategy": "doc-only", "authoring": "graph"})
    assert check_context_authority_config(cfg) == 1
    assert "FAIL" in capsys.readouterr().err


def test_warns_but_passes_on_unknown_value(tmp_path: Path, capsys) -> None:
    cfg = _cfg(tmp_path, {"strategy": "bogus"})
    assert check_context_authority_config(cfg) == 0
    assert "WARN" in capsys.readouterr().err


def test_skips_when_no_context_block(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path, None)
    assert check_context_authority_config(cfg) == 0
