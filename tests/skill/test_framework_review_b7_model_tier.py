"""B7 — model_tier audit (value enum + heavy whitelist + tier_map coverage)."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from cataforge.skill.builtins.framework_review.framework_check import (
    Report,
    check_b7_model_tier,
)


def _write_agent(tmp_path: Path, agent_id: str, frontmatter: dict) -> None:
    agent_dir = tmp_path / ".cataforge" / "agents" / agent_id
    agent_dir.mkdir(parents=True, exist_ok=True)
    fm_lines = [f"{k}: {v}" for k, v in frontmatter.items()]
    (agent_dir / "AGENT.md").write_text(
        "---\nname: " + agent_id + "\n"
        + "\n".join(fm_lines) + "\n---\n"
        f"# {agent_id}\n## Identity\n- test\n",
        encoding="utf-8",
    )


def _write_framework_json(
    tmp_path: Path,
    defaults: dict[str, str] | None = None,
    heavy_whitelist: list[str] | None = None,
) -> None:
    fw_dir = tmp_path / ".cataforge"
    fw_dir.mkdir(parents=True, exist_ok=True)
    consts: dict = {}
    if defaults is not None:
        consts["AGENT_MODEL_DEFAULTS"] = defaults
    if heavy_whitelist is not None:
        consts["AGENT_MODEL_TIER_HEAVY_WHITELIST"] = heavy_whitelist
    (fw_dir / "framework.json").write_text(
        json.dumps({"version": "test", "constants": consts}),
        encoding="utf-8",
    )


def _write_platform_profile(tmp_path: Path, pid: str, routing: dict) -> None:
    p = tmp_path / ".cataforge" / "platforms" / pid
    p.mkdir(parents=True, exist_ok=True)
    (p / "profile.yaml").write_text(
        yaml.safe_dump({"platform_id": pid, "model_routing": routing}),
        encoding="utf-8",
    )


def test_b7_valid_tier_no_finding(tmp_path: Path) -> None:
    _write_framework_json(
        tmp_path,
        defaults={"foo": "standard"},
        heavy_whitelist=[],
    )
    _write_agent(tmp_path, "foo", {"model_tier": "standard"})

    report = Report()
    check_b7_model_tier(tmp_path, report)
    findings = [f for f in report.findings if f.check_id == "B7_model_tier_value"]
    assert findings == []


def test_b7_invalid_enum_fails(tmp_path: Path) -> None:
    _write_framework_json(tmp_path, defaults={}, heavy_whitelist=[])
    _write_agent(tmp_path, "foo", {"model_tier": "extralarge"})

    report = Report()
    check_b7_model_tier(tmp_path, report)
    findings = [f for f in report.findings if f.check_id == "B7_model_tier_value"]
    assert len(findings) == 1
    assert findings[0].severity == "FAIL"
    assert "extralarge" in findings[0].message


def test_b7_heavy_without_whitelist_fails(tmp_path: Path) -> None:
    _write_framework_json(tmp_path, defaults={}, heavy_whitelist=[])
    _write_agent(tmp_path, "foo", {"model_tier": "heavy"})

    report = Report()
    check_b7_model_tier(tmp_path, report)
    findings = [
        f for f in report.findings
        if f.check_id == "B7_model_tier_value" and "heavy" in f.message
    ]
    assert len(findings) == 1
    assert findings[0].severity == "FAIL"


def test_b7_heavy_with_whitelist_passes(tmp_path: Path) -> None:
    _write_framework_json(
        tmp_path,
        defaults={"foo": "heavy"},
        heavy_whitelist=["foo"],
    )
    _write_agent(tmp_path, "foo", {"model_tier": "heavy"})

    report = Report()
    check_b7_model_tier(tmp_path, report)
    findings = [f for f in report.findings if f.check_id == "B7_model_tier_value"]
    assert findings == []


def test_b7_tier_diverges_from_default_warns(tmp_path: Path) -> None:
    _write_framework_json(
        tmp_path,
        defaults={"foo": "standard"},
        heavy_whitelist=[],
    )
    _write_agent(tmp_path, "foo", {"model_tier": "light"})

    report = Report()
    check_b7_model_tier(tmp_path, report)
    findings = [
        f for f in report.findings
        if f.check_id == "B7_model_tier_value" and "diverges" in f.message
    ]
    assert len(findings) == 1
    assert findings[0].severity == "WARN"


def test_b7_legacy_model_field_fails(tmp_path: Path) -> None:
    """Direct migration: legacy `model:` without `model_tier:` is FAIL."""
    _write_framework_json(tmp_path, defaults={}, heavy_whitelist=[])
    _write_agent(tmp_path, "foo", {"model": "sonnet"})

    report = Report()
    check_b7_model_tier(tmp_path, report)
    findings = [f for f in report.findings if f.check_id == "B7_legacy_model_field"]
    assert len(findings) == 1
    assert findings[0].severity == "FAIL"
    assert "sonnet" in findings[0].message


def test_b7_legacy_model_with_tier_does_not_fail(tmp_path: Path) -> None:
    """If model_tier: is present, the legacy `model:` line is acceptable in
    source (translator strips it). Don't double-FAIL."""
    _write_framework_json(
        tmp_path,
        defaults={"foo": "standard"},
        heavy_whitelist=[],
    )
    _write_agent(
        tmp_path, "foo",
        {"model": "sonnet", "model_tier": "standard"},
    )

    report = Report()
    check_b7_model_tier(tmp_path, report)
    findings = [f for f in report.findings if f.check_id == "B7_legacy_model_field"]
    assert findings == []


