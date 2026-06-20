"""CataForge Penpot integration — Docker Compose deployment + MCP server.

Invoked via ``cataforge penpot [init|deploy|remote|mcp-only|start|stop|status|doctor|ensure]``.

Command orchestration lives in ``commands`` and ``doctor``; the per-concern
implementation is split into ``docker`` (compose stack), ``mcp_process``
(npx MCP lifecycle) and ``client`` (Claude registration).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from cataforge.adapter.integrations.penpot import mcp_process  # noqa: F401
from cataforge.adapter.integrations.penpot._constants import (
    DEFAULT_MCP_PACKAGE_VERSION,
    DEFAULT_MCP_PORT,
    DEFAULT_PENPOT_PORT,
    DEFAULT_PENPOT_VERSION,
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
from cataforge.adapter.integrations.penpot.commands import (
    MODE_LOCAL,
    MODE_MCP_ONLY,
    MODE_REMOTE,
    PENPOT_SAAS_URL,
    _print_status_table,
    _prompt_mode,
    _status_rows,
    cmd_deploy,
    cmd_ensure,
    cmd_init,
    cmd_mcp_only,
    cmd_remote,
    cmd_start,
    cmd_status,
    cmd_stop,
    print_header,
    print_remote_onboarding,
)
from cataforge.adapter.integrations.penpot.config import get_config
from cataforge.adapter.integrations.penpot.docker import (
    _extract_secret_key,
    _generate_compose_file,
    _is_penpot_container_running,
    _is_penpot_running,
    _node_major,
    deploy_penpot,
    preflight_check,
)
from cataforge.adapter.integrations.penpot.doctor import cmd_doctor
from cataforge.adapter.integrations.penpot.mcp_process import (
    _diagnose_mcp_log,
    _is_mcp_running,
    _mcp_npx_env,
    _read_mcp_pid,
    _remove_mcp_pid,
    _report_mcp_failure,
    _tail_log,
    _write_mcp_pid,
    start_mcp,
    stop_mcp,
)
from cataforge.utils.common import ensure_utf8
from cataforge.utils.common import load_dotenv as load_dotenv
from cataforge.utils.process import pid_alive

__all__ = [
    # constants
    "DEFAULT_MCP_PACKAGE_VERSION",
    "DEFAULT_MCP_PORT",
    "DEFAULT_PENPOT_PORT",
    "DEFAULT_PENPOT_VERSION",
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
    # mcp_process (submodule exposed for monkeypatching in tests)
    "mcp_process",
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
    "_print_status_table",
    "_prompt_mode",
    "_status_rows",
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


HANDLERS: dict[str, Callable[[dict[str, Any]], int]] = {
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
