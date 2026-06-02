"""e2e_scan.py — Testing skill Layer 1 backdoor + real-input scan.

Two checks on a tests/e2e/ tree:

* ``e2e_backdoor_scan`` — flags lines matching common test-only backdoor
  patterns (window-property injection, query-flag gates, store-bypass
  shortcuts) that let e2e suites pass without exercising the real user
  input path. Each match is WARN.

* ``e2e_real_input_presence`` — counts real browser interaction calls
  across all matched files. Zero such calls in the entire e2e tree is
  WARN: the suite likely fixture-injects state instead of typing.

Exit codes follow §Layer 1 调用协议: 0=PASS (with WARN allowed),
1=FAIL never used here (everything is WARN-only — the goal is to
surface anti-patterns for Layer 2 / qa-engineer review, not block CI).
2=usage error / target missing.

Usage:
  python -m cataforge.runtime.skill.builtins.testing.e2e_scan <e2e_dir>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from cataforge.core.paths import project_root_from_env
from cataforge.core.types import Severity
from cataforge.runtime.skill.builtins._shared import CheckReport, IssueCollector
from cataforge.runtime.skill.builtins.testing._render import render_text
from cataforge.runtime.skill.builtins.testing.e2e_patterns import E2ERuleSet, load_e2e_rules
from cataforge.utils.common import ensure_utf8


def collect_e2e_files(target: Path, rules: E2ERuleSet) -> list[Path]:
    exts = rules.all_extensions()
    if target.is_file():
        return [target] if target.suffix.lower() in exts else []
    files: list[Path] = []
    for p in target.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() not in exts:
            continue
        if any(part in {"node_modules", "dist", "build", ".next"} for part in p.parts):
            continue
        files.append(p)
    return sorted(files)


def scan_file(path: Path, rules: E2ERuleSet) -> tuple[list[tuple[int, str, str]], int]:
    """Return ``(backdoor_findings, real_input_count)`` for *path*."""
    findings: list[tuple[int, str, str]] = []
    real_input = 0
    rule = rules.rule_for_extension(path.suffix)
    if rule is None:
        return findings, 0
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return findings, 0
    for lineno, line in enumerate(text.splitlines(), start=1):
        for label, pattern in rule.backdoor_patterns:
            if pattern.search(line):
                findings.append((lineno, label, line.strip()[:100]))
        for pattern in rule.real_input_patterns:
            if pattern.search(line):
                real_input += 1
                break
    return findings, real_input


def collect(base: Path, project_root: Path | None = None) -> CheckReport:
    """Scan *base* and return a structured report (no console I/O).

    Every finding is advisory (WARN): backdoor matches per line, plus a
    single real-input-absence warning when the whole tree has zero real
    interaction calls. Counts land in ``summary`` for the renderer.
    Rules are resolved for *project_root* so project overrides apply.
    """
    rules = load_e2e_rules(project_root)
    files = collect_e2e_files(base, rules)
    issues = IssueCollector()

    backdoor_total = 0
    real_input_total = 0
    for f in files:
        findings, real_input = scan_file(f, rules)
        real_input_total += real_input
        for lineno, label, snippet in findings:
            backdoor_total += 1
            issues.add(
                Severity.LOW,
                "e2e_backdoor_scan",
                f"[{f}:{lineno}] e2e_backdoor_scan ({label}): {snippet}",
                path=str(f),
            )

    if files and real_input_total == 0:
        issues.add(
            Severity.LOW,
            "e2e_real_input_presence",
            "e2e_real_input_presence — 整个 e2e 套件未发现任何真实交互调用 "
            "(keyboard.type / page.fill / page.click / page.press / .type)；"
            "可能完全依赖 fixture/store 注入",
        )

    return CheckReport(
        issues,
        summary={
            "backdoor_total": backdoor_total,
            "real_input_total": real_input_total,
            "file_count": len(files),
        },
        headline=f"e2e_scan: 扫描 {len(files)} 个 e2e 文件 @ {base}",
    )


def run(target: str) -> int:
    """Scan *target* and print the text report. Returns 0, or 2 if missing."""
    base = Path(target)
    if not base.exists():
        print(f"ERROR: 目标路径不存在: {base}")
        return 2
    print(render_text(collect(base, project_root_from_env())))
    return 0


def main() -> None:
    ensure_utf8()
    args = sys.argv[1:]
    fmt = "text"
    if "--format" in args:
        idx = args.index("--format")
        fmt = args[idx + 1] if idx + 1 < len(args) else "text"
        args = args[:idx] + args[idx + 2 :]
    if not args or args[0] in {"-h", "--help"}:
        print("用法: python -m cataforge.runtime.skill.builtins.testing.e2e_scan <e2e_dir>")
        sys.exit(2)

    base = Path(args[0])
    if not base.exists():
        print(f"ERROR: 目标路径不存在: {base}")
        sys.exit(2)
    report = collect(base, project_root_from_env())
    if fmt == "json":
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(render_text(report))
    sys.exit(0)


if __name__ == "__main__":
    main()