def test_b7_platform_tier_map_complete_passes(tmp_path: Path) -> None:
    _write_framework_json(tmp_path, defaults={}, heavy_whitelist=[])
    _write_platform_profile(
        tmp_path, "claude-like",
        {
            "per_agent_model": True,
            "user_resolved": False,
            "tier_map": {"light": "haiku", "standard": "sonnet", "heavy": "opus"},
        },
    )

    report = Report()
    check_b7_model_tier(tmp_path, report)
    findings = [f for f in report.findings if f.check_id == "B7_platform_tier_map"]
    assert findings == []


def test_b7_platform_tier_map_missing_warns(tmp_path: Path) -> None:
    _write_framework_json(tmp_path, defaults={}, heavy_whitelist=[])
    _write_platform_profile(
        tmp_path, "claude-like",
        {
            "per_agent_model": True,
            "user_resolved": False,
            "tier_map": {"light": "haiku"},  # standard / heavy missing
        },
    )

    report = Report()
    check_b7_model_tier(tmp_path, report)
    findings = [f for f in report.findings if f.check_id == "B7_platform_tier_map"]
    assert len(findings) == 1
    assert findings[0].severity == "WARN"
    assert "standard" in findings[0].message
    assert "heavy" in findings[0].message


def test_b7_platform_per_agent_false_skipped(tmp_path: Path) -> None:
    """per_agent_model=false → no tier_map check (deploy never writes model:)."""
    _write_framework_json(tmp_path, defaults={}, heavy_whitelist=[])
    _write_platform_profile(
        tmp_path, "codex-like",
        {
            "per_agent_model": False,
            "user_resolved": False,
            "tier_map": {},
        },
    )

    report = Report()
    check_b7_model_tier(tmp_path, report)
    findings = [f for f in report.findings if f.check_id == "B7_platform_tier_map"]
    assert findings == []


def test_b7_platform_user_resolved_skipped(tmp_path: Path) -> None:
    """user_resolved=true → no tier_map check (provider-agnostic)."""
    _write_framework_json(tmp_path, defaults={}, heavy_whitelist=[])
    _write_platform_profile(
        tmp_path, "opencode-like",
        {
            "per_agent_model": True,
            "user_resolved": True,
            "tier_map": {},
        },
    )

    report = Report()
    check_b7_model_tier(tmp_path, report)
    findings = [f for f in report.findings if f.check_id == "B7_platform_tier_map"]
    assert findings == []
