"""render_text signal-to-noise (P5): group by category, surface all
gating findings, cap the informational tail (full list via --verbose /
--format json). JSON stays the untruncated Layer 2 contract."""

from __future__ import annotations

import json

from cataforge.runtime.skill.builtins.code_review.engine.findings import (
    Finding,
    PipelineResult,
    render_json,
    render_text,
)


def _result_with_info_flood() -> PipelineResult:
    r = PipelineResult(mode="scan", target="src")
    r.checks_run = ["code_review.complexity_gate"]
    r.findings.append(Finding("code_review.eslint", "fail", "convention", "ESLint boom", "a.js", 1))
    r.findings.append(
        Finding("code_review.complexity_gate", "warn", "complexity", "warned", "b.py", 2)
    )
    for i in range(15):
        r.findings.append(
            Finding(
                "code_review.complexity_gate",
                "info",
                "complexity",
                f"fn{i}: cognitive=20",
                "c.py",
                i + 1,
            )
        )
    return r


def test_render_groups_by_category() -> None:
    text = render_text(_result_with_info_flood())
    assert "── complexity:" in text
    assert "── convention:" in text
    assert "RESULT: FAIL" in text


def test_render_caps_info_tail_by_default() -> None:
    text = render_text(_result_with_info_flood())
    shown = text.count("INFO:")
    assert shown == 10  # capped
    assert "还有 5 条" in text


def test_render_verbose_shows_all_info() -> None:
    text = render_text(_result_with_info_flood(), verbose=True)
    assert text.count("INFO:") == 15
    assert "还有" not in text


def test_render_always_shows_gating_findings() -> None:
    text = render_text(_result_with_info_flood())
    assert "FAIL:" in text  # gating finding never truncated
    assert "WARN:" in text


def test_json_untruncated_regardless_of_flood() -> None:
    payload = json.loads(render_json(_result_with_info_flood()))
    assert len(payload["findings"]) == 17  # 1 fail + 1 warn + 15 info
    assert payload["result"] == "FAIL"
