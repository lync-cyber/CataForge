"""cataforge agent — agent management."""

from __future__ import annotations

import os
import shutil
import sys

import click

from cataforge.core.errors import CataforgeError
from cataforge.interface.cli.guards import require_initialized
from cataforge.interface.cli.helpers import emit_hint, resolve_root
from cataforge.interface.cli.main import cli
from cataforge.utils.run_subprocess import run as run_proc


@cli.group("agent")
def agent_group() -> None:
    """Manage CataForge agents.

    Agents are defined in ``.cataforge/agents/<id>/AGENT.md``. Use
    ``cataforge agent list`` to see what's registered,
    ``cataforge agent validate [id]`` to check a definition, and
    ``cataforge agent run <id> [task...]`` to surface an agent's
    AGENT.md prompt for on-demand invocation.
    """


@agent_group.command("list")
@require_initialized
def agent_list() -> None:
    """List all registered agents (from ``.cataforge/agents/``)."""
    from cataforge.interface.cli.ui import ui
    from cataforge.runtime.agent.manager import AgentManager

    mgr = AgentManager(project_root=resolve_root())
    agents = mgr.list_agents()
    if not agents:
        click.echo("No agents found.")
        emit_hint(
            "  Hint: scaffold with `cataforge setup --force-scaffold`, "
            "or add a new agent directory under .cataforge/agents/<id>/."
        )
        return
    ui.bullets(agents)
    ui.info(f"{len(agents)} agent(s) registered")


@agent_group.command("validate")
@click.argument("agent_id", required=False)
@require_initialized
def agent_validate(agent_id: str | None) -> None:
    """Validate one agent (by id) or all agents if no id is given.

    Checks AGENT.md frontmatter, declared tools, and model field.
    Fails with exit 1 if any issue is found, so it can gate CI.
    """
    from cataforge.interface.cli.ui import ui
    from cataforge.runtime.agent.manager import AgentManager

    mgr = AgentManager(project_root=resolve_root())
    issues = mgr.validate(agent_id)
    if not issues:
        ui.ok("All agents valid.")
        return

    for issue in issues:
        ui.fail(issue)
    raise CataforgeError(f"{len(issues)} agent definition issue(s) found.")


@agent_group.command("run")
@click.argument("agent_id")
@click.argument("task", nargs=-1)
@click.option(
    "--task-type",
    "task_type",
    default="new_creation",
    help=(
        "task_type forwarded to the agent (new_creation | revision | "
        "continuation | retrospective | skill-improvement | apply-learnings | "
        "amendment | on_demand). Default: new_creation."
    ),
)
@click.option(
    "--print-only",
    is_flag=True,
    default=False,
    help=(
        "Skip clipboard copy (when pyperclip / xclip are unavailable, "
        "or in CI). Always set in non-TTY contexts."
    ),
)
@require_initialized
def agent_run(agent_id: str, task: tuple[str, ...], task_type: str, print_only: bool) -> None:
    """Surface AGENT.md + task framing for on-demand invocation.

    This is **not** a remote dispatcher — sub-agent dispatch is the
    runtime IDE's job (Claude Code's Task tool, Cursor's agent mode,
    etc.). What this command does is render the standard prompt
    payload (AGENT.md prose + task_type framing + user task) so the
    user can paste it into the IDE / chat to manually trigger an
    agent that is normally only reached through orchestrator routing
    (e.g. ``reflector`` for ad-hoc retrospectives, ``debugger`` for
    framework script debugging).

    Without this, ad-hoc invocation forces the user to copy-paste the
    AGENT.md by hand and re-derive the framing each time.
    """
    from cataforge.runtime.agent.manager import AgentManager

    mgr = AgentManager(project_root=resolve_root())
    if agent_id not in mgr.list_agents():
        raise CataforgeError(
            f"agent {agent_id!r} not found under .cataforge/agents/. "
            f"Run `cataforge agent list` to see registered ids."
        )

    content = mgr.get_agent_content(agent_id)
    if content is None:
        raise CataforgeError(f"AGENT.md missing for {agent_id!r}.")

    task_text = " ".join(task).strip() if task else ""
    payload = _render_invocation_prompt(agent_id, task_type, task_text, content)

    click.echo(payload)

    if print_only or not sys.stdout.isatty():
        return

    if _try_copy_to_clipboard(payload):
        click.secho(
            "\n(prompt copied to clipboard — paste into your IDE chat to invoke the agent)",
            fg="green",
            err=True,
        )


def _render_invocation_prompt(agent_id: str, task_type: str, task_text: str, agent_md: str) -> str:
    """Compose the on-demand invocation payload.

    Layout:
      1. Banner with agent_id + task_type
      2. The user-provided task (or a placeholder)
      3. The full AGENT.md (so the IDE has the role definition)
    """
    task_block = task_text or "(no task provided — describe what you want this agent to do)"
    return (
        f"# CataForge agent invocation: {agent_id}\n"
        f"task_type: {task_type}\n"
        f"\n"
        f"## Task\n"
        f"{task_block}\n"
        f"\n"
        f"## Role definition (from .cataforge/agents/{agent_id}/AGENT.md)\n"
        f"{agent_md}"
    )


def _try_copy_to_clipboard(text: str) -> bool:
    """Best-effort clipboard copy. Silently no-ops when no backend works."""
    if sys.platform == "win32":
        try:
            proc = run_proc(["clip"], input=text)
            return proc.returncode == 0
        except (FileNotFoundError, OSError):
            return False
    if sys.platform == "darwin":
        try:
            proc = run_proc(["pbcopy"], input=text)
            return proc.returncode == 0
        except (FileNotFoundError, OSError):
            return False
    # Linux / BSD: try xclip then xsel; fail silently if neither is present.
    if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        return False
    for cmd in (["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"]):
        if shutil.which(cmd[0]):
            try:
                proc = run_proc(cmd, input=text)
                if proc.returncode == 0:
                    return True
            except OSError:
                continue
    return False
