"""Shared per-run state handed to every check."""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from cataforge.runtime.skill.builtins.code_review.engine.fs import iter_files, resolved
from cataforge.utils.run_subprocess import run as run_proc

DETECT_TIMEOUT_SECS = 15


@dataclass
class CheckContext:
    """One pipeline run's shared state.

    ``tool_cache`` maps tool name → availability; tests pre-seed it to keep
    checks hermetic. ``reported_missing`` dedups the "未安装，跳过" finding so
    a tool absent for 100 files is reported once.
    """

    target: Path
    project_root: Path | None
    mode: str
    fix: bool = False
    tool_cache: dict[str, bool] = field(default_factory=dict)
    reported_missing: set[str] = field(default_factory=set)
    _walk: list[Path] | None = field(default=None, repr=False)

    def all_files(self) -> list[Path]:
        """Every file under target (excluded dirs pruned), cached — one walk
        serves every check's extension filter."""
        if self._walk is None:
            if self.target.is_file():
                self._walk = [self.target]
            else:
                self._walk = sorted(iter_files(self.target))
        return self._walk

    def files(self, extensions: frozenset[str]) -> list[Path]:
        return [p for p in self.all_files() if p.suffix.lower() in extensions]

    def present_extensions(self) -> set[str]:
        return {p.suffix.lower() for p in self.all_files()}

    def tool_available(self, name: str, detect: Sequence[str]) -> bool:
        if name not in self.tool_cache:
            try:
                run_proc(resolved(list(detect)), timeout=DETECT_TIMEOUT_SECS)
                self.tool_cache[name] = True
            except (FileNotFoundError, subprocess.TimeoutExpired):
                self.tool_cache[name] = False
        return self.tool_cache[name]

    def first_missing_report(self, name: str) -> bool:
        """True exactly once per missing tool — caller emits the WARN finding."""
        if name in self.reported_missing:
            return False
        self.reported_missing.add(name)
        return True
