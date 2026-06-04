"""Shared diagnostic pattern registry for cataforge CLI subcommands.

Each subcommand that scans logs / stderr / process output for known failure
modes imports the relevant pattern list from here. Adding a new entry costs
one declaration; previously the same string ("ERR_PNPM_IGNORED_BUILDS", "host
not found in upstream", "EADDRINUSE", …) was duplicated across subcommands.

A ``DiagPattern`` carries:

* ``needle`` — substring or compiled regex to search for
* ``diagnosis`` — one-line human explanation
* ``fix_action`` — what the user should do (free text)
* ``fix_command`` — optional shell command rendered bold for copy-paste
* ``severity`` — ``"error"`` (red) or ``"warn"`` (yellow)
"""

from __future__ import annotations

from cataforge.adapter.integrations.penpot.patterns import (
    NGINX_UPSTREAM_MISSING,
    PENPOT_PATTERNS,
    PNPM_BUILD_TOOLCHAIN_MISSING,
    PNPM_IGNORED_BUILDS,
    PORT_IN_USE,
)
from cataforge.utils.console import DiagPattern

__all__ = [
    "DOCKER_MISSING",
    "DOCTOR_PATTERNS",
    "NGINX_UPSTREAM_MISSING",
    "NPX_MISSING",
    "PENPOT_PATTERNS",
    "PNPM_BUILD_TOOLCHAIN_MISSING",
    "PNPM_IGNORED_BUILDS",
    "PORT_IN_USE",
    "RUFF_MISSING",
]


# ---------------------------------------------------------------------------
# Doctor — external tool / env patterns.
# ---------------------------------------------------------------------------

RUFF_MISSING = DiagPattern(
    needle="ruff: not found",
    diagnosis="ruff 未安装，doctor 的 lint 检查被跳过",
    fix_action="安装 ruff 到当前虚拟环境",
    fix_command="uv pip install ruff",
    severity="warn",
)

NPX_MISSING = DiagPattern(
    needle="npx: not found",
    diagnosis="npx 未在 PATH 中，依赖 Node 工具链的集成将无法运行",
    fix_action="安装 Node.js v22 LTS（包含 npx）",
    fix_command="https://nodejs.org",
    severity="warn",
)

DOCKER_MISSING = DiagPattern(
    needle="docker: not found",
    diagnosis="docker 未安装，Penpot 自托管模式不可用",
    fix_action="安装 Docker Desktop 或改用 cataforge penpot remote",
    fix_command="cataforge penpot remote",
    severity="warn",
)

DOCTOR_PATTERNS: list[DiagPattern] = [
    RUFF_MISSING,
    NPX_MISSING,
    DOCKER_MISSING,
]
