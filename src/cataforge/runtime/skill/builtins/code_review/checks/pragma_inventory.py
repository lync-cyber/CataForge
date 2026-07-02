"""Exemption pragma inventory — code-review scan probe (informational).

Enumerates every ``cataforge: allow(...)`` pragma in the scanned tree
(check id, reason, location, git-blame age) so exemption sprawl stays
visible and reviewable — legal escape hatches must not silently
accumulate. Lines carrying a ``cataforge``-marker comment that does NOT
parse as the unified grammar are reported as unknown-pragma (legacy
syntax residue no longer honored by any check). Prose files are skipped
(grammar docs quote pragma examples).
"""

from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path

from cataforge.runtime.skill.builtins.code_review.engine.context import CheckContext
from cataforge.runtime.skill.builtins.code_review.engine.findings import Finding
from cataforge.runtime.skill.builtins.code_review.engine.pragmas import parse_allowances
from cataforge.runtime.skill.builtins.code_review.engine.registry import (
    CheckSpec,
    register_check,
)
from cataforge.utils.run_subprocess import run as run_proc

CHECK_ID = "code_review.pragma_inventory"
GIT_TIMEOUT_SECS = 30

_CANDIDATE_RE = re.compile(r"cataforge[:\-]\s*[\w(-]+")
_ALLOW_MARK_RE = re.compile(r"cataforge:\s*allow\(")
_BLAME_TIME_RE = re.compile(r"^committer-time (\d+)$", re.MULTILINE)
_PROSE_SUFFIXES = frozenset({".md", ".rst", ".txt"})
_SECONDS_PER_DAY = 86400


def _blame_age_days(root: Path, rel: str, line: int) -> int | None:
    try:
        result = run_proc(
            ["git", "blame", "-L", f"{line},{line}", "--porcelain", "--", rel],
            cwd=root,
            timeout=GIT_TIMEOUT_SECS,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    match = _BLAME_TIME_RE.search(result.stdout)
    if match is None:
        return None
    return max(0, int((time.time() - int(match.group(1))) // _SECONDS_PER_DAY))


def _inventory_file(root: Path, path: Path, text: str) -> list[Finding]:
    findings: list[Finding] = []
    allowances = parse_allowances(text)
    allow_lines = {a.line for a in allowances}
    try:
        rel = path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        rel = str(path)
    for lineno, line in enumerate(text.splitlines(), start=1):
        candidates = _CANDIDATE_RE.findall(line)
        if not candidates:
            continue
        parsed = len(_ALLOW_MARK_RE.findall(line)) if lineno in allow_lines else 0
        if len(candidates) > parsed:
            findings.append(
                Finding(
                    check_id=CHECK_ID,
                    severity="info",
                    category="convention",
                    detail=(
                        f"unknown-pragma：{line.strip()[:80]} — 非统一豁免语法，任何检查都不识别"
                        "（语法见 pragma-grammar.md）"
                    ),
                    file=str(path),
                    line=lineno,
                )
            )
    for allowance in allowances:
        age = _blame_age_days(root, rel, allowance.line)
        aging = f"，引入 {age} 天前" if age is not None else ""
        reason = f'reason="{allowance.reason}"' if allowance.reason else "缺 reason"
        findings.append(
            Finding(
                check_id=CHECK_ID,
                severity="info",
                category="convention",
                detail=f"allow({allowance.check}) {reason}{aging}",
                file=str(path),
                line=allowance.line,
            )
        )
    return findings


def run(ctx: CheckContext) -> list[Finding]:
    """Every exemption pragma (and legacy residue) as informational findings."""
    root = ctx.project_root or (ctx.target if ctx.target.is_dir() else ctx.target.parent)
    findings: list[Finding] = []
    for path in ctx.all_files():
        if path.suffix.lower() in _PROSE_SUFFIXES:
            continue
        try:
            text = path.read_text(errors="replace")
        except OSError:
            continue
        if "cataforge" not in text:
            continue
        findings.extend(_inventory_file(root, path, text))
    return findings


register_check(
    CheckSpec(
        id=CHECK_ID,
        title=(
            "豁免 pragma 盘点探针 — 枚举全部 cataforge: allow(...)（check / reason / git blame "
            "引入天数）记 INFO；cataforge 标记但不符合统一语法的残留报 unknown-pragma"
        ),
        severity="informational",
        category="convention",
        modes=frozenset({"scan"}),
        run=run,
    )
)
