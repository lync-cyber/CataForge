#!/usr/bin/env python3
"""code_lint.py — 代码静态检查 (Code Review Layer 1)

用法: python code_lint.py <file_or_dir> [--fix]
返回: exit 0=全部通过, exit 1=有错误

默认检查模式(仅报告)；传入 --fix 则自动修复。
工具不存在时跳过并 WARN，不阻断检查流程。
"""

import sys
import io
import subprocess
from pathlib import Path

# Ensure UTF-8 output on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# 排除目录
EXCLUDE_DIRS = {
    "node_modules",
    ".git",
    "dist",
    "build",
    "__pycache__",
    ".venv",
    "venv",
    ".next",
    "coverage",
    "bin",
    "obj",
}

# 语言→工具映射
LINTERS = [
    {
        "extensions": {".js", ".ts", ".jsx", ".tsx"},
        "tools": [
            {
                "name": "ESLint",
                "detect": ["npx", "eslint", "--version"],
                "check": ["npx", "eslint"],
                "fix": ["npx", "eslint", "--fix"],
            },
            {
                "name": "Prettier",
                "detect": ["npx", "prettier", "--version"],
                "check": ["npx", "prettier", "--check"],
                "fix": ["npx", "prettier", "--write"],
            },
        ],
    },
    {
        "extensions": {".py"},
        "tools": [
            {
                "name": "Ruff Check",
                "detect": ["ruff", "--version"],
                "check": ["ruff", "check"],
                "fix": ["ruff", "check", "--fix"],
            },
            {
                "name": "Ruff Format",
                "detect": ["ruff", "--version"],
                "check": ["ruff", "format", "--check"],
                "fix": ["ruff", "format"],
            },
        ],
    },
    {
        "extensions": {".cs"},
        "tools": [
            {
                "name": "dotnet format",
                "detect": ["dotnet", "--version"],
                "check": ["dotnet", "format", "--verify-no-changes", "--include"],
                "fix": ["dotnet", "format", "--include"],
            },
        ],
    },
    {
        "extensions": {".go"},
        "tools": [
            {
                "name": "golangci-lint",
                "detect": ["golangci-lint", "--version"],
                "check": ["golangci-lint", "run"],
                "fix": ["golangci-lint", "run", "--fix"],
            },
        ],
    },
    {
        "extensions": {".rs"},
        "tools": [
            {
                "name": "clippy",
                "detect": ["cargo", "clippy", "--version"],
                "check": ["cargo", "clippy", "--", "-D", "warnings"],
                "fix": ["cargo", "clippy", "--fix", "--allow-dirty"],
            },
        ],
    },
]

# 所有支持的扩展名集合
ALL_EXTENSIONS = set()
for group in LINTERS:
    ALL_EXTENSIONS.update(group["extensions"])


class CodeLinter:
    def __init__(self, target: str, fix: bool = False):
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
                subprocess.run(
                    tool["detect"],
                    capture_output=True,
                    timeout=15,
                )
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

        checked_files = set()
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


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python code_lint.py <file_or_dir> [--fix]")
        print("返回: exit 0=全部通过, exit 1=有错误, exit 2=参数错误")
        sys.exit(2)

    target_path = sys.argv[1]
    fix_mode = "--fix" in sys.argv
    linter = CodeLinter(target_path, fix_mode)
    sys.exit(linter.run())
