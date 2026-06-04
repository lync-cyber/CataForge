"""Penpot log-diagnosis patterns.

Shared by the ``penpot start`` failure reporter (``mcp_process``) and the CLI
``penpot doctor`` diagnostics so a single declaration updates both surfaces.
"""

from __future__ import annotations

import re

from cataforge.utils.console import DiagPattern

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
