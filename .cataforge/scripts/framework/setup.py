"""Framework setup helper — called by the orchestrator during Bootstrap.

This script is referenced from ``.cataforge/agents/orchestrator/ORCHESTRATOR-PROTOCOLS.md``
and from the ``/bootstrap`` slash command.  It provides three subcommands:

- ``--emit-env-block``: detect the project's package ecosystem (uv / pnpm /
  cargo / ...) and print a Markdown block that the orchestrator injects into
  the §执行环境 section of ``CLAUDE.md``.  Exit code 2 when nothing is
  detected so the orchestrator can fall back to asking the user.

- ``--apply-permissions``: read the same detection result and narrow the
  Bash allowlist in ``.claude/settings.json`` (or the platform equivalent) to
  the minimum commands needed for this stack, per least-privilege.

- ``--platform <id>``: a thin wrapper around ``cataforge setup --platform``
  kept here so the protocol documentation stays stable across CLI changes.

The module name ``setup.py`` and the flag names are load-bearing: they are
referenced by ``framework.json`` migration check ``mc-0.7.0-setup-emit-env``
(path + patterns ``--emit-env-block`` + ``build_env_block``).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


# ----------------------------------------------------------------------------
# Stack detection
# ----------------------------------------------------------------------------


def detect_stack(root: Path) -> dict[str, Any] | None:
    """Best-effort detection of the project's primary toolchain.

    Returns a dict with ``stack``, ``package_manager``, ``install_cmd``,
    ``test_cmd``, ``lint_cmd``, plus ``bash_allow`` (a list of prefix strings
    safe to whitelist in the hook layer).  Returns ``None`` when nothing is
    recognized.  Detection stops at the first match in this priority order.
    """
    # Python — prefer uv when uv.lock is present
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        is_uv = (root / "uv.lock").is_file()
        pm = "uv" if is_uv else "pip"
        install = "uv sync" if is_uv else "pip install -e ."
        return {
            "stack": "python",
            "package_manager": pm,
            "install_cmd": install,
            "test_cmd": "uv run pytest" if is_uv else "pytest",
            "lint_cmd": "uv run ruff check" if is_uv else "ruff check",
            "bash_allow": _python_bash_allow(is_uv),
        }

    # Node — order: pnpm > yarn > npm, inferred from lockfile
    pkg = root / "package.json"
    if pkg.is_file():
        if (root / "pnpm-lock.yaml").is_file():
            pm, run = "pnpm", "pnpm"
        elif (root / "yarn.lock").is_file():
            pm, run = "yarn", "yarn"
        else:
            pm, run = "npm", "npm run"
        return {
            "stack": "node",
            "package_manager": pm,
            "install_cmd": f"{pm} install",
            "test_cmd": f"{run} test",
            "lint_cmd": f"{run} lint",
            "bash_allow": _node_bash_allow(pm),
        }

    # Rust
    if (root / "Cargo.toml").is_file():
        return {
            "stack": "rust",
            "package_manager": "cargo",
            "install_cmd": "cargo build",
            "test_cmd": "cargo test",
            "lint_cmd": "cargo clippy",
            "bash_allow": ["cargo "],
        }

    # Go
    if (root / "go.mod").is_file():
        return {
            "stack": "go",
            "package_manager": "go",
            "install_cmd": "go mod download",
            "test_cmd": "go test ./...",
            "lint_cmd": "go vet ./...",
            "bash_allow": ["go "],
        }

    return None


def _python_bash_allow(is_uv: bool) -> list[str]:
    base = ["python ", "pytest", "ruff "]
    if is_uv:
        base.insert(0, "uv ")
    else:
        base.insert(0, "pip ")
    return base


def _node_bash_allow(pm: str) -> list[str]:
    return [f"{pm} ", "node ", "npx "]


# ----------------------------------------------------------------------------
# --emit-env-block
# ----------------------------------------------------------------------------


def build_env_block(stack: dict[str, Any]) -> str:
    """Render a Markdown block for CLAUDE.md §执行环境.

    Kept small and declarative — this text is loaded as a project instruction
    on every session, so every line spends context budget.
    """
    return (
        f"- 技术栈: {stack['stack']}\n"
        f"- 包管理器: {stack['package_manager']}\n"
        f"- 安装命令: `{stack['install_cmd']}`\n"
        f"- 测试命令: `{stack['test_cmd']}`\n"
        f"- Lint 命令: `{stack['lint_cmd']}`\n"
    )


def cmd_emit_env_block(root: Path) -> int:
    stack = detect_stack(root)
    if stack is None:
        print(
            "- 无自动检测到的标准包管理器（请根据实际技术栈手动填写）",
            file=sys.stdout,
        )
        return 2
    print(build_env_block(stack), end="")
    return 0


# ----------------------------------------------------------------------------
# --apply-permissions
# ----------------------------------------------------------------------------


def cmd_apply_permissions(root: Path) -> int:
    stack = detect_stack(root)
    if stack is None:
        print("no stack detected — leaving permissions unchanged", file=sys.stderr)
        return 2

    allow_prefixes: list[str] = list(stack["bash_allow"])
    # Always keep these generic utility prefixes — they're needed regardless
    # of stack for orchestrator Bootstrap itself.
    allow_prefixes.extend(["git ", "ls ", "cat ", "echo "])

    # Claude Code: .claude/settings.json → permissions.allow
    settings = root / ".claude" / "settings.json"
    if settings.is_file():
        data = json.loads(settings.read_text(encoding="utf-8"))
        perms = data.setdefault("permissions", {})
        perms["allow"] = [f"Bash({p}*)" for p in allow_prefixes]
        settings.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"updated {settings} — {len(allow_prefixes)} allow prefixes")
        return 0

    # Cursor: .cursor/hooks.json (permissions may live elsewhere; stub)
    cursor_settings = root / ".cursor" / "hooks.json"
    if cursor_settings.is_file():
        print(
            "Cursor permissions narrowing not implemented yet — "
            f"detected stack: {stack['stack']}",
            file=sys.stderr,
        )
        return 0

    print("no platform settings file found — nothing to update", file=sys.stderr)
    return 1


# ----------------------------------------------------------------------------
# --platform  (thin wrapper around the CLI)
# ----------------------------------------------------------------------------


def cmd_platform(platform_id: str) -> int:
    """Delegate to ``cataforge setup --platform <id>`` so there's a single
    code path for platform switching.  Kept here purely so orchestrator
    documentation can reference a stable script path.
    """
    try:
        from cataforge.cli.main import cli
    except ImportError:
        print(
            "cataforge package not importable — please install it "
            "(uv tool install cataforge) and re-run.",
            file=sys.stderr,
        )
        return 1
    # Invoke click command group programmatically
    return int(
        cli.main(
            args=["setup", "--platform", platform_id],
            standalone_mode=False,
        )
        or 0
    )


# ----------------------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--emit-env-block",
        action="store_true",
        help="Print the §执行环境 Markdown block for CLAUDE.md.",
    )
    group.add_argument(
        "--apply-permissions",
        action="store_true",
        help="Narrow the Bash allowlist in the platform settings file.",
    )
    group.add_argument(
        "--platform",
        metavar="ID",
        help="Set runtime.platform and redeploy (delegates to cataforge CLI).",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Project root (defaults to cwd, walking up to find .cataforge/).",
    )
    args = parser.parse_args(argv)

    root = args.root or _find_project_root()

    if args.emit_env_block:
        return cmd_emit_env_block(root)
    if args.apply_permissions:
        return cmd_apply_permissions(root)
    if args.platform:
        return cmd_platform(args.platform)
    return 2


def _find_project_root(start: Path | None = None) -> Path:
    """Walk up to find the nearest ``.cataforge/`` dir; fall back to cwd."""
    d = (start or Path.cwd()).resolve()
    while True:
        if (d / ".cataforge").is_dir():
            return d
        parent = d.parent
        if parent == d:
            return Path.cwd().resolve()
        d = parent


if __name__ == "__main__":
    raise SystemExit(main())
