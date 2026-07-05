"""Duplication dimension (scan mode, informational).

Symmetric with ``complexity_gate``: a zero-dependency built-in measurement
guarantees the dimension is never dark, and an external tool (jscpd)
augments it with a richer token-level signal *when it actually produces a
report*. A jscpd that can't run — absent, or a Windows ``.cmd`` shim that
no-ops under ``subprocess`` — falls through to the built-in floor rather
than leaving duplication unmeasured. No external tool is a single point of
failure for the dimension.

Built-in algorithm: hash windows of ``WINDOW`` consecutive
whitespace-normalized significant lines; a window hash at ≥2 distinct
locations marks those lines duplicated. Coarse by design (a floor).
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
from collections import defaultdict
from pathlib import Path

from cataforge.runtime.skill.builtins.code_review.engine.context import CheckContext
from cataforge.runtime.skill.builtins.code_review.engine.findings import Finding
from cataforge.runtime.skill.builtins.code_review.engine.fs import (
    load_project_ignore,
    probe_ignore_globs,
    resolved,
)
from cataforge.runtime.skill.builtins.code_review.engine.registry import (
    CheckSpec,
    register_check,
)
from cataforge.utils.run_subprocess import run as run_proc

CHECK_ID = "code_review.duplication"
_JSCPD_DETECT = ("npx", "jscpd", "--version")
JSCPD_TIMEOUT_SECS = 180
# Ratio (%) at or above which a duplication finding escalates from
# informational to a warn-level defect signal — shared by both surfaces.
WARN_RATIO = 5.0
WINDOW = 6  # consecutive significant lines forming a comparable block
_MIN_SIGNIFICANT_LEN = 4
_TOP_PAIRS = 5

SUPPORTED_EXTENSIONS = frozenset(
    {".js", ".ts", ".jsx", ".tsx", ".py", ".go", ".cs", ".rs", ".java", ".kt", ".swift"}
)


# ---- jscpd augmentation (best-effort) ----------------------------------------


def _jscpd_rel(name: str) -> str:
    return name.split("cataforge/")[-1] if "cataforge/" in name else Path(name).name


def parse_jscpd_report(report: Path) -> list[Finding]:
    """Structured finding from jscpd's JSON report; ``[]`` when clean."""
    try:
        data = json.loads(report.read_text(errors="replace"))
    except ValueError:
        return []
    dups = data.get("duplicates") or []
    if not dups:
        return []
    total = (data.get("statistics") or {}).get("total") or {}
    pct = float(total.get("percentage", 0.0) or 0.0)
    top = sorted(dups, key=lambda d: d.get("lines", 0), reverse=True)[:_TOP_PAIRS]
    locs = [
        f"  {d.get('lines', 0)}L {_jscpd_rel((d.get('firstFile') or {}).get('name', '?'))}"
        f" <-> {_jscpd_rel((d.get('secondFile') or {}).get('name', '?'))}"
        for d in top
    ]
    severity = "warn" if pct >= WARN_RATIO else "info"
    detail = "\n".join([f"jscpd: {len(dups)} clones, {pct:.2f}% duplicated", *locs])
    return [Finding(check_id=CHECK_ID, severity=severity, category="duplication", detail=detail)]


def _jscpd_findings(ctx: CheckContext) -> list[Finding] | None:
    """jscpd's rich signal, or ``None`` if it didn't produce a report (so the
    caller falls back to the built-in floor)."""
    if not ctx.tool_available("jscpd", _JSCPD_DETECT):
        return None
    with tempfile.TemporaryDirectory(prefix="cataforge-jscpd-") as tmp:
        workdir = Path(tmp)
        cmd = [
            "npx",
            "jscpd",
            str(ctx.target),
            "--ignore",
            probe_ignore_globs(load_project_ignore(ctx.project_root)),
            "--reporters",
            "json",
            "--output",
            str(workdir),
            "--silent",
        ]
        try:
            run_proc(resolved(cmd), timeout=JSCPD_TIMEOUT_SECS)
        except subprocess.TimeoutExpired:
            return None
        report = workdir / "jscpd-report.json"
        if not report.is_file():
            return None
        return parse_jscpd_report(report)


