"""Docker / Docker Compose helpers shared by integrations (e.g. Penpot).

Keeps orchestration modules thinner; Penpot-specific compose and ports stay in
``integrations.penpot``.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from typing import Any
from urllib.parse import urlparse

from cataforge.utils.console import fail, info, ok
from cataforge.utils.process import detect_platform, has_command
from cataforge.utils.run_subprocess import run as run_proc

DOCKER_PULL_TIMEOUT = 300
PULL_MAX_RETRIES = 3


def _platform() -> str:
    """Return the current platform string, evaluated on first call."""
    return detect_platform()


def __getattr__(name: str) -> object:
    if name == "PLATFORM":
        return detect_platform()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def ensure_docker_running() -> bool:
    """Ensure the Docker daemon is running. Try to start it if not."""
    try:
        import docker

        docker.from_env(timeout=10).ping()
        return True
    except Exception:
        pass

    try:
        r = run_proc(["docker", "info"], timeout=10)
        if r.returncode == 0:
            return True
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    if _platform() == "windows":
        docker_paths = [
            os.path.join(
                os.environ.get("PROGRAMFILES", ""),
                "Docker",
                "Docker",
                "Docker Desktop.exe",
            ),
        ]
        for p in docker_paths:
            if os.path.isfile(p):
                info("启动 Docker Desktop...")
                flags = 0
                if sys.platform == "win32":
                    flags = subprocess.CREATE_NEW_PROCESS_GROUP
                subprocess.Popen(  # allow-raw-subprocess: fire-and-forget GUI launch
                    [p], creationflags=flags
                )
                break
    elif _platform() == "darwin":
        run_proc(["open", "-a", "Docker"], timeout=10)
    else:
        run_proc(["sudo", "systemctl", "start", "docker"], timeout=30)

    for _ in range(30):
        try:
            r = run_proc(["docker", "info"], timeout=10)
            if r.returncode == 0:
                ok("Docker daemon 已就绪")
                return True
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            pass
        time.sleep(2)

    fail("Docker daemon 启动超时")
    return False


def docker_status() -> dict[str, Any]:
    """Quick Docker status check."""
    try:
        import docker

        client = docker.from_env(timeout=10)
        client.ping()
        info_dict = client.info()
        return dict(info_dict) if isinstance(info_dict, dict) else {}
    except Exception:
        pass
    try:
        r = run_proc(["docker", "info", "--format", "json"], timeout=10)
        if r.returncode == 0:
            data = json.loads(r.stdout)
            if isinstance(data, dict):
                return data
    except (
        FileNotFoundError,
        subprocess.TimeoutExpired,
        OSError,
        json.JSONDecodeError,
    ):
        pass
    return {}


def docker_compose_cmd() -> list[str]:
    """Return ``[\"docker\", \"compose\"]`` or ``[\"docker-compose\"]``, or []."""
    try:
        result = run_proc(["docker", "compose", "version"], timeout=10)
        if result.returncode == 0:
            return ["docker", "compose"]
    except (FileNotFoundError, OSError):
        pass
    if has_command("docker-compose"):
        return ["docker-compose"]
    return []


def rewrite_image_for_mirror(image: str, mirror: str) -> str:
    if not mirror:
        return image
    name, tag = (image.rsplit(":", 1) + ["latest"])[:2]
    if "/" not in name:
        name = f"library/{name}"
    return f"{mirror}/{name}:{tag}"


def is_mirror_reachable(mirror: str, timeout: float = 3.0) -> bool:
    if not mirror:
        return True
    try:
        parsed = urlparse(f"https://{mirror}")
        host = parsed.hostname or mirror
        port = parsed.port or 443
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect((host, port))
            return True
    except (ConnectionRefusedError, TimeoutError, OSError):
        return False


def _pull_image_docker_sdk(
    rewritten: str, canonical: str, mirror: str, *, pull_timeout: int
) -> bool:
    """Pull via docker SDK; when *mirror* is set, tag *canonical* from pulled image."""
    try:
        import docker
    except ImportError:
        return False

    try:
        client = docker.from_env(timeout=pull_timeout)
        pulled = client.images.pull(rewritten)
        if mirror:
            if ":" in canonical:
                c_repo, _, c_tag = canonical.rpartition(":")
            else:
                c_repo, c_tag = canonical, "latest"
            pulled.tag(c_repo, tag=c_tag)
        return True
    except Exception:
        return False


def pull_image_with_mirrors(
    image: str,
    mirrors: list[str],
    *,
    pull_timeout: int = DOCKER_PULL_TIMEOUT,
    max_retries: int = PULL_MAX_RETRIES,
) -> bool:
    """Try ``docker pull`` via mirrors; tag back to *image* when using a mirror."""
    import importlib.util

    from cataforge.utils.console import info, ok, warn

    sdk_available = importlib.util.find_spec("docker") is not None

    for mirror in mirrors:
        source_label = mirror if mirror else "Docker Hub"
        if mirror and not is_mirror_reachable(mirror):
            continue
        rewritten = rewrite_image_for_mirror(image, mirror)
        for attempt in range(1, max_retries + 1):
            info(f"  [{source_label}] 拉取 {rewritten} ({attempt}/{max_retries})...")
            if sdk_available and _pull_image_docker_sdk(
                rewritten, image, mirror, pull_timeout=pull_timeout
            ):
                ok(f"  {image} <- {source_label}")
                return True
            try:
                result = run_proc(
                    ["docker", "pull", rewritten],
                    timeout=pull_timeout,
                )
                if result.returncode == 0:
                    ok(f"  {image} <- {source_label}")
                    if mirror:
                        run_proc(
                            ["docker", "tag", rewritten, image],
                            timeout=30,
                        )
                    return True
            except subprocess.TimeoutExpired:
                warn(f"  [{source_label}] 拉取超时")
            except OSError as e:
                warn(f"  [{source_label}] 拉取异常: {e}")
    return False


def pull_all_images_from_compose_file(
    compose_file: str,
    mirrors: list[str],
    *,
    pull_timeout: int = DOCKER_PULL_TIMEOUT,
) -> bool:
    """Parse ``image:`` lines from a compose file and pull each image."""
    from cataforge.utils.console import info

    images: list[str] = []
    try:
        with open(compose_file) as f:
            for line in f:
                stripped = line.strip()
                if stripped.startswith("image:"):
                    img = stripped.split(":", 1)[1].strip().strip('"').strip("'")
                    if "  #" in img:
                        img = img[: img.index("  #")].rstrip()
                    if img:
                        images.append(img)
    except OSError:
        return False
    if not images:
        return False
    info(f"共需拉取 {len(images)} 个镜像")
    return all(pull_image_with_mirrors(img, mirrors, pull_timeout=pull_timeout) for img in images)
