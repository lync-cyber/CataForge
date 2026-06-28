"""Regression guards for CLAUDE.md project-state hygiene discipline."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_orchestrator_protocol_defines_project_state_write_discipline() -> None:
    text = (
        REPO_ROOT / ".cataforge" / "agents" / "orchestrator" / "ORCHESTRATOR-PROTOCOLS.md"
    ).read_text(encoding="utf-8")

    assert "项目状态写入纪律" in text
    assert "实时状态" in text
    assert "docs/EVENT-LOG.jsonl" in text
    assert "docs/reviews/" in text
    assert "docs/changelog/" in text


def test_claude_md_hygiene_does_not_claim_state_schema_is_bounded() -> None:
    text = (REPO_ROOT / "src" / "cataforge" / "core" / "claude_md_hygiene.py").read_text(
        encoding="utf-8"
    )

    assert "bounded by design" not in text
    assert "does not rewrite them automatically" in text
