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

import sys
from pathlib import Path

from cataforge.runtime.skill.builtins.testing.e2e_patterns import (
    all_extensions,
    rule_for_extension,
)
from cataforge.utils.common import ensure_utf8


def collect_e2e_files(target: Path) -> list[Path]:
    exts = all_extensions()
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


def scan_file(path: Path) -> tuple[list[tuple[int, str, str]], int]:
    """Return ``(backdoor_findings, real_input_count)`` for *path*."""
    findings: list[tuple[int, str, str]] = []
    real_input = 0
    rule = rule_for_extension(path.suffix)
    if rule is None:
        return findings, 0
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
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


def run(target: str) -> int:
    base = Path(target)
    if not base.exists():
        print(f"ERROR: 目标路径不存在: {base}")
        return 2

    files = collect_e2e_files(base)
    print(f"e2e_scan: 扫描 {len(files)} 个 e2e 文件 @ {base}")
    print("=" * 50)

    backdoor_total = 0
    real_input_total = 0
    for f in files:
        findings, real_input = scan_file(f)
        real_input_total += real_input
        for lineno, label, snippet in findings:
            backdoor_total += 1
            print(f"WARN: [{f}:{lineno}] e2e_backdoor_scan ({label}): {snippet}")

    if files and real_input_total == 0:
        print(
            "WARN: e2e_real_input_presence — 整个 e2e 套件未发现任何真实交互调用 "
            "(keyboard.type / page.fill / page.click / page.press / .type)；"
            "可能完全依赖 fixture/store 注入"
        )

    print()
    print("=" * 50)
    print(
        f"Summary: {backdoor_total} backdoor WARN, "
        f"{real_input_total} real-input call(s) across {len(files)} file(s)"
    )
    print("RESULT: PASS" + (" (warnings only)" if backdoor_total or not real_input_total else ""))
    return 0


def main() -> None:
    ensure_utf8()
    if len(sys.argv) < 2 or sys.argv[1] in {"-h", "--help"}:
        print(
            "用法: python -m cataforge.runtime.skill.builtins.testing.e2e_scan <e2e_dir>"
        )
        sys.exit(2)
    sys.exit(run(sys.argv[1]))


if __name__ == "__main__":
    main()
