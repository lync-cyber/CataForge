"""O2b: doctor WARN for entity-id headings with an unregistered prefix.

An id-shaped heading subject whose prefix is neither core nor registered is
dropped by ingest; the gate surfaces it (advisory) instead of the silent drop
that the closed ontology used to produce.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from tests.kg._kg_fixtures import setup_project_with_kg as _setup_project_with_kg


@dataclass
class _Paths:
    root: Path

    @property
    def framework_json(self) -> Path:
        return self.root / ".cataforge" / "framework.json"


@dataclass
class _Cfg:
    paths: _Paths


def _append_heading(project_root: Path, heading: str) -> None:
    prd = project_root / "docs" / "prd" / "prd-vertical-slice.md"
    prd.write_text(
        prd.read_text(encoding="utf-8") + f"\n\n{heading}\n\n聚合订单。\n", encoding="utf-8"
    )


def test_unregistered_prefix_heading_warns(tmp_path, capsys) -> None:
    from cataforge.interface.cli.doctor.kg_ingestion import check_kg_ingestion_completeness

    project_root = _setup_project_with_kg(tmp_path)
    _append_heading(project_root, "### XYZ-001 订单聚合")
    failures = check_kg_ingestion_completeness(_Cfg(paths=_Paths(root=project_root)))
    out = capsys.readouterr().out
    assert "XYZ" in out, out
    assert "custom_entity_prefixes" in out, out
    # Advisory: an unregistered heading does not fail the gate on its own.
    assert failures == 0, out


def test_registered_prefix_heading_not_warned(tmp_path, capsys) -> None:
    from cataforge.domain.kg._dispatch import invalidate_cache
    from cataforge.interface.cli.doctor.kg_ingestion import check_kg_ingestion_completeness

    project_root = _setup_project_with_kg(tmp_path)
    fw = project_root / ".cataforge" / "framework.json"
    data = json.loads(fw.read_text(encoding="utf-8"))
    data.setdefault("kg", {})["custom_entity_prefixes"] = {"XYZ": "Thing"}
    fw.write_text(json.dumps(data), encoding="utf-8")
    _append_heading(project_root, "### XYZ-001 订单聚合")
    invalidate_cache()
    check_kg_ingestion_completeness(_Cfg(paths=_Paths(root=project_root)))
    out = capsys.readouterr().out
    assert "unregistered prefix" not in out, out


def test_algorithm_mention_alongside_known_entity_not_warned(tmp_path, capsys) -> None:
    # A heading that already defines a known entity is not misread even when it
    # also names an algorithm token like SHA-256.
    from cataforge.interface.cli.doctor.kg_ingestion import check_kg_ingestion_completeness

    project_root = _setup_project_with_kg(tmp_path)
    _append_heading(project_root, "### F-901 使用 SHA-256 校验")
    check_kg_ingestion_completeness(_Cfg(paths=_Paths(root=project_root)))
    out = capsys.readouterr().out
    assert "unregistered prefix" not in out, out
