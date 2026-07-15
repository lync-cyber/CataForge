"""Penpot integration — command handlers."""

from __future__ import annotations

import os
import time
from typing import Any

from cataforge.adapter.integrations.penpot._constants import MCP_HEALTH_TIMEOUT
from cataforge.adapter.integrations.penpot.client import mask_url_secrets, register_claude_mcp
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
from cataforge.utils.console import (
    BOLD,
    CYAN,
    DIM,
    GREEN,
    NC,
    RED,
    fail,
    info,
    ok,
    section,
    warn,
)
from cataforge.utils.docker_util import docker_compose_cmd, ensure_docker_running
from cataforge.utils.process import has_command
from cataforge.utils.run_subprocess import run as run_proc

PENPOT_SAAS_URL = "https://design.penpot.app"

MODE_REMOTE = "remote"
MODE_LOCAL = "local"
MODE_MCP_ONLY = "mcp-only"

_MODE_KEY_TO_NAME = {"1": MODE_REMOTE, "2": MODE_LOCAL, "3": MODE_MCP_ONLY}
_MODE_NAME_TO_KEY = {v: k for k, v in _MODE_KEY_TO_NAME.items()}


def _compose_file(config: dict[str, Any]) -> str:
    return os.path.join(config["penpot_dir"], "docker-compose.yml")


def _container_mcp_url(config: dict[str, Any]) -> str:
    """Self-hosted endpoint: penpot-mcp container reached through frontend nginx."""
    return f"http://localhost:{config['penpot_port']}/mcp/stream"


def _npx_mcp_url(config: dict[str, Any]) -> str:
    """Host npx endpoint used by `remote` / `mcp-only` (no compose stack)."""
    return f"http://localhost:{config['mcp_port']}/mcp"


def _mcp_url(config: dict[str, Any]) -> str:
    """Resolve the MCP endpoint for mode-agnostic callers (status / ensure).

    A generated compose file means self-hosted (container behind the frontend);
    otherwise the host npx server.
    """
    if os.path.isfile(_compose_file(config)):
        return _container_mcp_url(config)
    return _npx_mcp_url(config)


def _wait_for_mcp(config: dict[str, Any], url: str, timeout: int = MCP_HEALTH_TIMEOUT) -> bool:
    for _ in range(timeout):
        if _is_mcp_running(config, url):
            return True
        time.sleep(1)
    return False


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
        "Docker 自托管 (frontend + backend + exporter + mcp + postgres + valkey + mailcatch)",
    )
    if not preflight_check("all"):
        return 1
    if not deploy_penpot(config):
        fail("Penpot 部署失败")
        return 1
    section("等待 MCP 容器就绪")
    url = _container_mcp_url(config)
    if not _wait_for_mcp(config, url):
        warn("penpot-mcp 容器未就绪（可能仍在拉镜像）；稍后 `cataforge penpot status` 复查")
    register_claude_mcp(url)
    print_self_hosted_onboarding(config)
    return 0


def cmd_mcp_only(config: dict[str, Any]) -> int:
    print_header("Penpot MCP Server (npx)", "只起本地 npx MCP — 假定 Penpot 已运行")
    warn(
        "mcp-only（宿主机 npx MCP）已不推荐：依赖 Node/npx 源码构建且需浏览器插件常驻。"
        "优先 cataforge penpot remote（托管）或 cataforge penpot deploy（自托管）。"
    )
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
    register_claude_mcp(_npx_mcp_url(config))
    print_remote_onboarding(config)
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


def print_self_hosted_onboarding(config: dict[str, Any]) -> None:
    """Walk the user through connecting the MCP plugin in the self-hosted UI.

    The penpot-mcp container reaches designs only through a WebSocket-connected
    browser plugin, so even with the whole stack up the user must load the
    plugin manifest into their local Penpot once per browser session — the
    self-hosted frontend serves it at ``/plugins/mcp/manifest.json``.
    """
    base = f"http://localhost:{config['penpot_port']}"
    plugin_manifest = f"{base}/plugins/mcp/manifest.json"
    mcp_endpoint = f"{base}/mcp/stream"
    section("浏览器侧设置（必须完成才能让 LLM 看到设计）")
    steps = [
        f"在浏览器打开 {BOLD}{base}{NC} 并登录自托管 Penpot",
        "打开任意设计文件 → 点击右上角 Plugins 图标",
        f"在 'Plugin manager' 粘贴: {BOLD}{plugin_manifest}{NC}",
        "点击 Install，再点 Open，最后点 Connect to MCP server",
        f"状态变 Connected 即可在 LLM 端使用 MCP 工具 ({DIM}{mcp_endpoint}{NC})",
    ]
    for n, msg in enumerate(steps, start=1):
        print(f"  {CYAN}{n}.{NC} {msg}")
    print(
        f"\n  {DIM}注意: {mcp_endpoint} 握手就绪 ≠ 插件已连 —— "
        f"只有插件面板 Connected 且保持打开，LLM 才能读写设计。{NC}\n"
    )


