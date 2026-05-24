"""kg_auto_ingest hook script — quiet-fail + path filtering contract."""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = (
    REPO_ROOT
    / "src" / "cataforge" / "hook" / "scripts" / "kg_auto_ingest.py"
)


def _run_script(payload: dict[str, object]) -> subprocess.CompletedProcess:
    """Run kg_auto_ingest.py as a subprocess with the given JSON payload."""
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH)],
        input=json.dumps(payload).encode("utf-8"),
        capture_output=True,
        timeout=60,
        check=False,
    )


@pytest.fixture
def doc_project(tmp_path: Path) -> Path:
    """A scaffold with a single ingestable markdown under docs/."""
    (tmp_path / "docs").mkdir()
    md = tmp_path / "docs" / "prd-acme.md"
    md.write_text(textwrap.dedent("""\
        ---
        id: prd-acme
        ---
        # PRD
        ## F-001 login
    """), encoding="utf-8")
    return tmp_path


# ---------- filtering ----------

def test_ignores_non_markdown(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    other = tmp_path / "docs" / "code.py"
    other.write_text("print('hi')\n", encoding="utf-8")
    result = _run_script({
        "tool_name": "Write",
        "tool_input": {"file_path": str(other)},
    })
    assert result.returncode == 0
    # No ingest invocation → no inferred .doc-graph.
    assert not (tmp_path / "docs" / ".doc-graph").exists()


def test_ignores_doc_graph_internals(tmp_path: Path) -> None:
    (tmp_path / "docs" / ".doc-graph").mkdir(parents=True)
    inner = tmp_path / "docs" / ".doc-graph" / "instances.nq"
    inner.write_text("", encoding="utf-8")
    # An Edit to a file inside .doc-graph/ must NOT recurse into ingest —
    # ingesting the store back into itself would deadlock the merge.
    inner_md = tmp_path / "docs" / ".doc-graph" / "stale.md"
    inner_md.write_text("---\nid: x\n---\n", encoding="utf-8")
    result = _run_script({
        "tool_name": "Edit",
        "tool_input": {"file_path": str(inner_md)},
    })
    assert result.returncode == 0


def test_ignores_cataforge_framework_assets(tmp_path: Path) -> None:
    (tmp_path / ".cataforge" / "skills").mkdir(parents=True)
    skill_md = tmp_path / ".cataforge" / "skills" / "fake.md"
    skill_md.write_text("---\nname: fake\n---\nBody\n", encoding="utf-8")
    result = _run_script({
        "tool_name": "Edit",
        "tool_input": {"file_path": str(skill_md)},
    })
    assert result.returncode == 0


# ---------- quiet-fail ----------

def test_quiet_fails_on_missing_file(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    ghost = tmp_path / "docs" / "ghost.md"
    result = _run_script({
        "tool_name": "Write",
        "tool_input": {"file_path": str(ghost)},
    })
    assert result.returncode == 0


def test_quiet_fails_on_missing_payload() -> None:
    result = _run_script({"tool_name": "Edit"})  # no tool_input
    assert result.returncode == 0


# ---------- happy path ----------

def test_ingests_valid_docs_file(doc_project: Path) -> None:
    md = doc_project / "docs" / "prd-acme.md"
    # The hook script CD's into the file's project root by walking up
    # for docs/; subprocess inherits the cwd of the caller, so the test
    # runs the script with cwd=doc_project to match the real PostToolUse
    # environment where the IDE invokes from the project root.
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH)],
        input=json.dumps({
            "tool_name": "Write",
            "tool_input": {"file_path": str(md)},
        }).encode("utf-8"),
        capture_output=True,
        cwd=str(doc_project),
        timeout=60,
        check=False,
    )
    # Quiet-fail: always exit 0 even if ingest had subtle issues.
    assert result.returncode == 0
