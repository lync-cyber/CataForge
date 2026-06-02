"""CataForge Penpot integration — Docker Compose deployment + MCP server.

Invoked via ``cataforge penpot [init|deploy|remote|mcp-only|start|stop|status|doctor|ensure]``.

Command orchestration lives here; the per-concern implementation is split
into ``docker`` (compose stack), ``mcp_process`` (npx MCP lifecycle) and
``client`` (Claude registration). Leaf functions are imported by name so the
orchestration's bare-name calls resolve through this package namespace.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from typing import Any

from cataforge.adapter.integrations.penpot._constants import (
    DEFAULT_MCP_PACKAGE_VERSION,
    DEFAULT_MCP_PORT,
    DEFAULT_PENPOT_PORT,
    DEFAULT_PLUGIN_PORT,
    DOCKER_COMPOSE_TEMPLATE,
    DOCKER_REGISTRY_MIRRORS,
    HEALTH_TIMEOUT,
    MCP_HEALTH_TIMEOUT,
    MCP_LOG_FILE,
    MCP_PID_FILE,
    PLATFORM,
    SUPPORTED_NODE_MAJORS,
)
from cataforge.adapter.integrations.penpot.client import _run_claude_mcp, register_claude_mcp
from cataforge.adapter.integrations.penpot.docker import (
    _extract_secret_key,
    _generate_compose_file,
    _is_penpot_container_running,
    _is_penpot_running,
    _node_major,
    deploy_penpot,
    preflight_check,
)
from cataforge.adapter.integrations.penpot.mcp_process import (
    _diagnose_mcp_log,
    _is_mcp_running,
    _mcp_npx_env,
    _read_mcp_pid,
    _remove_mcp_pid,
    _report_mcp_failure,
    _tail_log,
    _write_mcp_pid,
    pid_alive,
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
    ensure_utf8,
    fail,
    get_command_version,
    has_command,
    info,
    is_port_listening,
    load_dotenv,
    ok,
    section,
    warn,
)
from cataforge.utils.docker_util import docker_compose_cmd, ensure_docker_running
from cataforge.utils.run_subprocess import run as run_proc

# Public surface re-exported from the split submodules. Listed so callers and
# the test suite keep importing/patching ``cataforge.adapter.integrations.penpot.<name>``
# and to mark these imports as intentional re-exports.
__all__ = [
    # constants
    "DEFAULT_MCP_PACKAGE_VERSION",
    "DEFAULT_MCP_PORT",
    "DEFAULT_PENPOT_PORT",
    "DEFAULT_PLUGIN_PORT",
    "DOCKER_COMPOSE_TEMPLATE",
    "DOCKER_REGISTRY_MIRRORS",
    "HEALTH_TIMEOUT",
    "MCP_HEALTH_TIMEOUT",
    "MCP_LOG_FILE",
    "MCP_PID_FILE",
    "PLATFORM",
    "SUPPORTED_NODE_MAJORS",
    "PENPOT_SAAS_URL",
    "MODE_REMOTE",
    "MODE_LOCAL",
    "MODE_MCP_ONLY",
    # docker
    "_extract_secret_key",
    "_generate_compose_file",
    "_is_penpot_container_running",
    "_is_penpot_running",
    "_node_major",
    "deploy_penpot",
    "preflight_check",
    # mcp_process
    "_diagnose_mcp_log",
    "_is_mcp_running",
    "_mcp_npx_env",
    "_read_mcp_pid",
    "_remove_mcp_pid",
    "_report_mcp_failure",
    "_tail_log",
    "_write_mcp_pid",
    "pid_alive",
    "start_mcp",
    "stop_mcp",
    # client
    "_run_claude_mcp",
    "register_claude_mcp",
    # orchestration
    "get_config",
    "print_header",
    "print_remote_onboarding",
    "cmd_deploy",
    "cmd_mcp_only",
    "cmd_remote",
    "cmd_start",
    "cmd_stop",
    "cmd_status",
    "cmd_init",
    "cmd_doctor",
    "cmd_ensure",
    "main",
    "HANDLERS",
]

PENPOT_SAAS_URL = "https://design.penpot.app"

MODE_REMOTE = "remote"
MODE_LOCAL = "local"
MODE_MCP_ONLY = "mcp-only"

_MODE_KEY_TO_NAME = {"1": MODE_REMOTE, "2": MODE_LOCAL, "3": MODE_MCP_ONLY}
_MODE_NAME_TO_KEY = {v: k for k, v in _MODE_KEY_TO_NAME.items()}


def _env_int(name: str, default: int) -> int:
    """Read an int env var, falling back to *default* when unset or empty."""
    raw = os.environ.get(name)
    return int(raw) if raw else default


def get_config() -> dict[str, Any]:
    return {
        "penpot_dir": os.environ.get(
            "PENPOT_INSTALL_DIR",
            os.path.join(os.path.expanduser("~"), "penpot-docker"),
        ),
        "penpot_port": _env_int("PENPOT_PORT", DEFAULT_PENPOT_PORT),
        "mcp_port": _env_int("PENPOT_MCP_SERVER_PORT", DEFAULT_MCP_PORT),
        "plugin_port": _env_int("PENPOT_MCP_PLUGIN_PORT", DEFAULT_PLUGIN_PORT),
        "penpot_flags": os.environ.get(
            "PENPOT_FLAGS",
            "enable-login-with-password disable-email-verification "
            "enable-smtp enable-prepl-server disable-secure-session-cookies",
        ),
        "mcp_version": os.environ.get("PENPOT_MCP_VERSION", DEFAULT_MCP_PACKAGE_VERSION),
    }


def print_header(title: str, subtitle: str | None = None) -> None:
    """Render a consistent two-line banner above each sub-command's output."""
    bar = "━" * max(len(title) + 4, 50)
    print(f"\n{CYAN}{BOLD}━━ {title} {bar}{NC}")
    if subtitle:
        print(f"  {DIM}{subtitle}{NC}")
    print()


