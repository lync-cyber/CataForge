#!/bin/bash
# CataForge SessionStart hook — prepares Claude Code on the web sessions.
#
# Installs the editable package + dev extras so the toolchain (ruff,
# pytest, pre-commit, the `cataforge` CLI) is importable by the session
# Python, wires the git pre-commit hook, and persists a few env vars that
# keep CataForge's UTF-8 Chinese diagnostics and output streaming sane.
#
# Synchronous on purpose: the session waits until deps are ready, so the
# agent never races ahead of an install when running tests or linters.
set -euo pipefail

# Web-only: local clones manage their own venv per CLAUDE.md.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-.}"

# Editable install + dev extras. uv resolves from uv.lock and reuses the
# container's package cache, so re-runs are near-instant (idempotent).
if command -v uv >/dev/null 2>&1; then
  uv pip install --system -e ".[dev]"
else
  pip install -e ".[dev]"
fi

# Canonical one-time setup per CLAUDE.md: hang the static-check gate off
# .git/hooks/pre-commit. `|| true` keeps the session resilient if the
# pre-commit package or git dir is unavailable.
pre-commit install >/dev/null 2>&1 || true

# Persist session env vars (see also the "环境变量配置" section in README).
if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  {
    # UTF-8 everywhere: run_local.py emits Chinese diagnostics; avoids
    # cp1252/ascii encode crashes when piping check output.
    echo 'export PYTHONUTF8=1'
    echo 'export PYTHONIOENCODING=utf-8'
    echo 'export LANG=C.UTF-8'
    echo 'export LC_ALL=C.UTF-8'
    # Stream test/lint output immediately instead of block-buffering.
    echo 'export PYTHONUNBUFFERED=1'
    # No stray __pycache__/*.pyc churning the working tree.
    echo 'export PYTHONDONTWRITEBYTECODE=1'
    # Quieter, faster pip/uv inside the session.
    echo 'export PIP_DISABLE_PIP_VERSION_CHECK=1'
    echo 'export PIP_NO_INPUT=1'
    # Coloured ruff/pytest output in the web terminal.
    echo 'export FORCE_COLOR=1'
  } >> "$CLAUDE_ENV_FILE"
fi
