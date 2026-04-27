#!/usr/bin/env python3
"""Generate CLI reference markdown from Click definitions.

Reads the live `cataforge` Click app, dumps each command's `--help` text into
a markdown structure that can be diffed against `docs/reference/cli.md`. This
is a starting point for replacing the hand-written reference; for now it acts
as a verification tool — run it locally and inspect the diff before editing
cli.md by hand.

Usage:
    python scripts/gen_cli_reference.py                  # print to stdout
    python scripts/gen_cli_reference.py --out CLI.md     # write to file
    python scripts/gen_cli_reference.py --diff           # diff against docs/reference/cli.md

Exit:
    0  generated successfully
    1  click app failed to import
    2  --diff requested and there are differences
"""

from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path

import click

REPO_ROOT = Path(__file__).resolve().parent.parent
DOC_PATH = REPO_ROOT / "docs" / "reference" / "cli.md"


def load_cli() -> click.Group:
    sys.path.insert(0, str(REPO_ROOT / "src"))
    from cataforge.cli.main import cli  # type: ignore[import-not-found]

    if not isinstance(cli, click.Group):
        raise TypeError(f"Expected click.Group at cataforge.cli.main:cli, got {type(cli).__name__}")
    return cli


def render_command(name: str, cmd: click.Command, ctx: click.Context, level: int = 2) -> str:
    """Render one command's help block as markdown."""
    out: list[str] = []
    header = "#" * level
    out.append(f"{header} {name}")
    out.append("")
    out.append("```text")
    out.append(cmd.get_help(ctx).rstrip())
    out.append("```")
    out.append("")
    return "\n".join(out)


def render(cli: click.Group) -> str:
    out: list[str] = ["# CLI Reference (auto-generated)", ""]
    out.append("> Generated from Click definitions by `scripts/gen_cli_reference.py`. ")
    out.append("> Do not edit by hand — re-run the generator after CLI changes.")
    out.append("")

    ctx = click.Context(cli, info_name="cataforge")
    for name in sorted(cli.commands):
        cmd = cli.commands[name]
        sub_ctx = click.Context(cmd, info_name=name, parent=ctx)
        out.append(render_command(name, cmd, sub_ctx, level=2))
        if isinstance(cmd, click.Group):
            for sub_name in sorted(cmd.commands):
                sub_cmd = cmd.commands[sub_name]
                sub_sub_ctx = click.Context(sub_cmd, info_name=sub_name, parent=sub_ctx)
                out.append(render_command(f"{name} {sub_name}", sub_cmd, sub_sub_ctx, level=3))

    return "\n".join(out).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, help="write generated markdown to this path")
    parser.add_argument("--diff", action="store_true", help="diff against docs/reference/cli.md")
    args = parser.parse_args()

    try:
        cli = load_cli()
    except Exception as exc:
        print(f"Failed to import CLI: {exc}", file=sys.stderr)
        return 1

    text = render(cli)

    if args.diff:
        if not DOC_PATH.exists():
            print(f"Missing reference: {DOC_PATH}", file=sys.stderr)
            return 2
        existing = DOC_PATH.read_text(encoding="utf-8")
        diff = list(
            difflib.unified_diff(
                existing.splitlines(keepends=True),
                text.splitlines(keepends=True),
                fromfile=str(DOC_PATH.relative_to(REPO_ROOT)),
                tofile="(generated)",
            )
        )
        if not diff:
            print("OK: cli.md matches generated output")
            return 0
        sys.stdout.writelines(diff)
        print(f"\n{len(diff)} diff lines — review and update cli.md if behavior changed.", file=sys.stderr)
        return 2

    if args.out:
        args.out.write_text(text, encoding="utf-8")
        print(f"Wrote {args.out}")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
