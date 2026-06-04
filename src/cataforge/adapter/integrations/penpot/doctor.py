"""Penpot integration — diagnostic command."""

from __future__ import annotations

import os

from cataforge.adapter.integrations.penpot._constants import (
    MCP_LOG_FILE,
    SUPPORTED_NODE_MAJORS,
)
from cataforge.adapter.integrations.penpot.commands import (
    _print_status_table,
    _status_rows,
    print_header,
)
from cataforge.adapter.integrations.penpot.docker import _node_major
from cataforge.adapter.integrations.penpot.mcp_process import _diagnose_mcp_log, _tail_log
from cataforge.utils.common import (
    CYAN,
    NC,
    fail,
    get_command_version,
    has_command,
    info,
    ok,
    section,
    warn,
)


def cmd_doctor(config: dict) -> int:
    """Inspect compose file, MCP log, and service ports; suggest fixes."""
    print_header("Penpot 服务诊断")
    problems: list[str] = []
    actions: list[str] = []

    section("环境检查")
    if has_command("node"):
        node_ver = get_command_version(["node", "--version"])
        major = _node_major(node_ver)
        lo, hi = SUPPORTED_NODE_MAJORS[0], SUPPORTED_NODE_MAJORS[-1]
        if major is None or not (lo <= major <= hi):
            warn(f"Node.js {node_ver} 不在兼容范围 v{lo}–v{hi}")
            problems.append("node-version")
            actions.append("安装 Node v22 LTS（推荐通过 nvm/volta 管理）")
        else:
            ok(f"Node.js {node_ver}")
    else:
        fail("Node.js 未安装")
        problems.append("node-missing")
        actions.append("https://nodejs.org 安装 v22 LTS")

    section("compose 模板检查")
    compose_file = os.path.join(config["penpot_dir"], "docker-compose.yml")
    if os.path.isfile(compose_file):
        try:
            with open(compose_file) as fh:
                content = fh.read()
        except OSError:
            content = ""
        if "disable-mcp" in content and "PENPOT_MCP_URI" in content:
            ok("compose 已应用 nginx upstream 修复 (Bug 1)")
        else:
            warn("compose 文件未包含 disable-mcp / PENPOT_MCP_URI 占位（Bug 1 未修）")
            problems.append("compose-stale")
            actions.append("运行 `cataforge penpot deploy --force-recreate` 重写 compose 文件")
    else:
        info(f"未找到 compose 文件: {compose_file}")

    section("MCP 日志检查")
    if os.path.isfile(MCP_LOG_FILE):
        tail = _tail_log(MCP_LOG_FILE, lines=80)
        hints = _diagnose_mcp_log("\n".join(tail))
        if hints:
            for line in hints:
                print(f"  {line}")
            problems.append("mcp-startup")
        else:
            ok("MCP 日志未发现已知错误模式")
    else:
        info(f"未找到 MCP 日志: {MCP_LOG_FILE} (MCP 可能从未启动)")

    section("运行状态")
    rows = _status_rows(config)
    _print_status_table(rows)

    print()
    if not problems:
        ok("未发现已知问题")
        return 0
    section("修复建议")
    for n, msg in enumerate(actions, start=1):
        print(f"  {CYAN}{n}.{NC} {msg}")
    print()
    return 1
