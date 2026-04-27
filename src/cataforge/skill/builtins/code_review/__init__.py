"""Built-in code-review skill.

Layer 1 (lint) + Layer 2 (semantic, in SKILL.md prose) + scan operation.
``CHECKS_MANIFEST`` is the contract for `framework-review` to verify that
the skill's prose ``## Layer 1 检查项`` section stays in lockstep with
what the script actually runs.
"""

from __future__ import annotations

CHECKS_MANIFEST: tuple[dict[str, str], ...] = (
    {
        "id": "code_lint.eslint",
        "title": "ESLint (.js/.ts/.jsx/.tsx)",
        "severity": "fail-on-error",
    },
    {
        "id": "code_lint.prettier",
        "title": "Prettier 格式化检查 (.js/.ts/.jsx/.tsx)",
        "severity": "fail-on-error",
    },
    {
        "id": "code_lint.ruff",
        "title": "Ruff check + format (.py)",
        "severity": "fail-on-error",
    },
    {
        "id": "code_lint.dotnet_format",
        "title": "dotnet format --verify-no-changes (.cs)",
        "severity": "fail-on-error",
    },
    {
        "id": "code_lint.golangci",
        "title": "golangci-lint run (.go)",
        "severity": "fail-on-error",
    },
    {
        "id": "code_lint.clippy",
        "title": "cargo clippy -D warnings (.rs)",
        "severity": "fail-on-error",
    },
    {
        "id": "code_lint.tool_missing",
        "title": "工具未安装时跳过并 WARN，不阻断检查流程",
        "severity": "warn",
    },
)