def cmd_remote(config: dict[str, Any]) -> int:
    """Remote mode: register a hosted Penpot MCP endpoint from PENPOT_MCP_URL.

    No local process, Docker, or browser plugin — the URL points at a
    Penpot-hosted (or self-hosted remote-mode) MCP server authenticating via the
    token carried in the URL. PENPOT_MCP_URL is the single source of truth.
    """
    print_header(
        "Penpot Remote (托管 MCP)",
        "指向 PENPOT_MCP_URL 的托管 endpoint — 零本地进程 / 零 Docker / 零插件",
    )
    url = config.get("mcp_url", "")
    if not url:
        fail(
            "未设置 PENPOT_MCP_URL。在 .env 配置托管 MCP endpoint，例如:\n"
            f"    PENPOT_MCP_URL={PENPOT_SAAS_URL}/mcp/stream?userToken=<MCP_KEY>\n"
            "  (MCP key 在 Penpot 账户设置生成。) 或改用自托管: cataforge penpot deploy"
        )
        return 1
    register_claude_mcp(url)
    ok(f"已注册托管 Penpot MCP endpoint: {mask_url_secrets(url)}")
    return 0


def cmd_start(config: dict[str, Any]) -> int:
    print_header("启动 Penpot 服务")
    if not preflight_check("all"):
        return 1
    compose_file = _compose_file(config)
    if os.path.isfile(compose_file):
        dc_cmd = docker_compose_cmd()
        if dc_cmd and ensure_docker_running():
            run_proc(
                dc_cmd + ["-f", compose_file, "up", "-d"],
                cwd=config["penpot_dir"],
                timeout=120,
                capture_output=False,
            )
    register_claude_mcp(_container_mcp_url(config))
    return 0


def cmd_stop(config: dict[str, Any]) -> int:
    print_header("停止 Penpot 服务")
    # Host npx MCP (remote / mcp-only); no-op when only the container stack runs.
    section("停止 MCP Server")
    stop_mcp(config)
    compose_file = _compose_file(config)
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
    mcp = _mcp_url(config)
    return [
        (
            "Penpot Frontend",
            _is_penpot_running(config),
            f"http://localhost:{config['penpot_port']}",
        ),
        (
            "MCP Server",
            _is_mcp_running(config, mcp),
            mcp,
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
    elif os.path.isfile(_compose_file(config)):
        # Self-hosted handshake being up does not mean the browser plugin is
        # connected — the most common "MCP shows Up but LLM sees no designs".
        print(
            f"\n  {DIM}MCP 握手就绪。若 LLM 看不到设计，多半是浏览器插件未连 —— "
            f"在 http://localhost:{config['penpot_port']} 打开设计并 Connect MCP 插件。{NC}\n"
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
            description="托管 MCP (PENPOT_MCP_URL) — 零本地进程/Docker/插件，需 MCP key",
        ),
        ChoiceOption(
            key="2",
            label="Self-hosted",
            icon="⚙",
            description="全量自托管 (6 容器 + MCP) — 数据自管，需 Docker + 浏览器插件连接",
        ),
        ChoiceOption(
            key="3",
            label="MCP only",
            icon="🔌",
            description="[不推荐] 宿主机 npx MCP，接已有 Penpot 实例（需 Node + 插件）",
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
    url = _mcp_url(config)
    if _is_mcp_running(config, url):
        print(f"Penpot MCP already running ({url})")
        return 0
    compose_file = _compose_file(config)
    if os.path.isfile(compose_file):
        # Self-hosted: `up -d` brings the penpot-mcp container up with the stack.
        if has_command("docker") and not ensure_docker_running():
            fail("Docker daemon 无法启动")
            return 1
        dc_cmd = docker_compose_cmd()
        if dc_cmd:
            run_proc(
                dc_cmd + ["-f", compose_file, "up", "-d"],
                cwd=config["penpot_dir"],
                timeout=120,
            )
            if _wait_for_mcp(config, url):
                return 0
        fail("Penpot MCP 容器未就绪。诊断: cataforge penpot doctor")
        return 1
    # No compose stack → host npx (remote / mcp-only).
    if start_mcp(config):
        return 0
    fail("Penpot MCP not installed. Run: cataforge penpot deploy")
    return 1
