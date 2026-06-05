"""Shared issue model for graded Layer 1 review builtins.

doc-consistency and sprint-review both emit findings on the
CRITICAL/HIGH/MEDIUM/LOW scale; this module is the single representation
they collect into so severity partitioning and serialization are defined
once. (framework-review uses a distinct FAIL/WARN/INFO check-result axis
and keeps its own ``Finding`` model.)
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from cataforge.core.types import Severity

_BLOCKING = frozenset({Severity.CRITICAL, Severity.HIGH})


@dataclass
class Issue:
    severity: Severity
    category: str
    message: str
    task: str | None = None
    path: str | None = None

    @property
    def blocking(self) -> bool:
        return self.severity in _BLOCKING

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "severity": self.severity.value,
            "category": self.category,
            "message": self.message,
        }
        if self.task is not None:
            out["task"] = self.task
        if self.path is not None:
            out["path"] = self.path
        return out


class IssueCollector:
    """Accumulates :class:`Issue` records with blocking/advisory partitioning."""

    def __init__(self) -> None:
        self.issues: list[Issue] = []

    def add(
        self,
        severity: Severity,
        category: str,
        message: str,
        *,
        task: str | None = None,
        path: str | None = None,
    ) -> Issue:
        issue = Issue(severity, category, message, task=task, path=path)
        self.issues.append(issue)
        return issue

    @property
    def blocking(self) -> list[Issue]:
        return [i for i in self.issues if i.blocking]

    @property
    def advisory(self) -> list[Issue]:
        return [i for i in self.issues if not i.blocking]

    def __iter__(self) -> Iterator[Issue]:
        return iter(self.issues)

    def __len__(self) -> int:
        return len(self.issues)


@dataclass
class CheckReport:
    """Structured outcome of a Layer 1 check run.

    Separates *what was found* (``issues`` + ``summary``) from *how it
    prints*, so a checker's ``collect()`` can stay free of I/O and a single
    rendering layer can target text or JSON. ``exit_code`` is the single
    source of truth for the 0/1/2 subprocess contract shared by these
    builtins: 0 = clean, 1 = blocking findings, 2 = advisory only.

    ``summary`` carries non-issue render data (traceability matrices,
    coverage counts) keyed by the producing checker; ``headline`` is the
    leading status line a checker emits before its findings.
    """

    issues: IssueCollector
    summary: dict[str, Any] = field(default_factory=dict)
    headline: str | None = None

    @property
    def exit_code(self) -> int:
        if self.issues.blocking:
            return 1
        if self.issues.advisory:
            return 2
        return 0

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "exit_code": self.exit_code,
            "issues": [i.to_dict() for i in self.issues],
            "summary": self.summary,
        }
        if self.headline is not None:
            out["headline"] = self.headline
        return out


__all__ = ["CheckReport", "Issue", "IssueCollector"]
