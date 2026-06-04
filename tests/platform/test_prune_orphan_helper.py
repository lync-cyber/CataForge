"""Unit tests for _prune_orphan_flat_files helper."""

from __future__ import annotations

from pathlib import Path

from cataforge.adapter.platform.fileops import _prune_orphan_flat_files


def _write(directory: Path, name: str, content: str) -> Path:
    p = directory / name
    p.write_text(content, encoding="utf-8")
    return p


# ---- core pruning behaviour --------------------------------------------------


def test_removes_orphan_with_matching_signature(tmp_path: Path) -> None:
    known: set[str] = {"current"}
    _write(tmp_path, "current.md", "name: current\nbody\n")
    orphan = _write(tmp_path, "retired.md", "name: retired\nold body\n")

    actions = _prune_orphan_flat_files(tmp_path, known, ".md", "name: {stem}", "agents")

    assert not orphan.exists()
    assert set(tmp_path.iterdir()) == {tmp_path / "current.md"}
    assert any("pruned orphan" in a and "retired.md" in a for a in actions)


def test_preserves_file_without_matching_signature(tmp_path: Path) -> None:
    known: set[str] = set()
    user_file = _write(tmp_path, "notes.md", "# user notes\n")

    actions = _prune_orphan_flat_files(tmp_path, known, ".md", "name: {stem}", "agents")

    assert user_file.exists()
    assert actions == []


def test_preserves_known_name_even_with_signature(tmp_path: Path) -> None:
    known = {"active"}
    active = _write(tmp_path, "active.md", "name: active\nbody\n")

    actions = _prune_orphan_flat_files(tmp_path, known, ".md", "name: {stem}", "agents")

    assert active.exists()
    assert actions == []


def test_empty_known_names_removes_all_matching(tmp_path: Path) -> None:
    known: set[str] = set()
    a = _write(tmp_path, "alpha.md", "name: alpha\n")
    b = _write(tmp_path, "beta.md", "name: beta\n")

    actions = _prune_orphan_flat_files(tmp_path, known, ".md", "name: {stem}", "agents")

    assert not a.exists()
    assert not b.exists()
    assert set(tmp_path.iterdir()) == set()
    assert len([x for x in actions if "pruned orphan" in x]) == 2


# ---- extension filtering -----------------------------------------------------


def test_ignores_wrong_extension(tmp_path: Path) -> None:
    known: set[str] = set()
    toml_file = _write(tmp_path, "agent.toml", "# Auto-generated from agent/AGENT.md\n")

    actions = _prune_orphan_flat_files(tmp_path, known, ".md", "name: {stem}", "agents")

    assert toml_file.exists()
    assert actions == []


def test_toml_signature_variant(tmp_path: Path) -> None:
    known: set[str] = set()
    orphan = _write(
        tmp_path, "retired.toml", '# Auto-generated from retired/AGENT.md\nname = "retired"\n'
    )
    user_toml = _write(tmp_path, "manual.toml", 'name = "manual"\n')

    actions = _prune_orphan_flat_files(
        tmp_path,
        known,
        ".toml",
        "# Auto-generated from {stem}/AGENT.md",
        ".codex/agents",
        head_read_size=256,
    )

    assert not orphan.exists()
    assert user_toml.exists()
    assert any("pruned orphan" in a and "retired.toml" in a for a in actions)


# ---- head_read_size ----------------------------------------------------------


def test_head_signature_beyond_read_window_preserves_file(tmp_path: Path) -> None:
    known: set[str] = set()
    padding = "x" * 300
    candidate = _write(tmp_path, "agent.md", padding + "name: agent\n")

    actions = _prune_orphan_flat_files(
        tmp_path, known, ".md", "name: {stem}", "agents", head_read_size=256
    )

    assert candidate.exists(), "signature outside read window must not be pruned"
    assert actions == []


# ---- dry_run -----------------------------------------------------------------


def test_dry_run_does_not_delete(tmp_path: Path) -> None:
    known: set[str] = set()
    orphan = _write(tmp_path, "old.md", "name: old\n")

    actions = _prune_orphan_flat_files(
        tmp_path, known, ".md", "name: {stem}", "agents", dry_run=True
    )

    assert orphan.exists(), "dry-run must not delete"
    assert any("would prune orphan" in a and "old.md" in a for a in actions)


# ---- missing directory -------------------------------------------------------


def test_nonexistent_directory_returns_empty(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist"

    actions = _prune_orphan_flat_files(missing, set(), ".md", "name: {stem}", "agents")

    assert actions == []


# ---- precise residual set assertion ------------------------------------------


def test_exact_residual_set_after_mixed_prune(tmp_path: Path) -> None:
    known = {"keep-a", "keep-b"}
    keep_a = _write(tmp_path, "keep-a.md", "name: keep-a\n")
    keep_b = _write(tmp_path, "keep-b.md", "name: keep-b\n")
    _write(tmp_path, "orphan-x.md", "name: orphan-x\n")
    user_y = _write(tmp_path, "user-y.md", "# plain user file\n")

    _prune_orphan_flat_files(tmp_path, known, ".md", "name: {stem}", "agents")

    assert set(tmp_path.iterdir()) == {keep_a, keep_b, user_y}
