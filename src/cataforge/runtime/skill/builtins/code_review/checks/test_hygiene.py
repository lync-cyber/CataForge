"""Test-suite hygiene probe (scan mode, informational).

Static heuristics over the project's test tree, driven by
``rules/test-hygiene-{lang}.yaml``:

* unlabeled slow-test candidates — a test file hits a slow pattern
  (subprocess / network / sleep / container) while no slow-marker pattern
  appears anywhere in the file;
* per-test expensive-setup candidates — a per-test setup declaration is
  followed within a short window by a slow pattern, suggesting a
  deterministic expensive environment rebuilt for every test.

Both signals feed Layer 2 severity aggregation; the probe never gates.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cataforge.runtime.skill.builtins.code_review.engine.context import CheckContext
from cataforge.runtime.skill.builtins.code_review.engine.findings import Finding
from cataforge.runtime.skill.builtins.code_review.engine.pragmas import file_allowance
from cataforge.runtime.skill.builtins.code_review.engine.registry import (
    CheckSpec,
    register_check,
)
from cataforge.runtime.skill.rules.loader import compile_flags, discover_rules

_BUILTIN_MODULE = "cataforge.runtime.skill.builtins.code_review"
_SKILL_ID = "code-review"

CHECK_ID = "code_review.test_hygiene"
_SETUP_WINDOW_LINES = 15
_MAX_SETUP_FINDINGS_PER_FILE = 5


@dataclass(frozen=True)
class HygieneRule:
    extensions: frozenset[str]
    test_file_patterns: tuple[re.Pattern[str], ...]
    slow_patterns: tuple[tuple[re.Pattern[str], str], ...]
    marker_patterns: tuple[re.Pattern[str], ...]
    setup_decl_patterns: tuple[re.Pattern[str], ...]


@dataclass(frozen=True)
class HygieneRuleSet:
    by_language: dict[str, HygieneRule]

    def rule_for_extension(self, ext: str) -> HygieneRule | None:
        ext_lower = ext.lower()
        for rule in self.by_language.values():
            if ext_lower in rule.extensions:
                return rule
        return None

    def scanned_extensions(self) -> frozenset[str]:
        out: set[str] = set()
        for rule in self.by_language.values():
            if rule.slow_patterns:
                out.update(rule.extensions)
        return frozenset(out)


def _patterns(spec_raw: dict[str, Any], key: str) -> tuple[re.Pattern[str], ...]:
    return tuple(
        re.compile(p["regex"], compile_flags(p.get("flags"))) for p in (spec_raw.get(key) or [])
    )


def _labeled_patterns(
    spec_raw: dict[str, Any], key: str
) -> tuple[tuple[re.Pattern[str], str], ...]:
    return tuple(
        (re.compile(p["regex"], compile_flags(p.get("flags"))), p.get("label", ""))
        for p in (spec_raw.get(key) or [])
    )


def load_hygiene_rules(project_root: Path | None = None) -> HygieneRuleSet:
    by_language: dict[str, HygieneRule] = {}
    specs = discover_rules(_SKILL_ID, builtin_module=_BUILTIN_MODULE, project_root=project_root)
    for (rule_type, language), spec in specs.items():
        if rule_type != "test_hygiene":
            continue
        by_language[language] = HygieneRule(
            extensions=spec.extensions,
            test_file_patterns=_patterns(spec.raw, "test_file_patterns"),
            slow_patterns=_labeled_patterns(spec.raw, "slow_patterns"),
            marker_patterns=_patterns(spec.raw, "marker_patterns"),
            setup_decl_patterns=_patterns(spec.raw, "setup_decl_patterns"),
        )
    return HygieneRuleSet(by_language)


def _is_test_file(path: Path, scan_root: Path, rule: HygieneRule) -> bool:
    # 只对 scan 根以内的相对路径做目录式匹配 — 根以外的祖先目录名
    # （如工作区恰好叫 tests/）不得把整棵源码树误判为测试文件。
    try:
        rel = path.relative_to(scan_root)
    except ValueError:
        rel = path
    return any(p.search(rel.as_posix()) for p in rule.test_file_patterns)


def _slow_hits(lines: list[str], rule: HygieneRule) -> list[tuple[int, str]]:
    hits: list[tuple[int, str]] = []
    for lineno, line in enumerate(lines, start=1):
        for pattern, label in rule.slow_patterns:
            if pattern.search(line):
                hits.append((lineno, label))
                break
    return hits


def _unlabeled_slow_finding(
    path: Path, text: str, lines: list[str], rule: HygieneRule
) -> Finding | None:
    hits = _slow_hits(lines, rule)
    if not hits:
        return None
    if any(p.search(text) for p in rule.marker_patterns):
        return None
    labels = list(dict.fromkeys(label for _, label in hits))
    return Finding(
        check_id=CHECK_ID,
        severity="info",
        category="test-quality",
        detail=(
            f"无标签慢测候选: {len(hits)} 处（{', '.join(labels)}）"
            "— 按项目慢测标签约定打标，或改进程内验证"
        ),
        file=str(path),
        line=hits[0][0],
    )


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def _setup_window(lines: list[str], decl_idx: int) -> list[str]:
    """声明行 + 其函数体；函数体开始后一旦回落到声明缩进级即截断 —
    相邻的同级测试函数不进入窗口。装饰器式声明允许紧随一行同级
    函数头（same_indent_budget）。"""
    decl_indent = _indent(lines[decl_idx])
    window = [lines[decl_idx]]
    body_started = False
    same_indent_budget = 1
    for line in lines[decl_idx + 1 : decl_idx + _SETUP_WINDOW_LINES]:
        if not line.strip():
            continue
        if _indent(line) > decl_indent:
            body_started = True
        elif body_started or same_indent_budget == 0:
            break
        else:
            same_indent_budget -= 1
        window.append(line)
    return window


def _expensive_setup_findings(path: Path, lines: list[str], rule: HygieneRule) -> list[Finding]:
    if not rule.setup_decl_patterns:
        return []
    findings: list[Finding] = []
    for idx, line in enumerate(lines):
        if not any(p.search(line) for p in rule.setup_decl_patterns):
            continue
        lineno = idx + 1
        window = _setup_window(lines, idx)
        label = next(
            (
                lab
                for wline in window
                for pattern, lab in rule.slow_patterns
                if pattern.search(wline)
            ),
            None,
        )
        if label is None:
            continue
        findings.append(
            Finding(
                check_id=CHECK_ID,
                severity="info",
                category="test-quality",
                detail=(
                    f"每测重建昂贵 setup 候选（{label}）"
                    "— 确定性昂贵 setup 应升 suite 级共享 fixture 复用"
                ),
                file=str(path),
                line=lineno,
            )
        )
        if len(findings) >= _MAX_SETUP_FINDINGS_PER_FILE:
            break
    return findings


def _scan_file(path: Path, rule: HygieneRule) -> list[Finding]:
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return []
    allowance = file_allowance(text, CHECK_ID)
    if allowance is not None:
        if allowance.reason:
            return []
        return [
            Finding(
                check_id=CHECK_ID,
                severity="warn",
                category="test-quality",
                detail="allow(test_hygiene) 缺 reason — 豁免生效但须补充理由",
                file=str(path),
                line=allowance.line,
            )
        ]
    lines = text.splitlines()
    findings: list[Finding] = []
    unlabeled = _unlabeled_slow_finding(path, text, lines, rule)
    if unlabeled is not None:
        findings.append(unlabeled)
    findings.extend(_expensive_setup_findings(path, lines, rule))
    return findings


def run(ctx: CheckContext) -> list[Finding]:
    rules = load_hygiene_rules(ctx.project_root)
    exts = rules.scanned_extensions()
    if not exts:
        return []
    scan_root = ctx.target if ctx.target.is_dir() else ctx.target.parent
    findings: list[Finding] = []
    for path in ctx.files(exts):
        rule = rules.rule_for_extension(path.suffix)
        if rule is None or not _is_test_file(path, scan_root, rule):
            continue
        findings.extend(_scan_file(path, rule))
    return findings


register_check(
    CheckSpec(
        id=CHECK_ID,
        title=(
            "测试套件卫生探针（rules/test-hygiene-{lang}.yaml 驱动）— 无标签慢测候选 / "
            "每测重建昂贵 setup 候选，informational（文件级豁免："
            'cataforge: allow(test_hygiene, reason="...")）'
        ),
        severity="informational",
        category="test-quality",
        modes=frozenset({"scan"}),
        run=run,
    )
)
