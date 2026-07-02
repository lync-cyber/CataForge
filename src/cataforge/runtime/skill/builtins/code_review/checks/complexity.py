"""Complexity gate with ratchet baseline — code-review Layer 1.

Thresholds come from the ``scope: project`` ``complexity.yaml``
(builtin ships conservative defaults; a project override replaces the
whole file). Measurement sources, best first:

1. Installed tools for cyclomatic complexity — radon (``.py``),
   gocyclo (``.go``), lizard (multi-language fallback).
2. Pattern-driven proxy from the ``scope: language``
   ``complexity-{lang}.yaml`` files — function boundaries by regex,
   branches counted per line, nesting from relative indentation.
   Cognitive / nesting / function_lines always come from the proxy
   (tools only provide cyclomatic); every finding names its source.

Gate semantics: review judges only git-diff-touched functions against
``max(fail threshold, baseline value)`` (ratchet — touched code must
not get worse; untouched legacy never blocks; no git info → everything
is touched). Scan never gates: it refreshes
``.cataforge/baselines/complexity.json`` and reports over-warn
functions as informational findings. Exemption is line-scoped on the
function-definition line: ``cataforge: allow(complexity_gate,
reason="...")``. Details: ``.cataforge/references/complexity-checks.md``.
"""

from __future__ import annotations

import csv
import io
import json
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cataforge.runtime.skill.builtins.code_review.engine.baseline import (
    changed_line_ranges,
    load_baseline,
    overlaps,
    save_baseline,
)
from cataforge.runtime.skill.builtins.code_review.engine.context import CheckContext
from cataforge.runtime.skill.builtins.code_review.engine.findings import Finding
from cataforge.runtime.skill.builtins.code_review.engine.fs import resolved
from cataforge.runtime.skill.builtins.code_review.engine.pragmas import (
    Allowance,
    line_allowances,
)
from cataforge.runtime.skill.builtins.code_review.engine.registry import (
    CheckSpec,
    register_check,
)
from cataforge.runtime.skill.rules.loader import SUPPORTED_FLAGS, discover_rules
from cataforge.utils.run_subprocess import run as run_proc

_BUILTIN_MODULE = "cataforge.runtime.skill.builtins.code_review"
_SKILL_ID = "code-review"

CHECK_ID = "code_review.complexity_gate"
BASELINE_NAME = "complexity.json"
METRICS = ("cyclomatic", "cognitive", "function_lines", "nesting")
MEASURE_TIMEOUT_SECS = 120
_TAB_WIDTH = 4
_CLOSER_RE = re.compile(r"^[\s)\]}>,;]*$")

# radon rank lower bounds (cc value where the letter starts).
_RADON_RANKS = ((41, "F"), (31, "E"), (21, "D"), (11, "C"), (6, "B"))


@dataclass(frozen=True)
class LangComplexity:
    extensions: frozenset[str]
    function_patterns: tuple[re.Pattern[str], ...]
    branch_patterns: tuple[re.Pattern[str], ...]


@dataclass
class FunctionMetrics:
    name: str
    fingerprint: str
    display_path: str
    rel_path: str
    start: int  # 1-based definition line
    end: int  # 1-based last line of span
    metrics: dict[str, int]
    source: str
    allowance: Allowance | None


def _compile_flags(flags_raw: list[str] | None) -> int:
    if not flags_raw:
        return 0
    out = 0
    for f in flags_raw:
        out |= SUPPORTED_FLAGS.get(f, 0)
    return out


def _compile_patterns(entries: list[dict[str, Any]] | None) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(p["regex"], _compile_flags(p.get("flags"))) for p in (entries or []))


def load_complexity_rules(
    project_root: Path | None = None,
) -> tuple[dict[str, dict[str, int]] | None, dict[str, LangComplexity]]:
    """``(thresholds, per-language proxy patterns)`` for *project_root*."""
    specs = discover_rules(_SKILL_ID, builtin_module=_BUILTIN_MODULE, project_root=project_root)
    thresholds: dict[str, dict[str, int]] | None = None
    langs: dict[str, LangComplexity] = {}
    for (rule_type, language), spec in specs.items():
        if rule_type != "complexity":
            continue
        if spec.scope == "project":
            thresholds = spec.raw["thresholds"]
        else:
            langs[language] = LangComplexity(
                extensions=spec.extensions,
                function_patterns=_compile_patterns(spec.raw.get("function_patterns")),
                branch_patterns=_compile_patterns(spec.raw.get("branch_patterns")),
            )
    return thresholds, langs


