#!/usr/bin/env python3
"""PostToolUse Hook: Run formatters/linters on files modified by Edit or Write.

Matcher: Edit|Write
Skips .claude/ framework files to preserve framework formatting.
Always exits 0 — reports issues but never blocks.

Test:
  echo '{"tool_name":"Edit","tool_input":{"file_path":"src/app.ts"}}' | python .claude/hooks/lint_format.py
  Expected: exit 0, runs prettier + eslint on the file
"""

import json
import os
import shutil
import subprocess
import sys


def run_tool(cmd, label, filepath):
    """Run a formatting/linting tool, report errors to stderr."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
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
    except FileNotFoundError:
        pass  # Tool not installed — skip silently
    except subprocess.TimeoutExpired:
        pass
    except Exception:
        pass


def has_command(name):
    """Check if a command is available on PATH."""
    return shutil.which(name) is not None


def main():
    try:
        data = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    file_path = (data.get("tool_input") or {}).get("file_path")
    if not file_path:
        file_path = (data.get("tool_input") or {}).get("path")
    if not file_path:
        sys.exit(0)

    # Normalize path separators
    file_path = file_path.replace("\\", "/")

    if not os.path.isfile(file_path):
        sys.exit(0)

    ext = os.path.splitext(file_path)[1].lower()

    # JavaScript / TypeScript
    if ext in (".js", ".ts", ".jsx", ".tsx"):
        if has_command("npx"):
            run_tool(["npx", "prettier", "--write", file_path], "Prettier", file_path)
            run_tool(["npx", "eslint", "--fix", file_path], "ESLint", file_path)

    # Python
    elif ext == ".py":
        if has_command("ruff"):
            run_tool(["ruff", "format", file_path], "Ruff Format", file_path)
            run_tool(["ruff", "check", "--fix", file_path], "Ruff Check", file_path)

    # C#
    elif ext == ".cs":
        if has_command("dotnet"):
            run_tool(
                ["dotnet", "format", "--include", file_path], "dotnet format", file_path
            )

    # Markdown (skip .claude/ framework files)
    elif ext == ".md":
        if "/.claude/" in file_path or "\\.claude\\" in file_path:
            pass  # Preserve framework formatting
        elif has_command("npx"):
            run_tool(
                ["npx", "markdownlint-cli", "--fix", file_path],
                "markdownlint",
                file_path,
            )

    # Sync reminder for dispatch-prompt.md
    if "dispatch-prompt.md" in file_path:
        print(
            "[SYNC] dispatch-prompt.md modified — check if tdd-engine/SKILL.md "
            "common constraints need updating",
            file=sys.stderr,
        )

    sys.exit(0)


if __name__ == "__main__":
    main()
