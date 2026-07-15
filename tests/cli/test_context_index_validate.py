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
from cataforge.interface.cli.context.index import context_index, context_validate
from cataforge.interface.cli.docs_cmd import docs_index, docs_validate
from tests.cli.conftest import invoke_under_group
from tests.cli.conftest import make_minimal_project as _minimal_project
from tests.cli.conftest import write_doc as _write_doc

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


# ---- D6: validate == index --strict --dry-run -------------------------------


def test_validate_equals_index_strict_dryrun_clean(tmp_path: Path, monkeypatch) -> None:
    root = _minimal_project(tmp_path)
    _write_doc(root, "docs/prd/good.md", "---\nid: prd-good\ndoc_type: prd\n---\n# Good\n")
    indexer.main(["--project-root", str(root)])

    monkeypatch.chdir(root)
    via_validate = invoke_under_group(context_validate, [])
    via_index = invoke_under_group(context_index, ["--strict", "--dry-run"])

    assert via_validate.exit_code == via_index.exit_code == 0


def test_validate_equals_index_strict_dryrun_orphan(tmp_path: Path, monkeypatch) -> None:
    root = _minimal_project(tmp_path)
    _write_doc(root, "docs/prd/good.md", "---\nid: prd-good\ndoc_type: prd\n---\n# Good\n")
    indexer.main(["--project-root", str(root)])
    _write_doc(root, "docs/research/orphan.md", "# No front matter\n")

    monkeypatch.chdir(root)
    via_validate = invoke_under_group(context_validate, [])
    via_index = invoke_under_group(context_index, ["--strict", "--dry-run"])

    assert via_validate.exit_code == via_index.exit_code == 3


def test_index_dry_run_does_not_rebuild_index(tmp_path: Path, monkeypatch) -> None:
    """``--dry-run`` is a read-only gate: a doc added after the last build must
    not appear in the on-disk index after a dry-run."""
    root = _minimal_project(tmp_path)
    _write_doc(root, "docs/prd/good.md", "---\nid: prd-good\ndoc_type: prd\n---\n# Good\n")
    indexer.main(["--project-root", str(root)])
    _write_doc(root, "docs/prd/later.md", "---\nid: prd-later\ndoc_type: prd\n---\n# Later\n")

    monkeypatch.chdir(root)
    result = invoke_under_group(context_index, ["--dry-run"])

    assert result.exit_code == 0, result.output
    index = json.loads((root / "docs" / ".doc-index.json").read_text())
    assert "prd-later" not in index.get("documents", {})


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
    from cataforge.interface.cli.context.query import context_read
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
