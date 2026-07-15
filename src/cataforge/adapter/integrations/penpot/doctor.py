"""Penpot integration — diagnostic command."""

from __future__ import annotations

import os
from typing import Any

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
from cataforge.utils.console import (
    CYAN,
    NC,
    fail,
    info,
    ok,
    section,
    warn,
)
from cataforge.utils.process import get_command_version, has_command


def _check_node_env(problems: list[str], actions: list[str]) -> None:
    section("环境检查")
    if not has_command("node"):
        fail("Node.js 未安装")
        problems.append("node-missing")
        actions.append("https://nodejs.org 安装 v22 LTS")
        return
    node_ver = get_command_version(["node", "--version"])
    major = _node_major(node_ver)
    lo, hi = SUPPORTED_NODE_MAJORS[0], SUPPORTED_NODE_MAJORS[-1]
    if major is None or not (lo <= major <= hi):
        warn(f"Node.js {node_ver} 不在兼容范围 v{lo}–v{hi}")
        problems.append("node-version")
        actions.append("安装 Node v22 LTS（推荐通过 nvm/volta 管理）")
    else:
        ok(f"Node.js {node_ver}")


def _check_compose(config: dict[str, Any], problems: list[str], actions: list[str]) -> None:
    section("compose 模板检查")
    compose_file = os.path.join(config["penpot_dir"], "docker-compose.yml")
    if not os.path.isfile(compose_file):
        info(f"未找到 compose 文件: {compose_file}")
        return
    try:
        with open(compose_file) as fh:
            content = fh.read()
    except OSError:
        content = ""
    if not ("enable-mcp" in content and "penpot-mcp" in content):
        warn("compose 缺 penpot-mcp 服务或未启用 enable-mcp")
        problems.append("compose-stale")
        actions.append(
            f"compose 缺 penpot-mcp 容器：删除 {compose_file} 后重新 "
            "`cataforge penpot deploy` 重生成"
        )
        return
    if "--multi-user" in content:
        ok("compose 含 penpot-mcp 容器且 frontend enable-mcp")
        info(
            "penpot-mcp 以 multi-user 启动：插件连接 URL 须带 ?userToken="
            "（PENPOT_MCP_MULTI_USER 开关）"
        )
    elif '["node", "index.js"]' in content:
        ok("compose 含 penpot-mcp 容器（single-user，插件免 userToken）且 frontend enable-mcp")
    else:
        warn(
            "penpot-mcp 缺 single-user command：走镜像默认 multi-user，"
            "插件连接会因缺 userToken 被拒"
        )
        problems.append("mcp-implicit-multi-user")
        actions.append(
            f"删除 {compose_file} 后重新 `cataforge penpot deploy` 重生成"
            "（默认 single-user，插件免 userToken）"
        )


def _check_mcp_log(problems: list[str]) -> None:
    section("MCP 日志检查")
    if not os.path.isfile(MCP_LOG_FILE):
        info(f"未找到 MCP 日志: {MCP_LOG_FILE} (MCP 可能从未启动)")
        return
    tail = _tail_log(MCP_LOG_FILE, lines=80)
    hints = _diagnose_mcp_log("\n".join(tail))
    if hints:
        for line in hints:
            print(f"  {line}")
        problems.append("mcp-startup")
    else:
        ok("MCP 日志未发现已知错误模式")


def _explain_self_hosted_endpoint(config: dict[str, Any]) -> None:
    """Clear up the two recurring self-hosted confusions: wrong ports + plugin.

    The npx ports (4400/4401) are never exposed by the container stack, and a
    healthy handshake still needs a connected browser plugin to read designs.
    """
    port = config["penpot_port"]
    section("插件连接")
    info(
        f"自托管 MCP 入口: http://localhost:{port}/mcp/stream"
        "（4400/4401 是 npx 模式端口，自托管不暴露）"
    )
    info(
        "MCP 工具需浏览器插件 Connected 才能读写设计: "
        f"在 http://localhost:{port} 打开设计 → Plugins → "
        f"粘贴 http://localhost:{port}/plugins/mcp/manifest.json → Connect"
    )


def cmd_doctor(config: dict[str, Any]) -> int:
    """Inspect the active mode's toolchain, MCP wiring, and service ports."""
    print_header("Penpot 服务诊断")
    problems: list[str] = []
    actions: list[str] = []

    compose_file = os.path.join(config["penpot_dir"], "docker-compose.yml")
    if os.path.isfile(compose_file):
        # Self-hosted: MCP is the penpot-mcp container — no host Node needed.
        _check_compose(config, problems, actions)
        _explain_self_hosted_endpoint(config)
    else:
        # remote / mcp-only: MCP runs via host npx.
        _check_node_env(problems, actions)
        _check_mcp_log(problems)

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
