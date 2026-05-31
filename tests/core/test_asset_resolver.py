"""Tests for layered asset resolution (runtime.assets.resolver)."""

from __future__ import annotations

from pathlib import Path

from cataforge.core.paths import ProjectPaths
from cataforge.runtime.assets.resolver import resolve_kind


def _write(root: Path, rel: str, body: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")


_AGENT = """\
---
name: architect
---

# Role

## Identity
- base identity

## Rules
- base rule
"""


def test_whole_file_override_from_user_layer(tmp_path: Path) -> None:
    _write(tmp_path, ".cataforge/agents/architect/AGENT.md", _AGENT)
    _write(
        tmp_path,
        ".cataforge/overrides/user/agents/architect/AGENT.md",
        "---\nname: architect\n---\n\n# Role\n\n## Identity\n- user identity\n",
    )
    dest = tmp_path / "staged" / "agents"
    ids = resolve_kind(ProjectPaths(tmp_path), "agents", dest)

    assert ids == ["architect"]
    out = (dest / "architect" / "AGENT.md").read_text(encoding="utf-8")
    assert "user identity" in out
    assert "base identity" not in out


def test_section_patch_overrides_and_adds(tmp_path: Path) -> None:
    _write(tmp_path, ".cataforge/agents/architect/AGENT.md", _AGENT)
    _write(
        tmp_path,
        ".cataforge/overrides/project/agents/architect/AGENT.patch.md",
        "## Rules\n- patched rule\n\n## Project Extra\n- new section\n",
    )
    dest = tmp_path / "staged" / "agents"
    resolve_kind(ProjectPaths(tmp_path), "agents", dest)

    out = (dest / "architect" / "AGENT.md").read_text(encoding="utf-8")
    assert "patched rule" in out
    assert "base rule" not in out
    assert "## Project Extra" in out
    # Untouched section + frontmatter preserved.
    assert "base identity" in out
    assert out.startswith("---\nname: architect\n")


def test_user_patch_layers_on_project_whole_file(tmp_path: Path) -> None:
    """user > project: a user patch applies on top of a project whole-file override."""
    _write(tmp_path, ".cataforge/agents/architect/AGENT.md", _AGENT)
    _write(
        tmp_path,
        ".cataforge/overrides/project/agents/architect/AGENT.md",
        "---\nname: architect\n---\n\n# Role\n\n## Identity\n- project identity\n\n"
        "## Rules\n- project rule\n",
    )
    _write(
        tmp_path,
        ".cataforge/overrides/user/agents/architect/AGENT.patch.md",
        "## Rules\n- user rule\n",
    )
    dest = tmp_path / "staged" / "agents"
    resolve_kind(ProjectPaths(tmp_path), "agents", dest)

    out = (dest / "architect" / "AGENT.md").read_text(encoding="utf-8")
    assert "project identity" in out  # from project whole-file
    assert "user rule" in out  # user patch wins on Rules
    assert "project rule" not in out


def test_new_sibling_file_added_by_override(tmp_path: Path) -> None:
    _write(tmp_path, ".cataforge/agents/architect/AGENT.md", _AGENT)
    _write(
        tmp_path,
        ".cataforge/overrides/user/agents/architect/EXTRA-PROTOCOLS.md",
        "# Extra protocols\n",
    )
    dest = tmp_path / "staged" / "agents"
    resolve_kind(ProjectPaths(tmp_path), "agents", dest)

    assert (dest / "architect" / "AGENT.md").is_file()
    assert (dest / "architect" / "EXTRA-PROTOCOLS.md").read_text(encoding="utf-8") == (
        "# Extra protocols\n"
    )


def test_brand_new_agent_only_in_override(tmp_path: Path) -> None:
    _write(tmp_path, ".cataforge/agents/architect/AGENT.md", _AGENT)
    _write(
        tmp_path,
        ".cataforge/overrides/project/agents/custom-bot/AGENT.md",
        "---\nname: custom-bot\n---\n\n# Role\n\n## Identity\n- bespoke\n",
    )
    dest = tmp_path / "staged" / "agents"
    ids = resolve_kind(ProjectPaths(tmp_path), "agents", dest)

    assert ids == ["architect", "custom-bot"]
    assert "bespoke" in (dest / "custom-bot" / "AGENT.md").read_text(encoding="utf-8")


def test_no_layers_returns_empty(tmp_path: Path) -> None:
    (tmp_path / ".cataforge").mkdir()
    dest = tmp_path / "staged" / "agents"
    assert resolve_kind(ProjectPaths(tmp_path), "agents", dest) == []


def test_orphan_patch_not_materialized_as_real_asset(
    tmp_path: Path, caplog
) -> None:
    """A ``<typo>.patch.md`` with no base ``<typo>.md`` in any layer is an
    orphan (typo'd patch name) — it must be skipped + logged, never written
    out verbatim as a real ``<typo>.md`` asset."""
    import logging

    _write(tmp_path, ".cataforge/agents/architect/AGENT.md", _AGENT)
    # Typo: base is AGENT.md, patch is mis-named orchestrater.patch.md → no
    # orchestrater.md to patch.
    _write(
        tmp_path,
        ".cataforge/overrides/project/agents/architect/orchestrater.patch.md",
        "## Bogus\n- should not ship\n",
    )
    dest = tmp_path / "staged" / "agents"
    with caplog.at_level(logging.WARNING, logger="cataforge.runtime.assets.resolver"):
        resolve_kind(ProjectPaths(tmp_path), "agents", dest)

    # The orphan patch is NOT written as a standalone asset ...
    assert not (dest / "architect" / "orchestrater.md").exists()
    assert not (dest / "architect" / "orchestrater.patch.md").exists()
    assert "should not ship" not in (
        dest / "architect" / "AGENT.md"
    ).read_text(encoding="utf-8")
    # ... and the skip is surfaced as a diagnostic.
    assert any(
        "orphan patch" in r.message or "orphan patch" in r.getMessage()
        for r in caplog.records
    ), f"no orphan-patch warning logged: {[r.getMessage() for r in caplog.records]}"


def test_patch_with_base_still_applies(tmp_path: Path) -> None:
    """Regression guard for the orphan check: a patch WITH a matching base in
    a lower layer still patches normally (the legitimate path is untouched)."""
    _write(tmp_path, ".cataforge/agents/architect/AGENT.md", _AGENT)
    _write(
        tmp_path,
        ".cataforge/overrides/project/agents/architect/AGENT.patch.md",
        "## Rules\n- patched rule\n",
    )
    dest = tmp_path / "staged" / "agents"
    resolve_kind(ProjectPaths(tmp_path), "agents", dest)
    out = (dest / "architect" / "AGENT.md").read_text(encoding="utf-8")
    assert "patched rule" in out
    assert "base rule" not in out