def thresholds_for(project_root: Path | None) -> dict[str, dict[str, int]] | None:
    """Threshold table for external consumers (the scan probes' commands)."""
    thresholds, _ = load_complexity_rules(project_root)
    return thresholds


def radon_rank(threshold: int) -> str:
    """radon ``-n`` letter whose range contains ``threshold + 1``."""
    for bound, letter in _RADON_RANKS:
        if threshold + 1 >= bound:
            return letter
    return "A"


# ---- proxy measurement -------------------------------------------------------


def _indent_of(line: str) -> int:
    expanded = line.expandtabs(_TAB_WIDTH)
    return len(expanded) - len(expanded.lstrip(" "))


def _function_defs(
    lines: list[str], patterns: tuple[re.Pattern[str], ...]
) -> list[tuple[int, str, int]]:
    """``(0-based line index, name, indent)`` per detected definition line."""
    defs: list[tuple[int, str, int]] = []
    for idx, line in enumerate(lines):
        if not line.strip():
            continue
        for pattern in patterns:
            match = pattern.search(line)
            if match:
                defs.append((idx, match.group(1) or "<anonymous>", _indent_of(line)))
                break
    return defs


def _span_end(lines: list[str], start: int, indent: int) -> int:
    """0-based last line of the function starting at *start*.

    The body is every following line indented deeper; a same-indent line
    that only closes brackets still belongs to the function, any other
    same-or-lower indent line ends it.
    """
    end = len(lines) - 1
    for j in range(start + 1, len(lines)):
        line = lines[j]
        if not line.strip():
            continue
        width = _indent_of(line)
        if width < indent or (width == indent and not _CLOSER_RE.match(line)):
            return j - 1
    return end


