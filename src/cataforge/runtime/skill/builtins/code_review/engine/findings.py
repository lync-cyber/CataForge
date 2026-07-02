"""Structured findings — the Layer 1 → Layer 2 / report-aggregation contract.

Every check returns ``list[Finding]``; the pipeline renders them as text
(human console) or JSON (Layer 2 semantic review, CODE-SCAN aggregation).
Finding severity drives the exit code: any ``fail`` finding → exit 1;
``warn`` and ``info`` never gate.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

FINDING_SEVERITIES = ("fail", "warn", "info")

_SEVERITY_LABEL = {"fail": "FAIL", "warn": "WARN", "info": "INFO"}


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


def render_text(result: PipelineResult) -> str:
    lines: list[str] = []
    for f in result.findings:
        label = _SEVERITY_LABEL.get(f.severity, f.severity.upper())
        head, *rest = f.detail.splitlines() or [""]
        lines.append(f"{label}: {_location(f)}({f.check_id}) {head}")
        lines.extend(f"  {r}" for r in rest)
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
