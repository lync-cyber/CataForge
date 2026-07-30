from __future__ import annotations

from pathlib import Path

from cataforge.adapter.platform.registry import get_adapter
from cataforge.runtime.deploy.capability_report import (
    build_capability_report,
    load_capability_report,
    write_capability_report,
)


def _write_agent(root: Path) -> Path:
    agents = root / ".cataforge" / "agents"
    source = agents / "reviewer" / "AGENT.md"
    source.parent.mkdir(parents=True)
    source.write_text(
        "---\n"
        "name: reviewer\n"
        "tools: file_read, file_grep\n"
        "disallowedTools: file_write, file_edit\n"
        "---\n"
        "Review only.\n",
        encoding="utf-8",
    )
    return agents


def test_codex_report_records_conditional_hook_and_enforcement(tmp_path: Path) -> None:
    adapter = get_adapter("codex")
    report = build_capability_report(adapter, _write_agent(tmp_path))

    assert report["agent_tool_policy"] == "inherit_only"
    assert report["capabilities"]["user_question"]["status"] == "conditional"
    assert report["capabilities"]["web_fetch"]["status"] == "replacement"
    assert report["hooks"]["detect_correction"]["mode"] == "hybrid"
    assert report["hooks"]["detect_correction"]["fallback"]["coverage"] == "partial"

    reviewer = report["agents"]["reviewer"]
    assert reviewer["sandbox_mode"] == "read-only"
    assert reviewer["allowed_tools"] == []
    assert reviewer["denied_tools"] == []
    assert reviewer["unenforced"] == ["file_grep", "file_read"]


def test_capability_report_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "state" / "capability-report.json"
    write_capability_report(path, get_adapter("codex"), _write_agent(tmp_path))

    loaded = load_capability_report(path)
    assert loaded is not None
    assert loaded["report_version"] == 1
    assert loaded["platform"] == "codex"
