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
    cataforge event log ...
    cataforge penpot [deploy|mcp-only|start|stop|status|ensure]

Exit codes (see docs/reference/cli.md §退出码):
    0   success
    1   generic failure (validation, missing prereq, business logic)
    2   Click usage error (unknown option, missing required arg, …)
    70  feature not yet implemented (stub subcommands)
"""

from __future__ import annotations

import logging
from pathlib import Path

import click

from cataforge import __version__
from cataforge.utils.common import ensure_utf8_stdio

# Reconfigure stdout/stderr to UTF-8 before any command runs, so users never need
# to prefix invocations with `PYTHONUTF8=1` (matters on Windows cp936 terminals
# where output like `✔ ✖ →` would otherwise raise UnicodeEncodeError).
ensure_utf8_stdio()


# Keys used on ``ctx.obj`` (a plain dict) so subcommands can read the
# globally-scoped flags without re-parsing argv.
CTX_VERBOSE = "verbose"
CTX_QUIET = "quiet"
CTX_PROJECT_DIR = "project_dir"


@click.group(
    help=(
        "CataForge — AI Programming: Agent + Skill Workflow Framework.\n"
        "\n"
        "\b\n"
        "GETTING STARTED (0→1):\n"
        "  cataforge bootstrap --platform claude-code   # one-shot: setup+deploy+doctor\n"
        "  cataforge bootstrap --dry-run                # preview what bootstrap would do\n"
        "\n"
        "\b\n"
        "EVERYDAY COMMANDS:\n"
        "  bootstrap    One-shot setup → upgrade → deploy → doctor (idempotent).\n"
        "  setup        Initialise .cataforge/; pick target platform.\n"
        "  deploy       Emit IDE-visible artefacts (CLAUDE.md, .claude/…).\n"
        "  upgrade      Refresh scaffold after `pip install -U cataforge`.\n"
        "  doctor       Diagnose environment + scaffold integrity.\n"
        "\n"
        "\b\n"
        "FRAMEWORK OBJECTS:\n"
        "  agent        List / validate agents.\n"
        "  skill        List / run skills.\n"
        "  hook         List / test pre/post tool hooks.\n"
        "  mcp          Manage MCP servers (list, register, start, stop).\n"
        "  plugin       Install / remove plugins.\n"
        "\n"
        "\b\n"
        "LOGS & INTEGRATIONS:\n"
        "  docs         Document section loader + chapter indexer.\n"
        "  event        Append records to docs/EVENT-LOG.jsonl.\n"
        "  correction   Query the on-correction learning log.\n"
        "  penpot       Penpot design-tool Docker + MCP integration.\n"
        "\n"
        "Run `cataforge COMMAND --help` for command-specific options."
    ),
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.version_option(__version__, prog_name="cataforge")
@click.option(
    "-v", "--verbose",
    is_flag=True,
    help="Enable debug-level logging for cataforge.* loggers.",
)
@click.option(
    "-q", "--quiet",
    is_flag=True,
    help="Suppress non-error output (logging level = WARNING).",
)
@click.option(
    "--project-dir",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    default=None,
    help="Override project root discovery (default: walk up for .cataforge/).",
)
@click.pass_context
def cli(
    ctx: click.Context,
    verbose: bool,
    quiet: bool,
    project_dir: Path | None,
) -> None:
    """CataForge — AI Programming: Agent + Skill Workflow Framework."""
    if verbose and quiet:
        raise click.UsageError("--verbose and --quiet are mutually exclusive.")

    # Tune only the ``cataforge.*`` logger level; rely on Python's
    # ``logging.lastResort`` (stderr, WARNING+) to actually emit — we
    # deliberately do NOT install an explicit StreamHandler so that
    # repeated invocations under CliRunner (which swaps sys.stderr between
    # calls) can't be left holding a stale, closed stream reference.
    root_logger = logging.getLogger("cataforge")
    if verbose:
        root_logger.setLevel(logging.DEBUG)
    elif quiet:
        root_logger.setLevel(logging.WARNING)
    # default: leave level untouched so host apps' logging.basicConfig wins

    # Expose to subcommands via ctx.obj (plain dict — no custom class needed).
    ctx.ensure_object(dict)
    ctx.obj[CTX_VERBOSE] = verbose
    ctx.obj[CTX_QUIET] = quiet
    ctx.obj[CTX_PROJECT_DIR] = project_dir.resolve() if project_dir else None


def _register_commands() -> None:
    """Import all command modules so they register with the CLI group."""
    from cataforge.cli import (  # noqa: F401
        agent_cmd,
        bootstrap_cmd,
        correction_cmd,
        deploy_cmd,
        docs_cmd,
        doctor_cmd,
        event_cmd,
        hook_cmd,
        mcp_cmd,
        penpot_cmd,
        plugin_cmd,
        setup_cmd,
        skill_cmd,
        upgrade_cmd,
    )


_register_commands()
