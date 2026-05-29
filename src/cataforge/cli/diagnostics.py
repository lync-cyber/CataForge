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

import re

from cataforge.cli.ui import DiagPattern

# ---------------------------------------------------------------------------
# Penpot — log patterns shared by `penpot start` failure reporter and
# `penpot doctor`.
# ---------------------------------------------------------------------------

PNPM_IGNORED_BUILDS = DiagPattern(
    needle=re.compile(r"ERR_PNPM_IGNORED_BUILDS|Ignored build scripts"),
    diagnosis="pnpm 10+ 拒绝执行 esbuild/sharp 等依赖的 build 脚本",
    fix_action=(
        "确认 PNPM_CONFIG_STRICT_DEP_BUILDS=false 已传入"
        "（cataforge 已默认注入）；若仍失败，多半是 Node 版本过新——"
        "建议安装 Node v22 LTS 后重试"
    ),
)

PNPM_BUILD_TOOLCHAIN_MISSING = DiagPattern(
    needle=re.compile(
        r"ERR_PNPM_RECURSIVE_RUN_FIRST_FAIL"
        r"|Cannot find module.*(?:typescript[\\/]bin[\\/]tsc"
        r"|esbuild[\\/]bin[\\/]esbuild)"
    ),
    diagnosis=(
        "@penpot/mcp 从源码构建时找不到 tsc/esbuild —— "
        "Node 版本超出兼容范围时 pnpm 工作区未正确落地构建工具链"
    ),
    fix_action="改用 Node v22 LTS 后重试（预检对过新 Node 仅警告不阻断）",
    fix_command="cataforge penpot remote",
)

NGINX_UPSTREAM_MISSING = DiagPattern(
    needle="host not found in upstream",
    diagnosis="Penpot frontend nginx 找不到 penpot-mcp 主机",
    fix_action="升级 cataforge 后重建容器",
    fix_command="cataforge penpot deploy",
)

PORT_IN_USE = DiagPattern(
    needle="EADDRINUSE",
    diagnosis="端口已被占用",
    fix_action="用 cataforge penpot stop 清理旧进程，或设置 PENPOT_MCP_SERVER_PORT 改用其他端口",
    fix_command="cataforge penpot stop",
)

PENPOT_PATTERNS: list[DiagPattern] = [
    PNPM_IGNORED_BUILDS,
    PNPM_BUILD_TOOLCHAIN_MISSING,
    NGINX_UPSTREAM_MISSING,
    PORT_IN_USE,
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


# ---------------------------------------------------------------------------
# Upgrade — manifest drift / merge conflict patterns.
# ---------------------------------------------------------------------------

UPGRADE_LOCAL_MODS = DiagPattern(
    needle=re.compile(r"user-modified|drift"),
    diagnosis="检测到本地修改与新 scaffold 冲突",
    fix_action=(
        "选项: (a) `cataforge upgrade apply --dry-run` 预览; "
        "(b) `cataforge upgrade rollback` 回退本地修改后重试; "
        "(c) 手动 diff 后保留必要修改再 apply"
    ),
)

UPGRADE_PATTERNS: list[DiagPattern] = [UPGRADE_LOCAL_MODS]
