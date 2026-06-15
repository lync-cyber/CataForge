"""setup.py — path-stable shim forwarding to ``cataforge setup``.

The canonical invocations are::

    cataforge setup --platform <id>     # set runtime.platform and redeploy
    cataforge setup env-block           # §执行环境 block (exit 2 = no stack)
    cataforge setup permissions         # narrow Bash allowlist to the stack

which work from any subdirectory inside a CataForge project (the CLI walks up
to find ``.cataforge/``). Kept as a stable entry point for callers that pass
the flag form below; each flag maps straight onto the CLI subcommand.
"""

from __future__ import annotations

import sys

# Flag form → `cataforge setup` argv tail.
_FLAG_TO_ARGS = {
    "--emit-env-block": ["env-block"],
    "--apply-permissions": ["permissions"],
}


def _translate(argv: list[str]) -> list[str] | None:
    """Map flag-form argv onto a ``setup`` subcommand call, or ``None`` if unknown."""
    project_dir: list[str] = []
    rest = list(argv)
    if "--root" in rest:
        i = rest.index("--root")
        if i + 1 < len(rest):
            project_dir = ["--project-dir", rest[i + 1]]
            del rest[i : i + 2]
    if not rest:
        return None
    if rest[0] in _FLAG_TO_ARGS:
        return [*project_dir, "setup", *_FLAG_TO_ARGS[rest[0]]]
    if rest[0] == "--platform" and len(rest) >= 2:
        return [*project_dir, "setup", "--platform", rest[1]]
    return None


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    cli_args = _translate(args)
    if cli_args is None:
        sys.stderr.write(
            "setup.py: unrecognized arguments. Use the CLI directly:\n"
            "  cataforge setup --platform <id> | env-block | permissions\n"
        )
        return 2
    try:
        from cataforge.interface.cli.main import cli
    except ImportError as e:
        sys.stderr.write(
            f"setup.py: cannot import cataforge ({e.__class__.__name__}: {e}). "
            "Install it (`pip install cataforge`) and re-run.\n"
        )
        return 1
    # Click exits on its own via SystemExit — cede control and re-raise.
    cli(args=cli_args, prog_name="setup.py")
    return 0  # unreachable; cli() always calls sys.exit


if __name__ == "__main__":
    sys.exit(main())
