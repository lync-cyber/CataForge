"""Penpot Docker Compose stack management."""

from __future__ import annotations

import os
import secrets
import subprocess
import time
from typing import Any

from cataforge.adapter.integrations.penpot._constants import (
    DOCKER_COMPOSE_TEMPLATE,
    DOCKER_REGISTRY_MIRRORS,
    HEALTH_TIMEOUT,
    SUPPORTED_NODE_MAJORS,
)
from cataforge.adapter.integrations.penpot.netenv import find_available_port, is_port_listening
from cataforge.utils.common import (
    DIM,
    NC,
    fail,
    get_command_version,
    has_command,
    info,
    ok,
    section,
    warn,
)
from cataforge.utils.docker_util import (
    docker_compose_cmd,
    ensure_docker_running,
    pull_all_images_from_compose_file,
)
from cataforge.utils.run_subprocess import run as run_proc


def _extract_secret_key(compose_file: str) -> str | None:
    try:
        with open(compose_file) as f:
            for line in f:
                if "PENPOT_SECRET_KEY=" in line:
                    val = line.split("=", 1)[1].strip()
                    if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
                        val = val[1:-1]
                    return val
    except OSError:
        pass
    return None


def _generate_compose_file(config: dict[str, Any], force: bool = False) -> str:
    compose_dir = config["penpot_dir"]
    os.makedirs(compose_dir, exist_ok=True)
    compose_file = os.path.join(compose_dir, "docker-compose.yml")
    if os.path.isfile(compose_file) and not force:
        info(f"docker-compose.yml 已存在: {compose_file}")
        return compose_file
    existing = _extract_secret_key(compose_file) if os.path.isfile(compose_file) else None
    secret_key = existing or secrets.token_hex(32)
    mcp_command = (
        '["node", "index.js", "--multi-user"]'
        if config.get("mcp_multi_user")
        else '["node", "index.js"]'
    )
    content = DOCKER_COMPOSE_TEMPLATE.format(
        penpot_port=config["penpot_port"],
        penpot_version=config["penpot_version"],
        penpot_flags=config["penpot_flags"],
        secret_key=secret_key,
        mcp_command=mcp_command,
    )
    with open(compose_file, "w") as f:
        f.write(content)
    ok(f"{'已重新生成' if force else '已生成'} docker-compose.yml: {compose_file}")
    return compose_file


def _is_penpot_container_running() -> bool:
    try:
        r = run_proc(
            ["docker", "ps", "--filter", "name=penpot", "--format", "{{.Names}}"],
            timeout=10,
        )
        return bool(r.stdout.strip())
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


def _is_penpot_running(config: dict[str, Any]) -> bool:
    return _is_penpot_container_running() and is_port_listening(config["penpot_port"])


def _node_major(version_str: str) -> int | None:
    """Parse the leading integer of a ``node --version`` output (``v22.11.0``)."""
    s = version_str.strip().lstrip("v")
    head = s.split(".", 1)[0]
    try:
        return int(head)
    except ValueError:
        return None


def preflight_check(scope: str = "all") -> bool:
    """Validate the toolchain a given mode needs.

    ``scope="all"`` (self-hosted): the MCP runs as the ``penpot-mcp`` compose
    container, so only Docker / Compose are required — no host Node. ``scope="mcp"``
    (``remote`` / ``mcp-only``): the MCP runs via host ``npx @penpot/mcp``, so
    only Node / npx are required — no Docker.
    """
    section("依赖预检")
    passed = True
    if scope == "all":
        if not has_command("docker"):
            fail("Docker 未安装。请安装: https://docs.docker.com/get-docker/")
            passed = False
        else:
            ok(f"Docker {DIM}({get_command_version(['docker', '--version'])}){NC}")
        dc_cmd = docker_compose_cmd()
        if not dc_cmd:
            fail("Docker Compose 未安装。")
            passed = False
        else:
            ok(f"Docker Compose {DIM}({get_command_version(dc_cmd + ['version'])}){NC}")
    else:
        if not has_command("node"):
            fail("Node.js 未安装。请安装: https://nodejs.org (推荐 v22 LTS)")
            passed = False
        else:
            node_ver = get_command_version(["node", "--version"])
            major = _node_major(node_ver)
            lo, hi = SUPPORTED_NODE_MAJORS[0], SUPPORTED_NODE_MAJORS[-1]
            if major is None or not (lo <= major <= hi):
                warn(
                    f"Node.js {node_ver} 不在 @penpot/mcp 兼容范围 "
                    f"(v{lo}–v{hi})；如启动失败请改用 v22 LTS"
                )
            else:
                ok(f"Node.js {DIM}({node_ver}){NC}")
        if not has_command("npx"):
            fail("npx 未找到")
            passed = False
        else:
            ok("npx")
    if not passed:
        fail("依赖预检未通过")
    return passed


def deploy_penpot(config: dict[str, Any]) -> bool:
    section("部署 Penpot (Docker Compose)")
    if not ensure_docker_running():
        return False
    if _is_penpot_running(config):
        ok("Penpot 已在运行，跳过部署")
        return True
    orig_port = config["penpot_port"]
    config["penpot_port"] = find_available_port(orig_port, "Penpot Frontend")
    dc_cmd = docker_compose_cmd()
    compose_file = _generate_compose_file(config, force=(config["penpot_port"] != orig_port))
    compose_dir = os.path.dirname(compose_file)
    info("拉取 Docker 镜像...")
    if not pull_all_images_from_compose_file(compose_file, DOCKER_REGISTRY_MIRRORS):
        fail("一个或多个 Docker 镜像拉取失败，已中止部署")
        return False
    info("启动 Penpot 服务...")
    up_result = run_proc(
        dc_cmd + ["-f", compose_file, "up", "-d"],
        cwd=compose_dir,
        timeout=120,
        capture_output=False,
    )
    if up_result.returncode != 0:
        fail("Docker Compose 启动失败")
        return False
    info(f"等待 Penpot 就绪 (最多 {HEALTH_TIMEOUT}s)...")
    for _i in range(HEALTH_TIMEOUT):
        if _is_penpot_running(config):
            ok(f"Penpot 就绪 {DIM}-> http://localhost:{config['penpot_port']}{NC}")
            return True
        time.sleep(1)
    warn(f"Penpot 在 {HEALTH_TIMEOUT}s 内未就绪")
    return False
