"""Doctor `kg_snapshot_gitignore` check tests.

In graph mode the gitignored store rebuilds from the committed NQuads snapshot
on clone, so a project-root .gitignore that also excludes the snapshots dir
silently drops the graph's only durable artifact. The check is advisory (WARN).
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class FakePaths:
    root: Path

    @property
    def framework_json(self) -> Path:
        return self.root / ".cataforge" / "framework.json"


@dataclass
class FakeConfig:
    paths: FakePaths


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _graph_project(tmp_path: Path, gitignore_body: str, *, mode: str = "graph") -> Path:
    work = tmp_path / "proj"
    work.mkdir()
    _git(work, "init", "-b", "main")
    (work / ".cataforge").mkdir()
    (work / ".cataforge" / "framework.json").write_text(
        json.dumps({"context": {"mode": mode}}), encoding="utf-8"
    )
    (work / ".gitignore").write_text(gitignore_body, encoding="utf-8")
    return work


def test_warns_when_snapshots_ignored_by_root_gitignore(tmp_path, capsys) -> None:
    from cataforge.interface.cli.doctor.kg_ingestion import check_kg_snapshot_gitignore

    proj = _graph_project(tmp_path, ".cataforge/kg/\n")
    cfg = FakeConfig(paths=FakePaths(root=proj))

    failures = check_kg_snapshot_gitignore(cfg)
    out = capsys.readouterr().out

    assert failures == 0, out
    assert "WARN" in out
    assert "snapshot" in out.lower()


def test_ok_when_snapshots_tracked(tmp_path, capsys) -> None:
    from cataforge.interface.cli.doctor.kg_ingestion import check_kg_snapshot_gitignore

    # Root ignores only the store, mirroring .cataforge/.gitignore — snapshots tracked.
    proj = _graph_project(tmp_path, ".cataforge/kg/store/\n")
    cfg = FakeConfig(paths=FakePaths(root=proj))

    failures = check_kg_snapshot_gitignore(cfg)
    out = capsys.readouterr().out

    assert failures == 0, out
    assert "WARN" not in out
    assert "OK" in out


def test_skips_outside_graph_mode(tmp_path, capsys) -> None:
    from cataforge.interface.cli.doctor.kg_ingestion import check_kg_snapshot_gitignore

    proj = _graph_project(tmp_path, ".cataforge/kg/\n", mode="markdown")
    cfg = FakeConfig(paths=FakePaths(root=proj))

    failures = check_kg_snapshot_gitignore(cfg)
    out = capsys.readouterr().out

    assert failures == 0, out
    assert "skipping" in out
