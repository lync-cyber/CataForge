"""Local network probes and .env loading for the Penpot docker/MCP stack."""

from __future__ import annotations

import os
import socket
from pathlib import Path

from cataforge.utils.console import get_console


def is_port_listening(port: int, host: str = "127.0.0.1") -> bool:
    """Return True if something is listening on *host:port*."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            s.connect((host, port))
            return True
    except (ConnectionRefusedError, TimeoutError, OSError):
        return False


def check_port_available(port: int, host: str = "127.0.0.1") -> bool:
    """Return True if *port* is free (nothing listening)."""
    return not is_port_listening(port, host)


def find_available_port(start_port: int, label: str = "") -> int:
    """Return *start_port* if free, otherwise try the next 20 ports."""
    for offset in range(20):
        port = start_port + offset
        if check_port_available(port):
            if offset > 0 and label:
                get_console().info(f"{label} 端口 {start_port} 被占用，改用 {port}")
            return port
    return start_port


def load_dotenv(path: str | Path | None = None, *, set_env: bool = False) -> dict[str, str]:
    """Load a .env file into a dict. Optionally set into os.environ."""
    cwd = Path.cwd()
    path = cwd / ".env" if path is None else Path(path).resolve()

    try:
        if not path.is_relative_to(cwd):
            raise ValueError(f"load_dotenv: path is outside the working directory: {path}")
    except AttributeError:
        # Python < 3.9 fallback
        try:
            path.relative_to(cwd)
        except ValueError:
            raise ValueError(
                f"load_dotenv: path is outside the working directory: {path}"
            ) from None

    result: dict[str, str] = {}
    if not path.is_file():
        return result

    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip("\"'")
        result[key] = val
        if set_env:
            os.environ.setdefault(key, val)

    return result