# ---- built-in floor ----------------------------------------------------------


def _significant_lines(text: str) -> list[tuple[int, str]]:
    """``(1-based lineno, whitespace-normalized text)`` for non-trivial lines."""
    out: list[tuple[int, str]] = []
    for idx, line in enumerate(text.splitlines(), start=1):
        norm = " ".join(line.split())
        if len(norm) >= _MIN_SIGNIFICANT_LEN:
            out.append((idx, norm))
    return out


def _windows(sig: list[tuple[int, str]]) -> list[tuple[str, int, tuple[int, ...]]]:
    """``(hash, start lineno, covered linenos)`` per sliding window."""
    out: list[tuple[str, int, tuple[int, ...]]] = []
    for k in range(len(sig) - WINDOW + 1):
        block = sig[k : k + WINDOW]
        digest = hashlib.sha1("\n".join(t for _, t in block).encode("utf-8")).hexdigest()
        out.append((digest, block[0][0], tuple(ln for ln, _ in block)))
    return out


def _rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.name


def builtin_floor(ctx: CheckContext) -> list[Finding]:
    root = ctx.project_root or (ctx.target if ctx.target.is_dir() else ctx.target.parent)
    index: dict[str, list[tuple[str, int, tuple[int, ...]]]] = defaultdict(list)
    total_sig = 0
    for path in ctx.files(SUPPORTED_EXTENSIONS):
        try:
            text = path.read_text(errors="replace")
        except OSError:
            continue
        sig = _significant_lines(text)
        total_sig += len(sig)
        rel = _rel(path, root)
        for digest, start, covered in _windows(sig):
            index[digest].append((rel, start, covered))

    duplicated_by_file: dict[str, set[int]] = defaultdict(set)
    pairs: list[str] = []
    groups = 0
    for occurrences in index.values():
        locations = {(rel, start) for rel, start, _ in occurrences}
        if len(locations) < 2:
            continue
        groups += 1
        for rel, _start, covered in occurrences:
            duplicated_by_file[rel].update(covered)
        if len(pairs) < _TOP_PAIRS:
            (ra, sa, _), (rb, sb, _) = occurrences[0], occurrences[1]
            pairs.append(f"  {ra}:{sa} <-> {rb}:{sb}")

    if groups == 0:
        return []

    dup_lines = sum(len(lines) for lines in duplicated_by_file.values())
    ratio = (dup_lines / total_sig * 100.0) if total_sig else 0.0
    # The floor over-approximates (line-level, indentation-normalized), so it
    # stays informational — precise warn-level escalation is jscpd's job.
    detail = "\n".join(
        [
            f"duplication (builtin floor): {groups} 重复块（≥{WINDOW} 行）, 约 {ratio:.2f}% 行重复",
            *pairs,
        ]
    )
    return [Finding(check_id=CHECK_ID, severity="info", category="duplication", detail=detail)]


def run(ctx: CheckContext) -> list[Finding]:
    if ctx.mode != "scan":
        return []
    if not (SUPPORTED_EXTENSIONS & ctx.present_extensions()):
        return []
    jscpd = _jscpd_findings(ctx)
    if jscpd is not None:
        return jscpd
    return builtin_floor(ctx)


register_check(
    CheckSpec(
        id=CHECK_ID,
        title=(
            "重复检测（内置行块克隆保底 + jscpd token 级增强）— 与 complexity_gate 同构：jscpd 出"
            "报告时用其更丰富信号，不可用/无报告时回落零依赖内置 floor，duplication 维度永不静默"
        ),
        severity="informational",
        category="duplication",
        modes=frozenset({"scan"}),
        run=run,
    )
)
