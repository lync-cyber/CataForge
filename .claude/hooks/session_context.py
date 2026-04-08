#!/usr/bin/env python3
"""SessionStart Hook: Inject plan summary and project context at session start.

Test:
  echo '{}' | python .claude/hooks/session_context.py
  Expected: JSON with additionalContext field (if plans exist)
"""

import json
import os
import sys

# Event logger integration
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
try:
    from event_logger import append_event as _log_event
except ImportError:
    _log_event = None


def _detect_pkg_env(project_dir: str, which_fn) -> str:
    """Detect project package manager(s) and return context string.

    Supports: Python (uv/pip), Node.js (npm/yarn/pnpm), Go, .NET.
    """
    sections = []
    _join = os.path.join
    _exists = os.path.isfile

    # --- Python ---
    has_pyproject = _exists(_join(project_dir, "pyproject.toml"))
    has_requirements = _exists(_join(project_dir, "requirements.txt"))
    if has_pyproject or has_requirements:
        pkg = "pip"
        if _exists(_join(project_dir, "uv.lock")):
            pkg = "uv"
        elif has_pyproject:
            try:
                with open(
                    _join(project_dir, "pyproject.toml"), "r", encoding="utf-8"
                ) as f:
                    if "[tool.uv]" in f.read():
                        pkg = "uv"
            except OSError:
                pass
        if pkg == "pip" and which_fn("uv") and has_pyproject:
            pkg = "uv"
        install = "uv sync" if pkg == "uv" else "pip install -e ."
        test = "uv run python -m pytest" if pkg == "uv" else "python -m pytest"
        sections.append(
            f"Python pkg-manager: {pkg}  |  install: {install}  |  test: {test}"
        )

    # --- Node.js ---
    if _exists(_join(project_dir, "package.json")):
        pkg = "npm"
        if _exists(_join(project_dir, "pnpm-lock.yaml")):
            pkg = "pnpm"
        elif _exists(_join(project_dir, "yarn.lock")):
            pkg = "yarn"
        elif _exists(_join(project_dir, "package-lock.json")):
            pkg = "npm"
        elif _exists(_join(project_dir, "bun.lockb")) or _exists(
            _join(project_dir, "bun.lock")
        ):
            pkg = "bun"
        run_prefix = {
            "npm": "npx",
            "yarn": "yarn",
            "pnpm": "pnpm exec",
            "bun": "bunx",
        }.get(pkg, "npx")
        sections.append(
            f"Node pkg-manager: {pkg}  |  install: {pkg} install  |  run: {run_prefix}"
        )

    # --- Go ---
    if _exists(_join(project_dir, "go.mod")):
        sections.append(
            "Go modules detected  |  install: go mod download  |  test: go test ./..."
        )

    # --- .NET ---
    has_dotnet = False
    try:
        has_dotnet = any(
            f.endswith((".csproj", ".sln")) for f in os.listdir(project_dir)
        )
    except OSError:
        pass
    if has_dotnet:
        sections.append(
            "dotnet detected  |  install: dotnet restore  |  test: dotnet test"
        )

    if not sections:
        return ""

    header = "=== Project Environment ==="
    footer = "IMPORTANT: Use the detected package manager consistently across sessions. Do NOT mix alternatives (e.g. uv/pip, npm/yarn/pnpm)."
    return f"{header}\n" + "\n".join(sections) + f"\n{footer}"


def _ensure_utf8_stdio():
    """Wrap stdout/stderr with UTF-8 encoding on Windows (CLI use only)."""
    import io

    if sys.stdout.encoding != "utf-8":
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace"
        )
    if sys.stderr.encoding != "utf-8":
        sys.stderr = io.TextIOWrapper(
            sys.stderr.buffer, encoding="utf-8", errors="replace"
        )


def main():
    _ensure_utf8_stdio()
    # Locate project root (two levels up from hooks/)
    hooks_dir = os.path.dirname(os.path.abspath(__file__))
    claude_dir = os.path.dirname(hooks_dir)
    project_dir = os.path.dirname(claude_dir)

    context_parts = []

    # Check for active plan
    plan_path = os.path.join(project_dir, ".claude", "plans", "PLAN.md")
    if os.path.isfile(plan_path):
        try:
            with open(plan_path, "r", encoding="utf-8") as f:
                lines = []
                for i, line in enumerate(f):
                    if i >= 20:
                        break
                    lines.append(line.rstrip())
            if lines:
                plan_summary = "\n".join(lines).strip()
                context_parts.append(
                    f"=== Active Plan (.claude/plans/PLAN.md) ===\n{plan_summary}\n..."
                )
        except OSError:
            pass

    # List plan files
    plans_dir = os.path.join(project_dir, ".claude", "plans")
    if os.path.isdir(plans_dir):
        try:
            plan_files = [f for f in os.listdir(plans_dir) if f.endswith(".md")]
            if plan_files:
                context_parts.append(
                    f"Plan files available: {', '.join(sorted(plan_files))}"
                )
        except OSError:
            pass

    # Detect package manager for environment consistency across sessions
    import shutil

    env_lines = _detect_pkg_env(project_dir, shutil.which)
    if env_lines:
        context_parts.append(env_lines)

    if context_parts:
        context_text = "\n\n".join(context_parts)
        output = json.dumps({"additionalContext": context_text}, ensure_ascii=False)
        print(output)

    # Log session_start event
    if _log_event:
        phase = "unknown"
        claude_md = os.path.join(project_dir, "CLAUDE.md")
        if os.path.isfile(claude_md):
            try:
                with open(claude_md, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip().startswith("- 当前阶段:"):
                            raw = line.split(":", 1)[1].strip()
                            # Skip unresolved template placeholders like {requirements|...}
                            if raw.startswith("{"):
                                break
                            phase = raw.split("|")[0].strip()
                            break
            except OSError:
                pass
        try:
            _log_event(
                event="session_start",
                phase=phase,
                detail="会话启动",
            )
        except Exception:
            pass  # Never block on logging failure

    sys.exit(0)


if __name__ == "__main__":
    main()
