"""`context index` / `context validate` parity with the deprecated `docs` aliases.

The new ``context`` verbs share the same implementation body as the deprecated
``docs`` aliases, so behaviour (exit code + stdout) is identical; the aliases
additionally print a one-line deprecation hint on stderr without disturbing
stdout.
"""

from __future__ import annotations

import json
from pathlib import Path

from cataforge.domain.docs import indexer
from cataforge.interface.cli.context_cmd import context_index, context_validate
from cataforge.interface.cli.docs_cmd import docs_index, docs_validate
from tests.cli.conftest import invoke_under_group, populate_required_source_assets


def _minimal_project(tmp_path: Path) -> Path:
    cf = tmp_path / ".cataforge"
    cf.mkdir()
    (cf / "framework.json").write_text(
        json.dumps({"version": "0.1.0", "runtime_api_version": "1.0"}),
        encoding="utf-8",
    )
    populate_required_source_assets(cf)
    return tmp_path


def _write_doc(root: Path, rel: str, body: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


# ---- context index parity ---------------------------------------------------


def test_context_index_builds_index(tmp_path: Path, monkeypatch) -> None:
    root = _minimal_project(tmp_path)
    _write_doc(root, "docs/prd/good.md", "---\nid: prd-good\ndoc_type: prd\n---\n# Good\n")

    monkeypatch.chdir(root)
    result = invoke_under_group(context_index, [])

    assert result.exit_code == 0, result.output
    assert (root / "docs" / ".doc-index.json").is_file()


def test_context_index_strict_orphan_exits_3(tmp_path: Path, monkeypatch) -> None:
    root = _minimal_project(tmp_path)
    _write_doc(root, "docs/prd/good.md", "---\nid: prd-good\ndoc_type: prd\n---\n# Good\n")
    _write_doc(root, "docs/research/orphan.md", "# No front matter\n")

    monkeypatch.chdir(root)
    result = invoke_under_group(context_index, ["--strict"])

    assert result.exit_code == 3, result.output


# ---- context validate parity ------------------------------------------------


def test_context_validate_clean_index_exits_zero(tmp_path: Path, monkeypatch) -> None:
    root = _minimal_project(tmp_path)
    _write_doc(root, "docs/prd/good.md", "---\nid: prd-good\ndoc_type: prd\n---\n# Good\n")
    indexer.main(["--project-root", str(root)])

    monkeypatch.chdir(root)
    result = invoke_under_group(context_validate, [])

    assert result.exit_code == 0
    assert "0 orphans" in result.output


def test_context_validate_orphan_exits_3(tmp_path: Path, monkeypatch) -> None:
    root = _minimal_project(tmp_path)
    _write_doc(root, "docs/prd/good.md", "---\nid: prd-good\ndoc_type: prd\n---\n# Good\n")
    indexer.main(["--project-root", str(root)])
    _write_doc(root, "docs/research/orphan.md", "# No front matter\n")

    monkeypatch.chdir(root)
    result = invoke_under_group(context_validate, [])

    assert result.exit_code == 3
    assert "orphan" in result.output.lower()


def test_context_validate_no_index_exits_2(tmp_path: Path, monkeypatch) -> None:
    root = _minimal_project(tmp_path)
    (root / "docs").mkdir()

    monkeypatch.chdir(root)
    result = invoke_under_group(context_validate, [])

    assert result.exit_code == 2


# ---- alias equivalence + stderr deprecation hint ----------------------------


def _stdout_only(result) -> str:
    """Strip stderr from the CliRunner combined stream to recover stdout.

    ``CliRunner.output`` interleaves stdout + stderr; ``result.stderr`` is the
    stderr-only capture. Removing it yields the stdout the JSON/text consumers
    actually read.
    """
    return result.output.replace(result.stderr, "", 1)


def test_docs_index_alias_matches_context_index(tmp_path: Path, monkeypatch) -> None:
    root = _minimal_project(tmp_path)
    _write_doc(root, "docs/prd/good.md", "---\nid: prd-good\ndoc_type: prd\n---\n# Good\n")

    monkeypatch.chdir(root)
    via_alias = invoke_under_group(docs_index, [])
    via_context = invoke_under_group(context_index, [])

    assert via_alias.exit_code == via_context.exit_code == 0
    assert _stdout_only(via_alias) == via_context.output
    assert "deprecated: use 'cataforge context index' instead" in via_alias.stderr
    assert via_context.stderr == ""


def test_docs_validate_alias_matches_context_validate(tmp_path: Path, monkeypatch) -> None:
    root = _minimal_project(tmp_path)
    _write_doc(root, "docs/prd/good.md", "---\nid: prd-good\ndoc_type: prd\n---\n# Good\n")
    indexer.main(["--project-root", str(root)])

    monkeypatch.chdir(root)
    via_alias = invoke_under_group(docs_validate, [])
    via_context = invoke_under_group(context_validate, [])

    assert via_alias.exit_code == via_context.exit_code == 0
    assert _stdout_only(via_alias) == via_context.output
    assert "deprecated: use 'cataforge context validate' instead" in via_alias.stderr
    assert "deprecated" not in via_context.stderr


def test_docs_load_alias_hint_on_stderr_stdout_intact(tmp_path: Path, monkeypatch) -> None:
    """The deprecation hint goes to stderr only — JSON consumers reading stdout
    are not broken."""
    from cataforge.interface.cli.context_cmd import context_read
    from cataforge.interface.cli.docs_cmd import docs_load

    root = _minimal_project(tmp_path)
    _write_doc(
        root,
        "docs/prd/prd-main.md",
        "---\nid: prd\ndoc_type: prd\n---\n# 1. Overview\n\nbody text\n",
    )
    indexer.main(["--project-root", str(root)])

    monkeypatch.chdir(root)
    via_alias = invoke_under_group(docs_load, ["prd#§1", "--json"])
    via_context = invoke_under_group(context_read, ["prd#§1", "--json"])

    assert via_alias.exit_code == via_context.exit_code == 0, via_alias.output
    alias_stdout = _stdout_only(via_alias)
    assert alias_stdout == via_context.output
    # stdout stays parseable JSON — hint must not leak into it.
    json.loads(alias_stdout)
    assert "deprecated: use 'cataforge context read' instead" in via_alias.stderr
