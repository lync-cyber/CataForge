"""Penpot integration — command handlers."""

from __future__ import annotations

import os
import time
from typing import Any

from cataforge.adapter.integrations.penpot.client import register_claude_mcp
from cataforge.adapter.integrations.penpot.docker import (
    _is_penpot_running,
    deploy_penpot,
    preflight_check,
)
from cataforge.adapter.integrations.penpot.mcp_process import (
    _is_mcp_running,
    start_mcp,
    stop_mcp,
)
from cataforge.utils.common import (
    BOLD,
    CYAN,
    DIM,
    GREEN,
    NC,
    RED,
    fail,
    has_command,
    info,
    is_port_listening,
    section,
    warn,
)
from cataforge.utils.docker_util import docker_compose_cmd, ensure_docker_running
from cataforge.utils.run_subprocess import run as run_proc

PENPOT_SAAS_URL = "https://design.penpot.app"

MODE_REMOTE = "remote"
MODE_LOCAL = "local"
MODE_MCP_ONLY = "mcp-only"

_MODE_KEY_TO_NAME = {"1": MODE_REMOTE, "2": MODE_LOCAL, "3": MODE_MCP_ONLY}
_MODE_NAME_TO_KEY = {v: k for k, v in _MODE_KEY_TO_NAME.items()}


def print_header(title: str, subtitle: str | None = None) -> None:
    """Render a consistent two-line banner above each sub-command's output."""
    bar = "━" * max(len(title) + 4, 50)
    print(f"\n{CYAN}{BOLD}━━ {title} {bar}{NC}")
    if subtitle:
        print(f"  {DIM}{subtitle}{NC}")
    print()


def cmd_deploy(config: dict[str, Any]) -> int:
    print_header(
        "Penpot 完整部署",
        "Docker 自托管 (frontend + backend + exporter + postgres + valkey + mailcatch) + MCP",
    )
    if not preflight_check("all"):
        return 1
    if not deploy_penpot(config):
        fail("Penpot 部署失败")
        return 1
    if not start_mcp(config):
        warn("MCP Server 启动异常")
    register_claude_mcp(config)
    return 0


def cmd_mcp_only(config: dict[str, Any]) -> int:
    print_header("Penpot MCP Server 部署", "只起 MCP — 假定 Penpot 已运行")
    if not preflight_check("mcp"):
        return 1
    penpot_base = os.environ.get("PENPOT_BASE_URL", "")
    is_remote = penpot_base and not any(h in penpot_base for h in ("localhost", "127.0.0.1"))
    if is_remote:
        info(f"将连接到远程 Penpot 实例: {penpot_base}")
    elif not _is_penpot_running(config):
        warn(f"Penpot 未在端口 {config['penpot_port']} 运行")
    if not start_mcp(config):
        return 1
    register_claude_mcp(config)
    return 0


def print_remote_onboarding(config: dict[str, Any]) -> None:
    """Walk the user through loading the MCP plugin into design.penpot.app.

    The MCP server itself talks to Penpot via a WebSocket-connected browser
    plugin (not the REST API), so the SaaS flow requires the user to load the
    plugin manifest into the Penpot UI exactly once per browser session.
    """
    plugin_manifest = f"http://localhost:{config['plugin_port']}/manifest.json"
    mcp_endpoint = f"http://localhost:{config['mcp_port']}/mcp"
    section("浏览器侧设置（必须完成才能让 LLM 看到设计）")
    steps = [
        f"在浏览器打开 {BOLD}{PENPOT_SAAS_URL}{NC} 并登录",
        "打开任意设计文件 → 点击右上角 Plugins 图标",
        f"在 'Plugin manager' 粘贴: {BOLD}{plugin_manifest}{NC}",
        "点击 Install，再点 Open，最后点 Connect to MCP server",
        f"状态变 Connected 即可在 LLM 端使用 MCP 工具 ({DIM}{mcp_endpoint}{NC})",
    ]
    for n, msg in enumerate(steps, start=1):
        print(f"  {CYAN}{n}.{NC} {msg}")
    print(
        f"\n  {DIM}提示: Chrome 142+ 会弹出 'Private Network Access' 授权框，"
        f"允许即可；Brave 需要对 design.penpot.app 关闭 Shield。{NC}"
    )
    print(f"  {DIM}插件 UI 关闭后 WebSocket 会断开 — 让 Plugin 面板保持打开。{NC}\n")


def cmd_remote(config: dict[str, Any]) -> int:
    """Remote (SaaS) mode: only launch local MCP, point user at design.penpot.app."""
    print_header(
        "Penpot Remote (SaaS) + 本地 MCP",
        f"使用 {PENPOT_SAAS_URL} 作为 Penpot 后端 — 无需 Docker 自托管",
    )
    if not preflight_check("mcp"):
        return 1
    if not start_mcp(config):
        return 1
    register_claude_mcp(config)
    print_remote_onboarding(config)
    return 0


