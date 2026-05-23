"""Shared Finding / Report dataclasses for framework-review checks."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Finding:
    check_id: str
    severity: str  # FAIL / WARN / INFO
    location: str
    message: str

    def render(self) -> str:
        return f"[{self.severity}] {self.check_id} @ {self.location}: {self.message}"


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)

    @property
    def fail_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "FAIL")

    @property
    def warn_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "WARN")

    @property
    def info_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "INFO")

    def add(
        self, check_id: str, severity: str, location: str, message: str
    ) -> None:
        self.findings.append(Finding(check_id, severity, location, message))
