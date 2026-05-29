"""Smoke tests for scripts/codegen_kg_schema.py (sub-PR 1 deliverable)."""

from __future__ import annotations

import filecmp
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "codegen_kg_schema.py"

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("linkml") is None,
    reason="linkml not installed (only required for KG codegen — add the `dev` extra)",
)


def _run_codegen(out_dir: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--out", str(out_dir)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"},
    )
    assert result.returncode == 0, (
        f"codegen exited {result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


@pytest.fixture(scope="session")
def codegen_out(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """One codegen run shared by every read-only assertion in this module.

    Codegen output is deterministic (proven by
    ``test_subclass_axioms_byte_identical_on_rerun``), so the read-only
    tests can all inspect a single shared artifact set instead of each
    paying the linkml-generation cost.
    """
    out = tmp_path_factory.mktemp("kg_codegen")
    _run_codegen(out)
    return out


def test_codegen_produces_expected_artifacts(codegen_out: Path) -> None:
    for name in (
        "core_pydantic.py",
        "governance_pydantic.py",
        "core_shapes.ttl",
        "governance_shapes.ttl",
        "subclass_axioms.ttl",
    ):
        assert (codegen_out / name).is_file(), f"missing artifact: {name}"


def test_subclass_axioms_byte_identical_on_rerun(codegen_out: Path, tmp_path: Path) -> None:
    """spike-2 §2.1 — subclass_axioms.ttl is the input to `kg init` bootstrap;
    deterministic emission is required so store init is reproducible."""
    fresh = tmp_path / "run2"
    _run_codegen(fresh)
    assert filecmp.cmp(
        codegen_out / "subclass_axioms.ttl",
        fresh / "subclass_axioms.ttl",
        shallow=False,
    )


def test_subclass_axioms_covers_known_chain(codegen_out: Path) -> None:
    """The `is_a` chain must materialize: Feature → Requirement → SoftwareArtifact,
    Page → Screen → SoftwareArtifact (the canonical UI-layer alias chain),
    Sprint → WorkUnit → SoftwareArtifact (agile process model)."""
    ttl = (codegen_out / "subclass_axioms.ttl").read_text(encoding="utf-8")
    for child, parent in [
        ("cf:Feature", "cf:Requirement"),
        ("cf:Requirement", "cf:SoftwareArtifact"),
        ("cf:Page", "cf:Screen"),
        ("cf:Screen", "cf:SoftwareArtifact"),
        ("cf:Sprint", "cf:WorkUnit"),
        ("cf:WorkUnit", "cf:SoftwareArtifact"),
    ]:
        triple = f"{child} rdfs:subClassOf {parent} ."
        assert triple in ttl, f"missing axiom: {triple}\n--- ttl ---\n{ttl}"


def test_pydantic_module_smoke_imports(codegen_out: Path) -> None:
    """Generated Pydantic module must be a parseable Python file with known classes."""
    core_py = codegen_out / "core_pydantic.py"
    spec = importlib.util.spec_from_file_location("_kg_core_pydantic", core_py)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for cls in ("Feature", "Component", "TestCase", "Project", "SoftwareArtifact"):
        assert hasattr(module, cls), f"generated module missing class: {cls}"