def cmd_start(config: dict[str, Any]) -> int:
    print_header("启动 Penpot 服务")
    if not preflight_check("all"):
        return 1
    compose_file = os.path.join(config["penpot_dir"], "docker-compose.yml")
    if os.path.isfile(compose_file):
        dc_cmd = docker_compose_cmd()
        if dc_cmd and ensure_docker_running():
            run_proc(
                dc_cmd + ["-f", compose_file, "up", "-d"],
                cwd=config["penpot_dir"],
                timeout=120,
                capture_output=False,
            )
    start_mcp(config)
    return 0


def cmd_stop(config: dict[str, Any]) -> int:
    print_header("停止 Penpot 服务")
    section("停止 MCP Server")
    stop_mcp(config)
    compose_file = os.path.join(config["penpot_dir"], "docker-compose.yml")
    if os.path.isfile(compose_file):
        dc_cmd = docker_compose_cmd()
        if dc_cmd:
            section("停止 Penpot (Docker)")
            run_proc(
                dc_cmd + ["-f", compose_file, "down"],
                cwd=config["penpot_dir"],
                timeout=120,
                capture_output=False,
            )
    return 0


def _status_rows(config: dict[str, Any]) -> list[tuple[str, bool, str]]:
    """Probe every Penpot-side service. Returned as (label, up, endpoint)."""
    return [
        (
            "Penpot Frontend",
            _is_penpot_running(config),
            f"http://localhost:{config['penpot_port']}",
        ),
        (
            "MCP Server",
            _is_mcp_running(config),
            f"http://localhost:{config['mcp_port']}/mcp",
        ),
        (
            "Plugin Server",
            is_port_listening(config["plugin_port"]),
            f"http://localhost:{config['plugin_port']}",
        ),
    ]


def _print_status_table(rows: list[tuple[str, bool, str]]) -> None:
    """Pretty-print the service probe results as an aligned three-column table."""
    label_w = max(len(r[0]) for r in rows) + 2
    state_w = 8
    print(f"  {BOLD}{'服务':<{label_w}}{'状态':<{state_w}}端点{NC}")
    print(f"  {DIM}{'─' * (label_w + state_w + 40)}{NC}")
    for label, up, endpoint in rows:
        state = f"{GREEN}✔ Up{NC}    " if up else f"{RED}✖ Down{NC}  "
        print(f"  {label:<{label_w}}{state:<{state_w}}{DIM}{endpoint}{NC}")


def cmd_status(config: dict[str, Any]) -> int:
    print_header("Penpot 服务状态")
    rows = _status_rows(config)
    _print_status_table(rows)
    mcp_up = rows[1][1]
    if not mcp_up:
        print(
            f"\n  下一步: "
            f"{BOLD}cataforge penpot init{NC}（交互向导）或 "
            f"{BOLD}cataforge penpot remote{NC} / "
            f"{BOLD}cataforge penpot deploy{NC}\n"
        )
    else:
        print()
    return 0


def _prompt_mode(default: str = MODE_REMOTE) -> str:
    """Prompt the user to pick a Penpot integration mode."""
    from cataforge.utils.console import ChoiceOption, get_console

    options = [
        ChoiceOption(
            key="1",
            label="Remote",
            icon="☁",
            description="design.penpot.app + 本地 MCP — 最快上手，零 Docker，需 Penpot 账号",
        ),
        ChoiceOption(
            key="2",
            label="Local",
            icon="⚙",
            description="全量自托管 (6 容器 + MCP) — 数据自己管，需 Docker + ~3GB 镜像",
        ),
        ChoiceOption(
            key="3",
            label="MCP only",
            icon="🔌",
            description="只起 MCP，自己接已有 Penpot 实例（自托管或他人共享）",
        ),
    ]
    chosen = get_console().prompt_choice(
        "选择 Penpot 集成模式",
        options,
        default=_MODE_NAME_TO_KEY[default],
    )
    return _MODE_KEY_TO_NAME[chosen]


def cmd_init(config: dict[str, Any]) -> int:
    """Interactive setup wizard — picks Remote / Local / MCP-only and dispatches."""
    print_header(
        "Penpot 集成向导",
        "为新用户挑选最合适的部署模式",
    )
    mode = _prompt_mode()
    print()
    if mode == MODE_REMOTE:
        return cmd_remote(config)
    if mode == MODE_LOCAL:
        return cmd_deploy(config)
    return cmd_mcp_only(config)


def cmd_ensure(config: dict[str, Any]) -> int:
    if _is_mcp_running(config):
        print(f"Penpot MCP already running on port {config['mcp_port']}")
        return 0
    compose_file = os.path.join(config["penpot_dir"], "docker-compose.yml")
    if os.path.isfile(compose_file):
        if has_command("docker") and not ensure_docker_running():
            fail("Docker daemon 无法启动")
            return 1
        dc_cmd = docker_compose_cmd()
        if dc_cmd and not _is_penpot_running(config):
            run_proc(
                dc_cmd + ["-f", compose_file, "up", "-d"],
                cwd=config["penpot_dir"],
                timeout=120,
            )
            for _ in range(30):
                if _is_penpot_running(config):
                    break
                time.sleep(1)
    if start_mcp(config):
        return 0
    fail("Penpot MCP not installed. Run: cataforge penpot deploy")
    return 1
