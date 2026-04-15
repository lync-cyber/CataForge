"""CataForge CLI — unified entry point.

Usage:
    cataforge setup [--platform cursor] [--with-penpot]
    cataforge deploy [--platform all]
    cataforge upgrade [check|apply|verify]
    cataforge doctor
    cataforge hook [list|test]
    cataforge agent [list|validate]
    cataforge skill [list|run]
    cataforge mcp [list|register|start|stop]
    cataforge plugin [list|install|remove]
    cataforge docs [load|index]
    cataforge penpot [deploy|mcp-only|start|stop|status]
"""

from __future__ import annotations

import click

from cataforge import __version__
from cataforge.utils.common import ensure_utf8_stdio

# Reconfigure stdout/stderr to UTF-8 before any command runs, so users never need
# to prefix invocations with `PYTHONUTF8=1` (matters on Windows cp936 terminals
# where output like `✔ ✖ →` would otherwise raise UnicodeEncodeError).
ensure_utf8_stdio()


@click.group()
@click.version_option(__version__, prog_name="cataforge")
def cli() -> None:
    """CataForge — AI Programming: Agent + Skill Workflow Framework."""


def _register_commands() -> None:
    """Import all command modules so they register with the CLI group."""
    from cataforge.cli import (  # noqa: F401
        agent_cmd,
        deploy_cmd,
        docs_cmd,
        doctor_cmd,
        hook_cmd,
        mcp_cmd,
        penpot_cmd,
        plugin_cmd,
        setup_cmd,
        skill_cmd,
        upgrade_cmd,
    )


_register_commands()
