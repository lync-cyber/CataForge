"""Shared issue model for graded Layer 1 review builtins.

doc-consistency and sprint-review both emit findings on the
CRITICAL/HIGH/MEDIUM/LOW scale; this module is the single representation
they collect into so severity partitioning and serialization are defined
once. (framework-review uses a distinct FAIL/WARN/INFO check-result axis
and keeps its own ``Finding`` model.)
"""

from __future__ import annotations

from dataclasses import dataclass
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

    def __iter__(self):
        return iter(self.issues)

    def __len__(self) -> int:
        return len(self.issues)


__all__ = ["Issue", "IssueCollector"]
