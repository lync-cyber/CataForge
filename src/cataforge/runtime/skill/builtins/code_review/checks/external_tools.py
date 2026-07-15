"""External linter/formatter adapters (per-file, extension-dispatched).

Each :class:`LintFamily` is one manifest entry; a family may drive several
tool commands (Ruff check + format). Tools that aren't installed emit one
WARN finding and are skipped — toolchain availability never hard-gates.
Families with ``config_markers`` are likewise skipped with a WARN when the
project root carries none of the marker files: a resolvable binary on a
project that never adopted the tool is "not configured", not a failure.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from dataclasses import dataclass

from cataforge.runtime.skill.builtins.code_review.engine.context import CheckContext
from cataforge.runtime.skill.builtins.code_review.engine.findings import Finding
from cataforge.runtime.skill.builtins.code_review.engine.fs import resolved
from cataforge.runtime.skill.builtins.code_review.engine.registry import (
    CheckSpec,
    register_check,
)
from cataforge.utils.run_subprocess import run as run_proc

TOOL_TIMEOUT_SECS = 60
_OUTPUT_HEAD_LINES = 20


@dataclass(frozen=True)
class Tool:
    name: str
    detect: tuple[str, ...]
    check: tuple[str, ...]
    fix: tuple[str, ...]


@dataclass(frozen=True)
class LintFamily:
    check_id: str
    title: str
    extensions: frozenset[str]
    tools: tuple[Tool, ...]
    config_markers: tuple[str, ...] = ()


_JS_EXTS = frozenset({".js", ".ts", ".jsx", ".tsx"})

_ESLINT_CONFIG_MARKERS: tuple[str, ...] = (
    "eslint.config.js",
    "eslint.config.mjs",
    "eslint.config.cjs",
    "eslint.config.ts",
    "eslint.config.mts",
    "eslint.config.cts",
    ".eslintrc.js",
    ".eslintrc.cjs",
    ".eslintrc.json",
    ".eslintrc.yml",
    ".eslintrc.yaml",
)

FAMILIES: tuple[LintFamily, ...] = (
    LintFamily(
        check_id="code_review.eslint",
        title="ESLint (.js/.ts/.jsx/.tsx)",
        extensions=_JS_EXTS,
        tools=(
            Tool(
                name="ESLint",
                detect=("npx", "eslint", "--version"),
                check=("npx", "eslint"),
                fix=("npx", "eslint", "--fix"),
            ),
        ),
        config_markers=_ESLINT_CONFIG_MARKERS,
    ),
    LintFamily(
        check_id="code_review.prettier",
        title="Prettier 格式化检查 (.js/.ts/.jsx/.tsx)",
        extensions=_JS_EXTS,
        tools=(
            Tool(
                name="Prettier",
                detect=("npx", "prettier", "--version"),
                check=("npx", "prettier", "--check"),
                fix=("npx", "prettier", "--write"),
            ),
        ),
    ),
    LintFamily(
        check_id="code_review.ruff",
        title="Ruff check + format (.py)",
        extensions=frozenset({".py"}),
        tools=(
            Tool(
                name="Ruff Check",
                detect=("ruff", "--version"),
                check=("ruff", "check"),
                fix=("ruff", "check", "--fix"),
            ),
            Tool(
                name="Ruff Format",
                detect=("ruff", "--version"),
                check=("ruff", "format", "--check"),
                fix=("ruff", "format"),
            ),
        ),
    ),
    LintFamily(
        check_id="code_review.dotnet_format",
        title="dotnet format --verify-no-changes (.cs)",
        extensions=frozenset({".cs"}),
        tools=(
            Tool(
                name="dotnet format",
                detect=("dotnet", "--version"),
                check=("dotnet", "format", "--verify-no-changes", "--include"),
                fix=("dotnet", "format", "--include"),
            ),
        ),
    ),
    LintFamily(
        check_id="code_review.golangci",
        title="golangci-lint run (.go)",
        extensions=frozenset({".go"}),
        tools=(
            Tool(
                name="golangci-lint",
                detect=("golangci-lint", "--version"),
                check=("golangci-lint", "run"),
                fix=("golangci-lint", "run", "--fix"),
            ),
        ),
    ),
    LintFamily(
        check_id="code_review.clippy",
        title="cargo clippy -D warnings (.rs)",
        extensions=frozenset({".rs"}),
        tools=(
            Tool(
                name="clippy",
                detect=("cargo", "clippy", "--version"),
                check=("cargo", "clippy", "--", "-D", "warnings"),
                fix=("cargo", "clippy", "--fix", "--allow-dirty"),
            ),
        ),
    ),
)

LINT_EXTENSIONS: frozenset[str] = frozenset().union(*(f.extensions for f in FAMILIES))


def _make_runner(family: LintFamily) -> Callable[[CheckContext], list[Finding]]:
    def run(ctx: CheckContext) -> list[Finding]:
        findings: list[Finding] = []
        files = ctx.files(family.extensions)
        if not files:
            return findings
        if family.config_markers:
            root = ctx.project_root or (ctx.target if ctx.target.is_dir() else ctx.target.parent)
            if not any((root / marker).is_file() for marker in family.config_markers):
                findings.append(
                    Finding(
                        check_id=family.check_id,
                        severity="warn",
                        category="convention",
                        detail=(
                            f"{family.title}: 项目根未发现配置文件"
                            f"（{family.config_markers[0]} 等），未采纳该工具，跳过"
                        ),
                    )
                )
                return findings
        for tool in family.tools:
            if not ctx.tool_available(tool.name, tool.detect) and ctx.first_missing_report(
                tool.name
            ):
                findings.append(
                    Finding(
                        check_id=family.check_id,
                        severity="warn",
                        category="convention",
                        detail=f"{tool.name} 未安装，跳过",
                    )
                )
        for path in files:
            for tool in family.tools:
                if not ctx.tool_cache.get(tool.name):
                    continue
                cmd = list(tool.fix if ctx.fix else tool.check) + [str(path)]
                try:
                    result = run_proc(resolved(cmd), timeout=TOOL_TIMEOUT_SECS)
                except subprocess.TimeoutExpired:
                    findings.append(
                        Finding(
                            check_id=family.check_id,
                            severity="warn",
                            category="convention",
                            detail=f"{tool.name} 超时",
                            file=str(path),
                        )
                    )
                    continue
                if result.returncode == 0:
                    continue
                if ctx.fix:
                    findings.append(
                        Finding(
                            check_id=family.check_id,
                            severity="info",
                            category="convention",
                            detail=f"FIXED: {tool.name}",
                            file=str(path),
                        )
                    )
                    continue
                output = (result.stdout + result.stderr).strip()
                err_lines = [line for line in output.splitlines() if line.strip()]
                detail = "\n".join([tool.name, *err_lines[:_OUTPUT_HEAD_LINES]])
                findings.append(
                    Finding(
                        check_id=family.check_id,
                        severity="fail",
                        category="convention",
                        detail=detail,
                        file=str(path),
                    )
                )
        return findings

    return run


for _family in FAMILIES:
    register_check(
        CheckSpec(
            id=_family.check_id,
            title=_family.title,
            severity="fail-on-error",
            category="convention",
            modes=frozenset({"review", "scan"}),
            run=_make_runner(_family),
        )
    )
