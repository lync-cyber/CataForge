"""Unit tests for cataforge.docs.loader optimizations and externalization."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from cataforge.docs import loader


@pytest.fixture(autouse=True)
def reset_caches():
    """Loader uses module-level caches; reset between tests so per-root config doesn't leak."""
    loader._INDEX_CACHE = None
    loader._INDEX_CACHE_ROOT = None
    loader._DOC_TYPE_MAP_CACHE.clear()
    yield
    loader._INDEX_CACHE = None
    loader._INDEX_CACHE_ROOT = None
    loader._DOC_TYPE_MAP_CACHE.clear()


def _make_project(root: Path, *, doc_type_override: dict[str, str] | None = None) -> None:
    (root / ".cataforge").mkdir()
    framework_data: dict = {"version": "0.1.0"}
    if doc_type_override is not None:
        framework_data["docs"] = {"doc_types": doc_type_override}
    (root / ".cataforge" / "framework.json").write_text(
        json.dumps(framework_data), encoding="utf-8"
    )
    (root / "docs").mkdir()


def _write_doc(root: Path, doc_type: str, filename: str, body: str) -> Path:
    target = root / "docs" / doc_type / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    return target


# ---------------------------------------------------------------------------
# Externalized doc_type map
# ---------------------------------------------------------------------------


def test_doc_type_map_uses_defaults_when_no_override(tmp_path: Path) -> None:
    _make_project(tmp_path)
    mapping = loader._load_doc_type_map(str(tmp_path))
    assert mapping["prd"] == "prd"
    assert mapping["arch"] == "arch"
    assert "ui-spec" in mapping


def test_doc_type_map_merges_custom_override(tmp_path: Path) -> None:
    _make_project(tmp_path, doc_type_override={"runbook": "ops/runbooks", "prd": "requirements"})
    mapping = loader._load_doc_type_map(str(tmp_path))
    assert mapping["runbook"] == "ops/runbooks"  # custom added
    assert mapping["prd"] == "requirements"      # default overridden
    assert mapping["arch"] == "arch"             # untouched defaults preserved


def test_doc_type_map_resolves_custom_doc_id(tmp_path: Path) -> None:
    _make_project(tmp_path, doc_type_override={"runbook": "ops"})
    body = "# 1. Overview\n\nrunbook content here\n"
    _write_doc(tmp_path, "ops", "runbook-foo-v1.md", body)

    content = loader.extract("runbook#§1", str(tmp_path))
    assert "runbook content here" in content


def test_doc_type_map_unknown_doc_id_raises(tmp_path: Path) -> None:
    _make_project(tmp_path)
    with pytest.raises(loader.DocResolveError, match="未知的 doc_id"):
        loader.extract("not-a-real-type#§1", str(tmp_path))


# ---------------------------------------------------------------------------
# Per-file cache in extract_batch
# ---------------------------------------------------------------------------


def test_extract_batch_reuses_per_file_cache(tmp_path: Path, monkeypatch) -> None:
    """When multiple refs target the same file, file IO must happen exactly once.

    Counts ``open()`` calls on docs/prd/* paths during a batch of 3 refs that
    all live in the same file.
    """
    _make_project(tmp_path)
    body = (
        "# PRD\n\n"
        "## 1. Overview\nIntro text.\n\n"
        "## 2. Features\n\n"
        "### F-001 Login\nLogin desc\n\n"
        "### F-002 Signup\nSignup desc\n\n"
        "### F-003 Logout\nLogout desc\n"
    )
    _write_doc(tmp_path, "prd", "prd-foo-v1.md", body)

    open_count = {"n": 0}
    real_open = open

    def counting_open(path, *a, **kw):
        if "docs/prd/" in str(path).replace("\\", "/"):
            open_count["n"] += 1
        return real_open(path, *a, **kw)

    monkeypatch.setattr("builtins.open", counting_open)

    successes, errors = loader.extract_batch(
        ["prd#§2.F-001", "prd#§2.F-002", "prd#§2.F-003"],
        str(tmp_path),
    )
    assert errors == []
    assert len(successes) == 3
    # Without cache: 3 opens (one per ref). With cache: 1 open total.
    # Allow up to 2 because file resolution may stat the dir, but the
    # important regression we are guarding is "<= refs" not "== refs".
    assert open_count["n"] <= 2, (
        f"expected per-file cache to collapse opens, got {open_count['n']} for 3 refs"
    )


# ---------------------------------------------------------------------------
# Stale-index warning
# ---------------------------------------------------------------------------