def cmd_deploy(config: dict) -> int:
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


def cmd_mcp_only(config: dict) -> int:
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


def print_remote_onboarding(config: dict) -> None:
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


def cmd_remote(config: dict) -> int:
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


def cmd_start(config: dict) -> int:
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


def cmd_stop(config: dict) -> int:
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


def _status_rows(config: dict) -> list[tuple[str, bool, str]]:
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


def cmd_status(config: dict) -> int:
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
    from cataforge.interface.cli.ui import ChoiceOption
    from cataforge.interface.cli.ui import ui as _ui

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
    chosen = _ui.prompt_choice(
        "选择 Penpot 集成模式",
        options,
        default=_MODE_NAME_TO_KEY[default],
    )
    return _MODE_KEY_TO_NAME[chosen]


def cmd_init(config: dict) -> int:
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


def cmd_ensure(config: dict) -> int:
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


def main(argv: list[str] | None = None) -> int:
    import argparse

    ensure_utf8()
    load_dotenv(set_env=True)

    parser = argparse.ArgumentParser(description="CataForge Penpot integration")
    parser.add_argument(
        "command",
        nargs="?",
        choices=[
            "init",
            "deploy",
            "mcp-only",
            "remote",
            "start",
            "stop",
            "status",
            "doctor",
        ],
    )
    parser.add_argument("--ensure", action="store_true")
    args = parser.parse_args(argv)
    config = get_config()

    if args.ensure:
        return HANDLERS["ensure"](config)
    if not args.command:
        parser.print_help()
        return 0
    return HANDLERS[args.command](config)


HANDLERS: dict[str, Callable[[dict], int]] = {
    "init": cmd_init,
    "deploy": cmd_deploy,
    "mcp-only": cmd_mcp_only,
    "remote": cmd_remote,
    "start": cmd_start,
    "stop": cmd_stop,
    "status": cmd_status,
    "doctor": cmd_doctor,
    "ensure": cmd_ensure,
}
