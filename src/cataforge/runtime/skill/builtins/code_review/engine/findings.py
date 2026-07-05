"""Structured findings — the Layer 1 → Layer 2 / report-aggregation contract.

Every check returns ``list[Finding]``; the pipeline renders them as text
(human console) or JSON (Layer 2 semantic review, CODE-SCAN aggregation).
Finding severity drives the exit code: any ``fail`` finding → exit 1;
``warn`` and ``info`` never gate.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field

FINDING_SEVERITIES = ("fail", "warn", "info")

_SEVERITY_LABEL = {"fail": "FAIL", "warn": "WARN", "info": "INFO"}
_SEVERITY_RANK = {"fail": 0, "warn": 1, "info": 2}
# Informational findings shown per category in text mode before the tail is
# collapsed; gating (fail/warn) findings are never truncated. Full list via
# --verbose or --format json.
_INFO_CAP = 10


@dataclass(frozen=True)
class Finding:
    """One Layer 1 defect or signal.

    ``severity``: ``fail`` gates the run, ``warn`` is a non-gating defect
    signal, ``info`` is an informational rot/probe signal. ``file``/``line``
    are empty/0 for cross-file or probe-level findings.
    """

    check_id: str
    severity: str
    category: str
    detail: str
    file: str = ""
    line: int = 0


@dataclass
class PipelineResult:
    """Outcome of one pipeline run over a target."""

    mode: str
    target: str
    checks_run: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)

    def count(self, severity: str) -> int:
        return sum(1 for f in self.findings if f.severity == severity)

    @property
    def exit_code(self) -> int:
        return 1 if self.count("fail") else 0

    @property
    def result(self) -> str:
        return "FAIL" if self.exit_code else "PASS"


def _location(finding: Finding) -> str:
    if finding.file and finding.line:
        return f"[{finding.file}:{finding.line}] "
    if finding.file:
        return f"[{finding.file}] "
    return ""


def _render_finding(finding: Finding) -> list[str]:
    label = _SEVERITY_LABEL.get(finding.severity, finding.severity.upper())
    head, *rest = finding.detail.splitlines() or [""]
    return [f"{label}: {_location(finding)}({finding.check_id}) {head}", *(f"  {r}" for r in rest)]


def render_text(result: PipelineResult, verbose: bool = False) -> str:
    """Group findings by category, gating (fail/warn) first and never
    truncated; the informational tail is capped per category unless
    *verbose*. The summary block and ``RESULT`` line are format-stable."""
    lines: list[str] = []
    by_category: dict[str, list[Finding]] = defaultdict(list)
    for f in result.findings:
        by_category[f.category].append(f)

    def _category_rank(category: str) -> tuple[int, str]:
        worst = min(_SEVERITY_RANK.get(f.severity, 3) for f in by_category[category])
        return (worst, category)

    for category in sorted(by_category, key=_category_rank):
        group = sorted(by_category[category], key=lambda f: _SEVERITY_RANK.get(f.severity, 3))
        counts = {sev: sum(1 for f in group if f.severity == sev) for sev in FINDING_SEVERITIES}
        lines.append(
            f"── {category}: fail={counts['fail']} warn={counts['warn']} info={counts['info']}"
        )
        shown_info = 0
        for f in group:
            if f.severity == "info":
                if not verbose and shown_info >= _INFO_CAP:
                    continue
                shown_info += 1
            lines.extend(_render_finding(f))
        if not verbose and counts["info"] > _INFO_CAP:
            lines.append(
                f"  … 还有 {counts['info'] - _INFO_CAP} 条 info"
                "（--verbose / --format json 查看全部）"
            )
    lines.append("")
    lines.append("=" * 41)
    lines.append(f"Code Review Layer 1 Summary ({result.mode})")
    lines.append(f"  Target: {result.target}")
    lines.append(f"  Checks run: {len(result.checks_run)}")
    lines.append(
        "  Findings: "
        f"fail={result.count('fail')} warn={result.count('warn')} info={result.count('info')}"
    )
    lines.append("=" * 41)
    lines.append(f"RESULT: {result.result}")
    return "\n".join(lines)


def render_json(result: PipelineResult) -> str:
    payload = {
        "mode": result.mode,
        "target": result.target,
        "checks_run": result.checks_run,
        "findings": [
            {
                "check_id": f.check_id,
                "severity": f.severity,
                "category": f.category,
                "file": f.file,
                "line": f.line,
                "detail": f.detail,
            }
            for f in result.findings
        ],
        "summary": {
            "fail": result.count("fail"),
            "warn": result.count("warn"),
            "info": result.count("info"),
        },
        "result": result.result,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)
