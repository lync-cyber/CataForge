"""Doctor gate for ``context.mode`` validity and the retired schema."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from cataforge.interface.cli.doctor.context_authority import check_context_mode_validity


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


def test_passes_on_valid_mode(tmp_path: Path) -> None:
    for mode in ("markdown", "graph"):
        assert check_context_mode_validity(_cfg(tmp_path, {"mode": mode})) == 0


def test_fails_on_invalid_mode(tmp_path: Path, capsys) -> None:
    cfg = _cfg(tmp_path, {"mode": "bogus"})
    assert check_context_mode_validity(cfg) == 1
    assert "FAIL" in capsys.readouterr().err


def test_fails_on_retired_strategy_key(tmp_path: Path, capsys) -> None:
    cfg = _cfg(tmp_path, {"strategy": "kg-first"})
    assert check_context_mode_validity(cfg) == 1
    assert "upgrade apply" in capsys.readouterr().err


def test_fails_on_retired_authoring_key(tmp_path: Path, capsys) -> None:
    cfg = _cfg(tmp_path, {"authoring": "graph"})
    assert check_context_mode_validity(cfg) == 1
    assert "FAIL" in capsys.readouterr().err


def test_passes_when_mode_absent(tmp_path: Path) -> None:
    # No context.mode and no retired keys → relies on the graph default.
    assert check_context_mode_validity(_cfg(tmp_path, {})) == 0


def test_skips_when_no_framework_json(tmp_path: Path) -> None:
    cfg = _Cfg(paths=_Paths(root=tmp_path))
    assert check_context_mode_validity(cfg) == 0
