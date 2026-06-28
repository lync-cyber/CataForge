#!/usr/bin/env python3
"""Anti-rot guard: every CLI capability has an invocation surface.

The inverse of ``check_prompt_cli_drift.py``. That guard verifies prompts
only name CLI verbs that exist; this one verifies the CLI commands that
exist are actually reachable from the agentic workflow — a top-level
``cataforge <group>`` that no agent / skill / protocol references is an
orphan capability: built but never invoked by the workflow.

This is the CLI-level counterpart to framework-review B2 (orphan skill:
a skill no AGENT.md.skills / SKILL.md.depends references). It lives here
rather than in framework-review because introspecting the Click tree means
importing ``cataforge.interface``, which the runtime layer (where
framework-review sits) may not do under the import-linter layer contract;
``scripts/`` is outside the package and free to import any layer.

Each top-level command must resolve one of three ways:

  - **referenced** — some prompt asset writes ``cataforge <group>`` (or a
    backticked ``<group> <subcommand>``). It has an agentic surface.
  - **hook-wired** — invoked from ``hooks/hooks.yaml``. A legitimate
    automation surface, just not an agentic one.
  - **exempt** — listed in EXEMPT with a reason: infrastructure / operator
    / maintainer tooling invoked by humans, deploy, or CI.

A command in none of these fails the guard: wire a surface, or add it to
EXEMPT with a one-line reason. Stale EXEMPT entries (command gone) and
exemptions that gained a real *agentic* surface also fail so the registry
stays honest; a mere hook surface does not invalidate an exemption, since
exemptions cover broader human / bootstrap reasons than the hook alone.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

for _stream_name in ("stdout", "stderr"):
    _stream = getattr(sys, _stream_name)
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parents[2]
# Resolve cataforge from the source tree so introspection works without a
# pip install — matching the sibling check_prompt_cli_drift.py (the CLI import
# in cli_commands() is function-local, hence no module-top E402).
sys.path.insert(0, str(REPO_ROOT / "src"))

SCAN_GLOBS: list[tuple[Path, str]] = [
    (REPO_ROOT / ".cataforge" / "agents", "**/AGENT.md"),
    (REPO_ROOT / ".cataforge" / "agents", "**/*PROTOCOLS*.md"),
    (REPO_ROOT / ".cataforge" / "skills", "**/*.md"),
    (REPO_ROOT / ".cataforge" / "rules", "**/*.md"),
]

# Top-level CLI commands intentionally NOT part of the agentic workflow —
# infrastructure / operator / maintainer tooling invoked by humans, deploy,
# hooks, or CI rather than by an agent or skill. Each needs a one-line reason.
# A new top-level command in neither this map nor the prompt assets fails the
# guard: classify it (wire a prompt surface, or justify the exemption here).
EXEMPT: dict[str, str] = {
    "git": "git policy/prune/sync — bootstrap + SessionStart hook + maintainer, not agentic",
    "hook": "hook lifecycle (list/test) — deploy/CI wiring + debugging, not the agentic loop",
    "mcp": "MCP server lifecycle (health/list/register/start/stop) — operator command",
    "override": "asset-override eject/list — maintainer tooling",
    "plugin": "plugin install/list/remove — operator command",
    "sync-main": "dogfood main-sync — maintainer/CI command",
}


def cli_commands() -> dict[str, tuple[str, ...]]:
    """Introspect ``{top-level command: (subcommand, ...)}`` from the Click tree."""
    from cataforge.interface.cli.main import _register_commands, cli

    _register_commands()
    out: dict[str, tuple[str, ...]] = {}
    for name, cmd in cli.commands.items():
        out[name] = tuple(getattr(cmd, "commands", {}).keys())
    return out


def iter_files() -> list[Path]:
    files: list[Path] = []
    seen: set[Path] = set()
    for root, pattern in SCAN_GLOBS:
        if not root.exists():
            continue
        for p in root.glob(pattern):
            if p.is_file() and p not in seen:
                seen.add(p)
                files.append(p)
    return files


def referenced_commands(commands: dict[str, tuple[str, ...]], texts: list[str]) -> set[str]:
    """Commands written as ``cataforge <name>`` or backticked ``<name> <sub>``."""
    canonical = {name: re.compile(rf"\bcataforge\s+{re.escape(name)}\b") for name in commands}
    backtick = {
        name: [re.compile(rf"`{re.escape(name)}\s+{re.escape(sub)}\b") for sub in subs]
        for name, subs in commands.items()
    }
    found: set[str] = set()
    for text in texts:
        for name in commands:
            if name in found:
                continue
            if canonical[name].search(text) or any(p.search(text) for p in backtick[name]):
                found.add(name)
    return found


def main() -> int:
    try:
        commands = cli_commands()
    except Exception as exc:  # pragma: no cover - import/registration failure
        print(f"orphan-cli: cannot introspect CLI commands: {exc}", file=sys.stderr)
        return 2

    texts: list[str] = []
    for path in iter_files():
        try:
            texts.append(path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, OSError):
            continue

    referenced = referenced_commands(commands, texts)

    hooks_yaml = REPO_ROOT / ".cataforge" / "hooks" / "hooks.yaml"
    hook_referenced: set[str] = set()
    if hooks_yaml.is_file():
        try:
            hook_referenced = referenced_commands(
                commands, [hooks_yaml.read_text(encoding="utf-8")]
            )
        except (UnicodeDecodeError, OSError):
            hook_referenced = set()

    has_surface = referenced | hook_referenced
    orphans = sorted(c for c in commands if c not in has_surface and c not in EXEMPT)
    # Only an *agentic* surface invalidates an exemption — a hook surface
    # does not, since exemptions cover broader human / bootstrap reasons.
    redundant = sorted(c for c in EXEMPT if c in commands and c in referenced)
    stale = sorted(c for c in EXEMPT if c not in commands)

    fails: list[str] = []
    for c in orphans:
        fails.append(
            f"`cataforge {c}` is an orphan capability — no agent/skill/protocol "
            f"references it and it is not in EXEMPT"
        )
    for c in redundant:
        fails.append(
            f"`{c}` is in EXEMPT but is now referenced by a prompt asset — "
            f"remove it from EXEMPT (it has a real surface)"
        )
    for c in stale:
        fails.append(f"`{c}` is in EXEMPT but no longer a CLI command — remove it from EXEMPT")

    if fails:
        print("Anti-rot: orphan CLI capabilities", file=sys.stderr)
        for f in fails:
            print(f"  {f}", file=sys.stderr)
        print(
            "\nFix: give the command an agentic surface (reference "
            "`cataforge <command>` in an AGENT.md / SKILL.md / protocol, or add a "
            "discovery SKILL.md), or add it to EXEMPT in "
            "scripts/checks/check_orphan_cli_capabilities.py with a one-line reason.",
            file=sys.stderr,
        )
        return 1

    # Disjoint buckets so the counts sum to len(commands): a command exempt
    # for broader reasons is reported as exempt even when also hook-wired.
    hook_only = sorted(c for c in hook_referenced if c not in referenced and c not in EXEMPT)
    print(
        f"OK: {len(commands)} CLI commands, "
        f"{len(referenced)} referenced + {len(hook_only)} hook-wired "
        f"+ {len(EXEMPT)} exempt, no orphans"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
