"""KGConfig defaults match task-5 §5.2 and round-2 decisions.

These tests must run successfully in CI environments without the `kg`
extra installed (no pyoxigraph, no linkml-runtime). The package's public
import path is permitted to do its own lazy-import gymnastics, but
`KGConfig` is a pure-stdlib dataclass and the contract here is that
importing it never reaches into pyoxigraph.
"""
from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

from cataforge.kg import KGConfig


def test_defaults_match_spec() -> None:
    cfg = KGConfig()
    assert cfg.store_backend == "oxigraph"
    assert cfg.db_path == Path(".cataforge/kg/store")
    assert cfg.governance is False
    assert cfg.coverage_mode == "strict"
    assert cfg.query_timeout == 30.0
    assert cfg.max_transaction_retries == 3
    assert cfg.base_namespace == "https://cataforge.dev/instance/"
    assert cfg.ontology_namespace == "https://cataforge.dev/ontology/"
    assert cfg.plugins_dir is None


def test_kg_active_doc_types_defaults_to_empty_set() -> None:
    """Round-2 decision: legacy loader is the read path until cutover populates this."""
    cfg = KGConfig()
    assert cfg.kg_active_doc_types == set()
    # Per-instance set, not shared mutable default.
    cfg.kg_active_doc_types.add("prd")
    assert KGConfig().kg_active_doc_types == set()


def test_str_db_path_is_coerced_to_path() -> None:
    cfg = KGConfig(db_path="/tmp/store")  # type: ignore[arg-type]
    assert isinstance(cfg.db_path, Path)
    assert cfg.db_path == Path("/tmp/store")


def test_list_active_doc_types_is_coerced_to_set() -> None:
    cfg = KGConfig(kg_active_doc_types=["prd", "arch", "prd"])  # type: ignore[arg-type]
    assert cfg.kg_active_doc_types == {"prd", "arch"}


def test_base_import_does_not_require_pyoxigraph() -> None:
    """Regression: `from cataforge.kg import KGConfig` in a CI image that
    didn't install the `kg` extra must not blow up at import time. Test in
    a subprocess that masks pyoxigraph in sys.modules so a developer-local
    install doesn't hide the regression."""
    code = textwrap.dedent(
        """
        import sys
        sys.modules["pyoxigraph"] = None  # force ImportError if anything imports it
        from cataforge.kg import KGConfig
        cfg = KGConfig()
        assert cfg.store_backend == "oxigraph"
        assert cfg.kg_active_doc_types == set()
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, (
        f"base import pulled in pyoxigraph eagerly\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
