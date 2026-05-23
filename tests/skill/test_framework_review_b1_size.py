"""B1-β size threshold coverage.

Specifically covers the path where agent companion ``*PROTOCOL*.md``
docs live next to AGENT.md and are loaded as prompt context per
CLAUDE.md §硬约束 1. The check must scan them, not just AGENT.md.
"""

from __future__ import annotations

from pathlib import Path

from cataforge.skill.builtins.framework_review.framework_check import (
    Report,
    check_b1_size,
    discover_agent_protocol_docs,
)


def _build_agent(
    tmp_path: Path,
    agent_id: str,
    *,
    agent_lines: int,
    protocol_lines: int | None = None,
    protocol_name: str = "ORCHESTRATOR-PROTOCOLS.md",
) -> Path:
    """Create a tmp agent dir with AGENT.md and optional PROTOCOL companion."""
    agent_dir = tmp_path / ".cataforge" / "agents" / agent_id
    agent_dir.mkdir(parents=True)
    (agent_dir / "AGENT.md").write_text(
        "\n".join(["x"] * agent_lines), encoding="utf-8"
    )
    if protocol_lines is not None:
        (agent_dir / protocol_name).write_text(
            "\n".join(["y"] * protocol_lines), encoding="utf-8"
        )
    return tmp_path


def test_discover_agent_protocol_docs_picks_up_companion(tmp_path: Path) -> None:
    """Companion *PROTOCOL*.md should be discovered alongside AGENT.md."""
    _build_agent(tmp_path, "orchestrator", agent_lines=10, protocol_lines=600)
    found = discover_agent_protocol_docs(tmp_path)
    assert len(found) == 1
    label, path = found[0]
    assert label == "agents/orchestrator/ORCHESTRATOR-PROTOCOLS.md"
    assert path.name == "ORCHESTRATOR-PROTOCOLS.md"


def test_discover_agent_protocol_docs_matches_singular_and_plural(
    tmp_path: Path,
) -> None:
    """Both PROTOCOL.md and PROTOCOLS.md should match (the glob is *PROTOCOL*)."""
    _build_agent(
        tmp_path,
        "a1",
        agent_lines=10,
        protocol_lines=20,
        protocol_name="MY-PROTOCOL.md",
    )
    _build_agent(
        tmp_path,
        "a2",
        agent_lines=10,
        protocol_lines=20,
        protocol_name="SOMETHING-PROTOCOLS.md",
    )
    found_paths = {label for label, _ in discover_agent_protocol_docs(tmp_path)}
    assert "agents/a1/MY-PROTOCOL.md" in found_paths
    assert "agents/a2/SOMETHING-PROTOCOLS.md" in found_paths


def test_b1_size_flags_oversize_protocol_companion(tmp_path: Path) -> None:
    """A 600-line PROTOCOLS.md must trigger B1-β even when AGENT.md is small."""
    _build_agent(tmp_path, "orchestrator", agent_lines=50, protocol_lines=600)
    report = Report()
    check_b1_size(tmp_path, scope="all", threshold=500, report=report)
    over = [
        f
        for f in report.findings
        if f.check_id == "B1_size_threshold"
        and f.location == "agents/orchestrator/ORCHESTRATOR-PROTOCOLS.md"
    ]
    assert len(over) == 1
    assert over[0].severity == "WARN"
    assert "600" in over[0].message


def test_b1_size_ignores_protocol_below_threshold(tmp_path: Path) -> None:
    """A PROTOCOLS.md within threshold should not trigger any finding."""
    _build_agent(tmp_path, "orchestrator", agent_lines=50, protocol_lines=400)
    report = Report()
    check_b1_size(tmp_path, scope="all", threshold=500, report=report)
    assert report.findings == []


def test_b1_size_scope_skills_skips_agent_protocols(tmp_path: Path) -> None:
    """scope=skills should not pick up agent protocol docs."""
    _build_agent(tmp_path, "orchestrator", agent_lines=50, protocol_lines=600)
    report = Report()
    check_b1_size(tmp_path, scope="skills", threshold=500, report=report)
    assert report.findings == []
