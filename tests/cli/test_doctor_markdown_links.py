"""doctor markdown-link resolution gate.

``cataforge deploy`` materializes only ``.cataforge/**`` downstream; a
prompt-asset markdown link to repo-root ``docs/`` resolves to a path that does
not ship. The gate flags such links (and links to files missing inside the
tree) so the deployable-asset boundary stays closed. Templates are exempt —
their links resolve against the generated ``docs/`` tree, not ``.cataforge/``.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from cataforge.interface.cli.doctor.protocol_refs import check_markdown_link_resolution


def _cfg(root: Path) -> SimpleNamespace:
    cf = root / ".cataforge"
    return SimpleNamespace(
        paths=SimpleNamespace(
            root=root,
            agents_dir=cf / "agents",
            skills_dir=cf / "skills",
            rules_dir=cf / "rules",
        )
    )


def _skill(root: Path, name: str, body: str) -> None:
    d = root / ".cataforge" / "skills" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(f"# {name}\n\n{body}\n", encoding="utf-8")


def _reference(root: Path, name: str) -> None:
    d = root / ".cataforge" / "references"
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text("# ref\n", encoding="utf-8")


def test_link_to_deployed_reference_is_clean(tmp_path: Path, capsys) -> None:
    _reference(tmp_path, "wiring-checks.md")
    _skill(tmp_path, "code-review", "判定见 [wiring-checks.md](../../references/wiring-checks.md)")

    rc = check_markdown_link_resolution(_cfg(tmp_path))
    out = capsys.readouterr().out

    assert rc == 0
    assert "resolve within the deployed tree" in out


def test_link_escaping_cataforge_is_flagged(tmp_path: Path, capsys) -> None:
    _skill(tmp_path, "code-review", "见 [w](../../../docs/reference/wiring-checks.md)")

    rc = check_markdown_link_resolution(_cfg(tmp_path))
    out = capsys.readouterr().out

    assert rc == 1
    assert "escapes .cataforge/" in out
    assert "skills/code-review/SKILL.md" in out


def test_link_to_missing_file_in_tree_is_flagged(tmp_path: Path, capsys) -> None:
    _skill(tmp_path, "debug", "见 [p](references/missing.md)")

    rc = check_markdown_link_resolution(_cfg(tmp_path))
    out = capsys.readouterr().out

    assert rc == 1
    assert "target missing" in out


def test_external_anchor_and_placeholder_links_ignored(tmp_path: Path) -> None:
    _skill(
        tmp_path,
        "x",
        "[site](https://example.com) [a](#section) "
        "[m](mailto:a@b.c) [g](references/lang-<lang>.md)",
    )

    rc = check_markdown_link_resolution(_cfg(tmp_path))

    assert rc == 0


def test_template_links_are_exempt(tmp_path: Path) -> None:
    # A template's relative links resolve against the generated docs/ tree.
    d = tmp_path / ".cataforge" / "skills" / "context" / "templates"
    d.mkdir(parents=True, exist_ok=True)
    (d / "prd.md").write_text("见 [arch](../../../../docs/arch/arch.md)\n", encoding="utf-8")

    rc = check_markdown_link_resolution(_cfg(tmp_path))

    assert rc == 0
