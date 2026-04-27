"""code_lint.py — Code static analysis (Code Review Layer 1).

Two operation modes:

* default (no flag): per-file lint + format using mainstream tools
  (ESLint/Prettier/Ruff/dotnet-format/golangci-lint/clippy). Used by
  the per-task TDD code-review path.

* ``scan``: project-level health scan layered on top of the lint pass.
  Adds duplication / dead-code / complexity probes (vulture, ts-prune,
  jscpd, radon, gocyclo when present). Tools that aren't installed
  emit WARN and are skipped — the scan never becomes a hard gate on
  toolchain availability.

Exit codes follow the §Layer 1 调用协议: 0=PASS, 1=fail-with-issues,
2=usage error / target missing.

Usage:
  python -m cataforge.skill.builtins.code_review.code_lint <file_or_dir> [--fix]
  python -m cataforge.skill.builtins.code_review.code_lint scan <path> \
        [--focus <category[,category...]>]
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from cataforge.utils.common import ensure_utf8_stdio

EXCLUDE_DIRS = {
    "node_modules", ".git", "dist", "build", "__pycache__",
    ".venv", "venv", ".next", "coverage", "bin", "obj",
}

LINTERS = [
    {
        "extensions": {".js", ".ts", ".jsx", ".tsx"},
        "tools": [
            {"name": "ESLint", "detect": ["npx", "eslint", "--version"],
             "check": ["npx", "eslint"], "fix": ["npx", "eslint", "--fix"]},
            {"name": "Prettier", "detect": ["npx", "prettier", "--version"],
             "check": ["npx", "prettier", "--check"], "fix": ["npx", "prettier", "--write"]},
        ],
    },
    {
        "extensions": {".py"},
        "tools": [
            {"name": "Ruff Check", "detect": ["ruff", "--version"],
             "check": ["ruff", "check"], "fix": ["ruff", "check", "--fix"]},
            {"name": "Ruff Format", "detect": ["ruff", "--version"],
             "check": ["ruff", "format", "--check"], "fix": ["ruff", "format"]},
        ],
    },
    {
        "extensions": {".cs"},
        "tools": [
            {"name": "dotnet format", "detect": ["dotnet", "--version"],
             "check": ["dotnet", "format", "--verify-no-changes", "--include"],
             "fix": ["dotnet", "format", "--include"]},
        ],
    },
    {
        "extensions": {".go"},
        "tools": [
            {"name": "golangci-lint", "detect": ["golangci-lint", "--version"],
             "check": ["golangci-lint", "run"],
             "fix": ["golangci-lint", "run", "--fix"]},
        ],
    },
    {
        "extensions": {".rs"},
        "tools": [
            {"name": "clippy", "detect": ["cargo", "clippy", "--version"],
             "check": ["cargo", "clippy", "--", "-D", "warnings"],
             "fix": ["cargo", "clippy", "--fix", "--allow-dirty"]},
        ],
    },
]

ALL_EXTENSIONS: set[str] = set()
for _group in LINTERS:
    ALL_EXTENSIONS.update(_group["extensions"])


# Project-level rot probes for the ``scan`` operation. Each entry maps a
# COMMON-RULES §统一问题分类体系 category to a list of probe commands.
# Probes that fail to launch (tool missing) emit WARN; non-zero exits
# without crash count as findings.
SCAN_PROBES: dict[str, list[dict]] = {
    "duplication": [
        {
            "name": "jscpd",
            "extensions": {
                ".js", ".ts", ".jsx", ".tsx", ".py", ".go",
                ".cs", ".rs", ".java", ".kt", ".swift",
            },
            "detect": ["npx", "jscpd", "--version"],
            "build_cmd": lambda target: ["npx", "jscpd", "--silent", str(target)],
            "fail_on_nonzero": False,
        },
        {
            # PMD CPD is the canonical Java duplication detector — better
            # tokenization than jscpd for Java's verbose syntax. Also
            # supports JSP / Apex / PLSQL / Modelica out of the box, so
            # we register it whenever the project has .java files even
            # if jscpd is also installed (the two report side-by-side).
            "name": "pmd-cpd",
            "extensions": {".java"},
            "detect": ["pmd", "cpd", "--help"],
            "build_cmd": lambda target: [
                "pmd", "cpd", "--minimum-tokens", "100",
                "--language", "java", "--dir", str(target),
            ],
            "fail_on_nonzero": False,
        },
    ],
    "dead-code": [
        {
            "name": "vulture",
            "extensions": {".py"},
            "detect": ["vulture", "--version"],
            "build_cmd": lambda target: ["vulture", str(target), "--min-confidence", "70"],
            "fail_on_nonzero": True,
        },
        {
            "name": "ts-prune",
            "extensions": {".ts", ".tsx"},
            "detect": ["npx", "ts-prune", "--version"],
            "build_cmd": lambda target: ["npx", "ts-prune", "--project", str(target)],
            "fail_on_nonzero": False,
        },
        {
            # cargo-machete detects unused dependencies declared in
            # Cargo.toml — the closest "dead-code" signal that Rust's
            # type-and-borrow checker doesn't already catch. Triggered
            # by the presence of any .rs file in the target.
            "name": "cargo-machete",
            "extensions": {".rs"},
            "detect": ["cargo", "machete", "--help"],
            "build_cmd": lambda target: ["cargo", "machete", str(target)],
            "fail_on_nonzero": True,
        },
    ],
    "complexity": [
        {
            "name": "radon (cc)",
            "extensions": {".py"},
            "detect": ["radon", "--version"],
            "build_cmd": lambda target: ["radon", "cc", "-n", "C", "-a", str(target)],
            "fail_on_nonzero": False,
        },
        {
            "name": "gocyclo",
            "extensions": {".go"},
            "detect": ["gocyclo", "-?"],
            "build_cmd": lambda target: ["gocyclo", "-over", "15", str(target)],
            "fail_on_nonzero": False,
        },
    ],
}

VALID_FOCUS = set(SCAN_PROBES.keys())


class CodeLinter:
    def __init__(self, target: str, fix: bool = False) -> None:
        self.target = Path(target)
        self.fix = fix
        self.errors = 0
        self.warnings = 0
        self.files_checked = 0
        self.tool_cache: dict[str, bool] = {}

    def tool_available(self, tool: dict) -> bool:
        name = tool["name"]
        if name not in self.tool_cache:
            try:
                subprocess.run(tool["detect"], capture_output=True, timeout=15)
                self.tool_cache[name] = True
            except (FileNotFoundError, subprocess.TimeoutExpired):
                self.tool_cache[name] = False
                print(f"WARN: {name} 未安装，跳过")
        return self.tool_cache[name]

    def collect_files(self) -> list[Path]:
        if self.target.is_file():
            return [self.target]
        files = []
        for p in self.target.rglob("*"):
            if any(part in EXCLUDE_DIRS for part in p.parts):
                continue
            if p.is_file() and p.suffix.lower() in ALL_EXTENSIONS:
                files.append(p)
        return sorted(files)

    def run_tool(self, tool: dict, filepath: Path) -> None:
        if not self.tool_available(tool):
            return
        cmd = (tool["fix"] if self.fix else tool["check"]) + [str(filepath)]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode != 0:
                output = (result.stdout + result.stderr).strip()
                err_lines = [line for line in output.splitlines() if line.strip()]
                if self.fix:
                    print(f"FIXED: [{filepath}] {tool['name']}")
                else:
                    self.errors += 1
                    print(f"FAIL: [{filepath}] {tool['name']}")
                    for line in err_lines[:20]:
                        print(f"  {line}")
        except subprocess.TimeoutExpired:
            self.warnings += 1
            print(f"WARN: [{filepath}] {tool['name']} 超时")

    def run(self) -> int:
        if not self.target.exists():
            print(f"ERROR: 目标路径不存在: {self.target}")
            return 2

        files = self.collect_files()
        if not files:
            print("WARN: 未找到可检查的代码文件")
            return 0

        checked_files: set[Path] = set()
        for f in files:
            ext = f.suffix.lower()
            for linter_group in LINTERS:
                if ext in linter_group["extensions"]:
                    if f not in checked_files:
                        self.files_checked += 1
                        checked_files.add(f)
                    for tool in linter_group["tools"]:
                        self.run_tool(tool, f)

        print()
        print("=========================================")
        print("Lint Check Summary")
        print(f"  Files checked: {self.files_checked}")
        print(f"  Errors: {self.errors}")
        print(f"  Warnings: {self.warnings}")
        print("=========================================")

        if self.errors > 0:
            print("RESULT: FAIL")
            return 1

        print("RESULT: PASS")
        return 0


class CodeScanner:
    """Project-level health scan: lint + duplication + dead-code + complexity.

    Each focus category gates which probes run. Probes that aren't
    installed emit WARN and the scan continues — the goal is "give the
    user whatever signal is locally available", not "fail because
    radon isn't installed".
    """

    def __init__(self, target: str, focus: list[str] | None = None) -> None:
        self.target = Path(target)
        self.focus = focus or sorted(VALID_FOCUS)
        self.findings = 0
        self.skipped = 0

    def collect_extensions(self) -> set[str]:
        if self.target.is_file():
            return {self.target.suffix.lower()}
        seen: set[str] = set()
        for p in self.target.rglob("*"):
            if any(part in EXCLUDE_DIRS for part in p.parts):
                continue
            if p.is_file():
                seen.add(p.suffix.lower())
        return seen

    def run_probe(self, probe: dict, present_exts: set[str]) -> None:
        name = probe["name"]
        if not (probe["extensions"] & present_exts):
            return
        try:
            subprocess.run(probe["detect"], capture_output=True, timeout=15)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            print(f"WARN: probe '{name}' 未安装，跳过")
            self.skipped += 1
            return
        cmd = probe["build_cmd"](self.target)
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        except subprocess.TimeoutExpired:
            print(f"WARN: probe '{name}' 超时")
            self.skipped += 1
            return
        output = (result.stdout + "\n" + result.stderr).strip()
        non_empty = bool(output)
        signal = (
            (probe["fail_on_nonzero"] and result.returncode != 0)
            or (not probe["fail_on_nonzero"] and non_empty)
        )
        if signal:
            self.findings += 1
            print(f"FINDING: [{name}]")
            for line in output.splitlines()[:30]:
                print(f"  {line}")
        else:
            print(f"PASS: [{name}] no findings")

    def run(self) -> int:
        if not self.target.exists():
            print(f"ERROR: 目标路径不存在: {self.target}")
            return 2

        invalid = [c for c in self.focus if c not in VALID_FOCUS]
        if invalid:
            print(
                f"ERROR: 无效的 --focus 值: {invalid}; "
                f"可选: {sorted(VALID_FOCUS)}"
            )
            return 2

        print(f"Scanning {self.target} (focus: {','.join(self.focus)})")
        print("=" * 50)

        # Layer 1 lint pass first — catches surface defects before
        # paying for the slower duplication / complexity probes.
        lint_rc = CodeLinter(str(self.target), fix=False).run()
        print()

        present_exts = self.collect_extensions()
        for category in self.focus:
            print(f"\n--- {category} ---")
            for probe in SCAN_PROBES[category]:
                self.run_probe(probe, present_exts)

        print()
        print("=" * 50)
        print("Scan Summary")
        print(f"  Findings: {self.findings}")
        print(f"  Probes skipped (tool missing/timeout): {self.skipped}")
        print(f"  Lint exit: {lint_rc}")
        print("=" * 50)

        # The scan only fails on lint errors — rot findings are
        # informational signals, not gates. Otherwise every project
        # without a clean dead-code report would be 'failing'.
        if lint_rc != 0:
            print("RESULT: FAIL (lint errors)")
            return 1
        print("RESULT: PASS")
        return 0


def main() -> None:
    ensure_utf8_stdio()
    if len(sys.argv) < 2:
        print(
            "用法:\n"
            "  python -m cataforge.skill.builtins.code_review.code_lint"
            " <file_or_dir> [--fix]\n"
            "  python -m cataforge.skill.builtins.code_review.code_lint"
            " scan <path> [--focus <category[,category...]>]"
        )
        sys.exit(2)

    if sys.argv[1] == "scan":
        if len(sys.argv) < 3:
            print(
                "用法: python -m cataforge.skill.builtins.code_review.code_lint"
                " scan <path> [--focus <category[,category...]>]"
            )
            sys.exit(2)
        target = sys.argv[2]
        focus: list[str] | None = None
        if "--focus" in sys.argv:
            idx = sys.argv.index("--focus")
            if idx + 1 >= len(sys.argv):
                print("ERROR: --focus 缺少参数值")
                sys.exit(2)
            focus = [c.strip() for c in sys.argv[idx + 1].split(",") if c.strip()]
        scanner = CodeScanner(target, focus)
        sys.exit(scanner.run())

    target_path = sys.argv[1]
    fix_mode = "--fix" in sys.argv
    linter = CodeLinter(target_path, fix_mode)
    sys.exit(linter.run())


if __name__ == "__main__":
    main()