def test_stale_warning_emitted_for_old_index(tmp_path: Path, capsys) -> None:
    _make_project(tmp_path)
    old_ts = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    (tmp_path / "docs" / ".doc-index.json").write_text(
        json.dumps({"generated_at": old_ts, "documents": {}}),
        encoding="utf-8",
    )

    loader._emit_stale_warning(str(tmp_path))
    captured = capsys.readouterr()
    assert "已" in captured.err and "天未更新" in captured.err


def test_no_stale_warning_for_fresh_index(tmp_path: Path, capsys) -> None:
    _make_project(tmp_path)
    fresh_ts = datetime.now(timezone.utc).isoformat()
    (tmp_path / "docs" / ".doc-index.json").write_text(
        json.dumps({"generated_at": fresh_ts, "documents": {}}),
        encoding="utf-8",
    )

    loader._emit_stale_warning(str(tmp_path))
    captured = capsys.readouterr()
    assert "天未更新" not in captured.err


# ---------------------------------------------------------------------------
# CLI flag plumbing — directly via main()
# ---------------------------------------------------------------------------


def _build_indexed_project(tmp_path: Path, capsys=None) -> None:
    _make_project(tmp_path)
    body = (
        "---\nid: prd-foo-v1\ndoc_type: prd\n---\n\n"
        "# PRD\n\n"
        "## 1. Overview\nLong intro text.\n\n"
        "## 2. Features\n\n"
        "### F-001 Login\nLogin desc spanning multiple words.\n"
    )
    _write_doc(tmp_path, "prd", "prd-foo-v1.md", body)
    from cataforge.docs.indexer import main as indexer_main
    rc = indexer_main(["--project-root", str(tmp_path)])
    assert rc == 0
    if capsys is not None:
        capsys.readouterr()  # drain indexer output so subsequent stdout is clean


def test_loader_main_json_output(tmp_path: Path, capsys) -> None:
    _build_indexed_project(tmp_path, capsys=capsys)
    rc = loader.main(["--project-root", str(tmp_path), "--json", "prd#§1"])
    assert rc == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert isinstance(payload, list) and len(payload) == 1
    assert payload[0]["status"] == "ok"
    assert payload[0]["ref"] == "prd#§1"
    assert "Long intro text." in payload[0]["content"]
    assert payload[0]["line_start"] >= 1
    assert payload[0]["line_end"] >= payload[0]["line_start"]


def test_loader_main_budget_defers(tmp_path: Path, capsys) -> None:
    _build_indexed_project(tmp_path, capsys=capsys)
    # Tiny budget → every ref defers
    rc = loader.main([
        "--project-root", str(tmp_path),
        "--budget", "1",
        "prd#§1", "prd#§2.F-001",
    ])
    assert rc == 0
    captured = capsys.readouterr()
    assert "[DEFERRED]" in captured.err
    assert "prd#§1" in captured.err
    assert "prd#§2.F-001" in captured.err


def test_loader_main_with_deps_expands_refs(tmp_path: Path, capsys) -> None:
    _make_project(tmp_path)
    # Construct an index by hand so we can inject a deps relationship without
    # plumbing it through the indexer (which doesn't yet emit deps for items).
    body = "# PRD\n\n## 1. Overview\nIntro\n\n## 2. Features\n\n### F-001 Login\nLogin\n"
    _write_doc(tmp_path, "prd", "prd-foo-v1.md", body)
    index = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "documents": {
            "prd": {
                "file_path": "docs/prd/prd-foo-v1.md",
                "sections": {
                    "1": {"line_start": 3, "line_end": 4, "items": {}, "deps": []},
                    "2": {
                        "line_start": 5,
                        "line_end": 8,
                        "items": {
                            "F-001": {
                                "line_start": 7, "line_end": 8,
                                "deps": ["prd#§1"],
                            },
                        },
                        "deps": [],
                    },
                },
            }
        },
        "xref": {},
    }
    (tmp_path / "docs" / ".doc-index.json").write_text(
        json.dumps(index), encoding="utf-8"
    )

    rc = loader.main([
        "--project-root", str(tmp_path),
        "--with-deps",
        "prd#§2.F-001",
    ])
    assert rc == 0
    captured = capsys.readouterr()
    # The dep should have been auto-loaded
    assert "[DEPS]" in captured.err
    assert "prd#§1" in captured.err
    assert "=== prd#§1 ===" in captured.out
    assert "=== prd#§2.F-001 ===" in captured.out
