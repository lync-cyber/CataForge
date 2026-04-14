"""PostToolUse Hook: Run formatters/linters on files modified by Edit or Write.

Matcher: Edit|Write
Skips .cataforge/ framework files to preserve framework formatting.
Always exits 0 — reports issues but never blocks.
"""

import os
import shutil
import subprocess
import sys

from cataforge.hook.base import hook_main, read_hook_input


def run_tool(cmd: list[str], label: str, filepath: str) -> None:
    """Run a formatting/linting tool, report errors to stderr."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0 and result.stderr:
            lines = [
                line
                for line in result.stderr.splitlines()
                if any(kw in line.lower() for kw in ("warning", "error", "err", "warn"))
                or any(c.isdigit() and ":" in line for c in line[:20])
            ]
            if lines:
                print(f"[{label}] Issues in: {filepath}", file=sys.stderr)
                for line in lines[:10]:
                    print(f"  {line}", file=sys.stderr)
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
        pass


def _has_command(name: str) -> bool:
    return shutil.which(name) is not None


@hook_main
def main() -> None:
    data = read_hook_input()

    file_path = (data.get("tool_input") or {}).get("file_path")
    if not file_path:
        file_path = (data.get("tool_input") or {}).get("path")
    if not file_path:
        sys.exit(0)

    file_path = file_path.replace("\\", "/")

    if not os.path.isfile(file_path):
        sys.exit(0)

    ext = os.path.splitext(file_path)[1].lower()

    if ext in (".js", ".ts", ".jsx", ".tsx"):
        if _has_command("npx"):
            run_tool(["npx", "prettier", "--write", file_path], "Prettier", file_path)
            run_tool(
                [
                    "npx", "eslint", "--fix",
                    "--rule", "no-unused-vars: off",
                    "--rule", "@typescript-eslint/no-unused-vars: off",
                    file_path,
                ],
                "ESLint",
                file_path,
            )

    elif ext == ".py":
        if _has_command("ruff"):
            run_tool(["ruff", "format", file_path], "Ruff Format", file_path)
            run_tool(
                ["ruff", "check", "--fix", "--extend-unfixable", "F401,F811", file_path],
                "Ruff Check",
                file_path,
            )

    elif ext == ".cs":
        if _has_command("dotnet"):
            run_tool(
                ["dotnet", "format", "--include", file_path], "dotnet format", file_path
            )

    elif ext == ".md":
        if "/.cataforge/" in file_path or "\\.cataforge\\" in file_path:
            pass
        elif _has_command("npx"):
            run_tool(
                ["npx", "markdownlint-cli", "--fix", file_path],
                "markdownlint",
                file_path,
            )

    if "dispatch-prompt.md" in file_path:
        print(
            "[SYNC] dispatch-prompt.md modified — check if tdd-engine/SKILL.md "
            "common constraints need updating",
            file=sys.stderr,
        )

    sys.exit(0)


if __name__ == "__main__":
    main()
