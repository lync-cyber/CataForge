"""Tests for deploy-time agent language-fragment injection (P4.2)."""

from __future__ import annotations

from pathlib import Path

from cataforge.core.paths import ProjectPaths
from cataforge.runtime.deploy.lang_fragments import (
    inject_into_staged_agents,
    inject_lang_fragments,
)


def _fragment(root: Path, agent_id: str, lang: str, body: str = "# guidance\n") -> None:
    d = root / ".cataforge" / "agents" / agent_id / "rules"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"lang-{lang}.md").write_text(body, encoding="utf-8")


def test_inject_links_existing_fragments_only(tmp_path: Path) -> None:
    _fragment(tmp_path, "arch", "python")
    paths = ProjectPaths(tmp_path)
    out = inject_lang_fragments("# Role\n\n## Identity\n- x\n", "arch", ["python", "go"], paths)
    assert "## 语言细则" in out
    assert ".cataforge/agents/arch/rules/lang-python.md" in out
    assert "lang-go" not in out  # no go fragment shipped


def test_inject_noop_without_fragments(tmp_path: Path) -> None:
    paths = ProjectPaths(tmp_path)
    md = "# Role\n\n## Identity\n- x\n"
    assert inject_lang_fragments(md, "arch", ["python"], paths) == md


def test_inject_into_staged_only_lang_aware(tmp_path: Path) -> None:
    _fragment(tmp_path, "aware", "python")
    paths = ProjectPaths(tmp_path)
    staged = tmp_path / "staged" / "agents"
    (staged / "aware").mkdir(parents=True)
    (staged / "aware" / "AGENT.md").write_text(
        "---\nname: aware\nlang_aware: true\n---\n\n## Identity\n- a\n", encoding="utf-8"
    )
    (staged / "plain").mkdir(parents=True)
    (staged / "plain" / "AGENT.md").write_text(
        "---\nname: plain\n---\n\n## Identity\n- b\n", encoding="utf-8"
    )

    injected = inject_into_staged_agents(staged, ["python"], paths)
    assert injected == ["aware"]
    assert "## 语言细则" in (staged / "aware" / "AGENT.md").read_text(encoding="utf-8")
    assert "## 语言细则" not in (staged / "plain" / "AGENT.md").read_text(encoding="utf-8")


def test_inject_noop_empty_langs(tmp_path: Path) -> None:
    assert inject_into_staged_agents(tmp_path, [], ProjectPaths(tmp_path)) == []