def _measure_span(
    lines: list[str],
    start: int,
    end: int,
    indent: int,
    branch_patterns: tuple[re.Pattern[str], ...],
) -> dict[str, int]:
    unit = 0
    for j in range(start + 1, end + 1):
        line = lines[j]
        if not line.strip():
            continue
        width = _indent_of(line)
        if width > indent and (unit == 0 or width - indent < unit):
            unit = width - indent
    unit = unit or _TAB_WIDTH

    branches = 0
    cognitive = 0
    max_depth = 0
    for j in range(start + 1, end + 1):
        line = lines[j]
        if not line.strip():
            continue
        width = _indent_of(line)
        depth = max(0, (width - indent) // unit - 1) if width > indent else 0
        max_depth = max(max_depth, depth)
        hits = sum(len(p.findall(line)) for p in branch_patterns)
        branches += hits
        cognitive += hits * (1 + depth)
    return {
        "cyclomatic": 1 + branches,
        "cognitive": cognitive,
        "function_lines": end - start + 1,
        "nesting": max_depth,
    }


# ---- tool adapters (cyclomatic overrides) ------------------------------------


def parse_radon_json(text: str) -> dict[tuple[str, int], int]:
    """``{(path, def line): cc}`` from ``radon cc -j`` output."""
    try:
        data = json.loads(text)
    except ValueError:
        return {}
    out: dict[tuple[str, int], int] = {}
    if not isinstance(data, dict):
        return {}
    for path, blocks in data.items():
        if not isinstance(blocks, list):
            continue
        for block in blocks:
            if not isinstance(block, dict):
                continue
            lineno, cc = block.get("lineno"), block.get("complexity")
            if isinstance(lineno, int) and isinstance(cc, int):
                out[(str(Path(path).resolve().as_posix()), lineno)] = cc
    return out


_GOCYCLO_LINE_RE = re.compile(r"^(\d+)\s+\S+\s+\S+\s+(.+):(\d+):\d+$")


def parse_gocyclo(text: str) -> dict[tuple[str, int], int]:
    """``{(path, def line): cc}`` from plain ``gocyclo`` output."""
    out: dict[tuple[str, int], int] = {}
    for line in text.splitlines():
        match = _GOCYCLO_LINE_RE.match(line.strip())
        if match:
            cc, path, lineno = match.groups()
            out[(str(Path(path).resolve().as_posix()), int(lineno))] = int(cc)
    return out


def parse_lizard_csv(text: str) -> dict[tuple[str, int], int]:
    """``{(path, def line): ccn}`` from ``lizard --csv`` output.

    CSV columns: nloc, ccn, tokens, params, length, location, file,
    function, long_name, start, end.
    """
    out: dict[tuple[str, int], int] = {}
    for row in csv.reader(io.StringIO(text)):
        if len(row) < 11:
            continue
        try:
            ccn, path, start = int(row[1]), row[6], int(row[9])
        except (ValueError, IndexError):
            continue
        out[(str(Path(path).resolve().as_posix()), start)] = ccn
    return out


@dataclass(frozen=True)
class _ToolAdapter:
    name: str  # tool_cache key (same key as the scan probe for that tool)
    detect: tuple[str, ...]
    extensions: frozenset[str]
    build_cmd: tuple[str, ...]  # target appended
    parse: Callable[[str], dict[tuple[str, int], int]]


_ADAPTERS: tuple[_ToolAdapter, ...] = (
    _ToolAdapter(
        name="radon (cc)",
        detect=("radon", "--version"),
        extensions=frozenset({".py"}),
        build_cmd=("radon", "cc", "-j"),
        parse=parse_radon_json,
    ),
    _ToolAdapter(
        name="gocyclo",
        detect=("gocyclo", "-?"),
        extensions=frozenset({".go"}),
        build_cmd=("gocyclo",),
        parse=parse_gocyclo,
    ),
    _ToolAdapter(
        name="lizard",
        detect=("lizard", "--version"),
        extensions=frozenset({".py", ".go", ".js", ".jsx", ".ts", ".tsx", ".java", ".cs", ".rs"}),
        build_cmd=("lizard", "--csv"),
        parse=parse_lizard_csv,
    ),
)


def _tool_overrides(ctx: CheckContext) -> dict[tuple[str, int], tuple[int, str]]:
    """``{(abs path, def line): (cc, source)}``; earlier adapters win."""
    overrides: dict[tuple[str, int], tuple[int, str]] = {}
    present = ctx.present_extensions()
    for adapter in _ADAPTERS:
        if not (adapter.extensions & present):
            continue
        if not ctx.tool_available(adapter.name, adapter.detect):
            continue
        try:
            result = run_proc(
                resolved([*adapter.build_cmd, str(ctx.target)]),
                timeout=MEASURE_TIMEOUT_SECS,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
        for key, cc in adapter.parse(result.stdout).items():
            overrides.setdefault(key, (cc, adapter.name.split(" ")[0]))
    return overrides


# ---- measurement orchestration -----------------------------------------------


def _measure_file(
    path: Path,
    rel: str,
    lang: LangComplexity,
    overrides: dict[tuple[str, int], tuple[int, str]],
) -> list[FunctionMetrics]:
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return []
    lines = text.splitlines()
    allowances = line_allowances(text, CHECK_ID)
    abs_posix = str(path.resolve().as_posix())
    occurrences: dict[str, int] = {}
    out: list[FunctionMetrics] = []
    for idx, name, indent in _function_defs(lines, lang.function_patterns):
        end = _span_end(lines, idx, indent)
        metrics = _measure_span(lines, idx, end, indent, lang.branch_patterns)
        source = "proxy"
        override = overrides.get((abs_posix, idx + 1))
        if override is None:
            candidates = [
                (line, cc_src)
                for (p, line), cc_src in overrides.items()
                if p == abs_posix and idx + 1 <= line <= end + 1
            ]
            if candidates:
                override = min(candidates)[1]
        if override is not None:
            metrics["cyclomatic"], source = override
        occurrences[name] = occurrences.get(name, 0) + 1
        suffix = f"#{occurrences[name]}" if occurrences[name] > 1 else ""
        out.append(
            FunctionMetrics(
                name=name,
                fingerprint=f"{rel}::{name}{suffix}",
                display_path=str(path),
                rel_path=rel,
                start=idx + 1,
                end=end + 1,
                metrics=metrics,
                source=source,
                allowance=allowances.get(idx + 1),
            )
        )
    return out


def _measure_all(ctx: CheckContext, langs: dict[str, LangComplexity]) -> list[FunctionMetrics]:
    root = ctx.project_root or (ctx.target if ctx.target.is_dir() else ctx.target.parent)
    all_exts: frozenset[str] = frozenset().union(*(lc.extensions for lc in langs.values()))
    overrides = _tool_overrides(ctx)
    functions: list[FunctionMetrics] = []
    for path in ctx.files(all_exts):
        lang = next((lc for lc in langs.values() if path.suffix.lower() in lc.extensions), None)
        if lang is None or not lang.function_patterns:
            continue
        try:
            rel = path.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            continue
        functions.extend(_measure_file(path, rel, lang, overrides))
    return functions


# ---- gate / scan -------------------------------------------------------------


def _judge(
    fn: FunctionMetrics,
    thresholds: dict[str, dict[str, int]],
    baseline: dict[str, dict[str, int]],
) -> list[Finding]:
    if fn.allowance is not None:
        if fn.allowance.reason:
            return []
        return [
            Finding(
                check_id=CHECK_ID,
                severity="warn",
                category="complexity",
                detail=f"{fn.name}: allow(complexity_gate) 缺 reason — 豁免生效但须补充理由",
                file=fn.display_path,
                line=fn.start,
            )
        ]
    recorded = baseline.get(fn.fingerprint, {})
    out: list[Finding] = []
    for metric in METRICS:
        value = fn.metrics[metric]
        base = recorded.get(metric)
        limit = max(thresholds[metric]["fail"], base or 0)
        if value > limit:
            out.append(
                Finding(
                    check_id=CHECK_ID,
                    severity="fail",
                    category="complexity",
                    detail=(
                        f"{fn.name}: {metric}={value} 超过门禁 {limit}"
                        f"（fail 阈值 {thresholds[metric]['fail']}，基线 "
                        f"{base if base is not None else '无'}，度量来源 {fn.source}）"
                    ),
                    file=fn.display_path,
                    line=fn.start,
                )
            )
        elif value > thresholds[metric]["warn"]:
            out.append(
                Finding(
                    check_id=CHECK_ID,
                    severity="warn",
                    category="complexity",
                    detail=(
                        f"{fn.name}: {metric}={value} 超过 warn 阈值 "
                        f"{thresholds[metric]['warn']}（度量来源 {fn.source}）"
                    ),
                    file=fn.display_path,
                    line=fn.start,
                )
            )
    return out


def _scan_findings(
    functions: list[FunctionMetrics],
    thresholds: dict[str, dict[str, int]],
    ctx: CheckContext,
) -> list[Finding]:
    findings: list[Finding] = []
    if ctx.project_root is not None:
        path = save_baseline(
            ctx.project_root, BASELINE_NAME, {fn.fingerprint: fn.metrics for fn in functions}
        )
        findings.append(
            Finding(
                check_id=CHECK_ID,
                severity="info",
                category="complexity",
                detail=f"复杂度基线已刷新：{len(functions)} 函数 → {path}",
            )
        )
    for fn in functions:
        over = [
            f"{metric}={fn.metrics[metric]}(warn {thresholds[metric]['warn']})"
            for metric in METRICS
            if fn.metrics[metric] > thresholds[metric]["warn"]
        ]
        if over:
            findings.append(
                Finding(
                    check_id=CHECK_ID,
                    severity="info",
                    category="complexity",
                    detail=f"{fn.name}: {', '.join(over)}（度量来源 {fn.source}）",
                    file=fn.display_path,
                    line=fn.start,
                )
            )
    return findings


def run(ctx: CheckContext) -> list[Finding]:
    """Measure functions; scan refreshes the baseline, review gates the diff."""
    thresholds, langs = load_complexity_rules(ctx.project_root)
    if thresholds is None or not langs:
        return []
    functions = _measure_all(ctx, langs)
    if ctx.mode == "scan":
        return _scan_findings(functions, thresholds, ctx)

    root = ctx.project_root or (ctx.target if ctx.target.is_dir() else ctx.target.parent)
    baseline = load_baseline(ctx.project_root, BASELINE_NAME) if ctx.project_root else {}
    ranges = changed_line_ranges(root)
    findings: list[Finding] = []
    for fn in functions:
        if ranges is not None and not overlaps(fn.start, fn.end, ranges.get(fn.rel_path, [])):
            continue
        findings.extend(_judge(fn, thresholds, baseline))
    return findings


register_check(
    CheckSpec(
        id=CHECK_ID,
        title=(
            "复杂度门禁（项目级 complexity.yaml 声明四指标 warn/fail 阈值，complexity-{lang}.yaml "
            "提供代理度量 pattern；radon/gocyclo/lizard 可用时优先取工具圈复杂度）— review 只对 "
            "git diff 涉及函数按 max(fail 阈值, 基线值) 施门禁（.cataforge/baselines/"
            "complexity.json 棘轮，scan 刷新、review 只读）；函数定义行豁免 "
            'cataforge: allow(complexity_gate, reason="...")'
        ),
        severity="fail-on-error",
        category="complexity",
        modes=frozenset({"review", "scan"}),
        run=run,
    )
)
