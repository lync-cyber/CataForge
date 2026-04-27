"""Top-level pytest configuration.

Probes for dev-only dependencies up-front and short-circuits the run with
a friendly install hint instead of letting an e2e test deep in the suite
fail with an opaque ``ModuleNotFoundError`` 60 seconds in. This is the
fix for the "I cloned the repo and ran pytest but `build` was missing"
class of issue.

Also exposes :func:`run_utf8` — the canonical wrapper for invoking child
processes from tests with UTF-8 stdio. Use it instead of raw
``subprocess.run`` whenever the child may emit non-ASCII output (Chinese
prose, em-dashes, box-drawing). See its docstring for the cp1252 trap
this helper closes.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent

# Modules that must be importable for the test suite to function.
# Each entry is (module_name, install_hint).
REQUIRED_DEV_MODULES: tuple[tuple[str, str], ...] = (
    ("build", "pip install build  (or pip install -e '.[dev]')"),
    ("pytest", "pip install pytest"),
    ("yaml", "pip install pyyaml"),
)


def pytest_configure(config: pytest.Config) -> None:  # noqa: ARG001
    """Verify dev dependencies before collecting tests.

    Failing in pytest_configure produces a single clear stderr message
    with the install command, instead of letting tests fail one-by-one
    with cryptic stack traces. This pairs with the ``[project.optional-
    dependencies].dev`` table in pyproject.toml — that's where these
    deps are *declared*; this hook is where their *absence* is surfaced.
    """
    missing: list[tuple[str, str]] = []
    for mod, hint in REQUIRED_DEV_MODULES:
        if importlib.util.find_spec(mod) is None:
            missing.append((mod, hint))

    if not missing:
        return

    msg_lines = [
        "",
        "=" * 70,
        "Missing dev dependencies — the test suite cannot run:",
        "",
    ]
    for mod, hint in missing:
        msg_lines.append(f"  - {mod}    →  {hint}")
    msg_lines.extend([
        "",
        "Recommended one-shot:",
        "    pip install -e '.[dev]'",
        "",
        "(or with uv:  uv sync --extra dev)",
        "=" * 70,
        "",
    ])
    print("\n".join(msg_lines), file=sys.stderr)
    pytest.exit("missing dev dependencies (see message above)", returncode=2)


def pytest_sessionstart(session: pytest.Session) -> None:  # noqa: ARG001
    """Auto-install pre-commit hooks on first session if missing.

    `.pre-commit-config.yaml` runs the same ruff / utf-8-stdio / schema-
    parity checks CI does. A fresh clone without `pre-commit install`
    lets those failures escape locally and only surface 60s later in
    GitHub Actions. `pre-commit` is already a [dev] dep, and
    `pre-commit install` is idempotent + does no network I/O — safe to
    invoke automatically.

    Behaviour:

    * No .git directory  → no-op (e.g. installed wheel sources).
    * Hook already there → no-op.
    * `CATAFORGE_SKIP_HOOK_AUTOINSTALL=1` set → no-op (CI / power users).
    * Otherwise           → run ``pre-commit install`` and log result.

    Any error during install fails soft — the test session must not be
    blocked by a setup convenience.
    """
    if os.environ.get("CATAFORGE_SKIP_HOOK_AUTOINSTALL"):
        return
    try:
        git_dir = _REPO_ROOT / ".git"
        if not git_dir.is_dir():
            return
        hook = git_dir / "hooks" / "pre-commit"
        if hook.is_file():
            return
    except OSError:
        return

    try:
        result = subprocess.run(
            [sys.executable, "-m", "pre_commit", "install"],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired) as exc:
        print(
            f"\n⚠  pre-commit not auto-installed ({exc}); run "
            "`pre-commit install` manually.\n",
            file=sys.stderr,
        )
        return

    if result.returncode == 0:
        print(
            "\n".join([
                "",
                "─" * 70,
                "✓ pre-commit hooks auto-installed (.git/hooks/pre-commit).",
                "  ruff / utf-8-stdio / schema-parity checks now run on commit.",
                "  Opt out: export CATAFORGE_SKIP_HOOK_AUTOINSTALL=1",
                "─" * 70,
                "",
            ]),
            file=sys.stderr,
        )
    else:
        print(
            f"\n⚠  pre-commit install failed (rc={result.returncode}): "
            f"{result.stderr.strip()[:200]}\n",
            file=sys.stderr,
        )


# ---------------------------------------------------------------------------
# UTF-8 subprocess helper
# ---------------------------------------------------------------------------


def run_utf8(
    cmd: list[str],
    *,
    cwd: str | Path | None = None,
    check: bool = False,
    timeout: float = 60,
    extra_env: dict[str, str] | None = None,
    **kwargs: Any,
) -> subprocess.CompletedProcess[str]:
    """``subprocess.run`` wrapper that always decodes child stdio as UTF-8.

    Why this exists: ``subprocess.run(text=True)`` decodes captured
    bytes with the *parent*'s ``locale.getpreferredencoding`` — on
    Windows CI that's cp1252. cataforge's CLI scripts force UTF-8
    output via ``ensure_utf8_stdio()`` + ``PYTHONUTF8=1``, so the
    captured bytes are UTF-8. Decoding UTF-8 as cp1252 raises
    ``UnicodeDecodeError`` inside the reader thread, which then
    silently leaves ``CompletedProcess.stdout`` as ``None``. Tests
    that call ``json.loads(r.stdout)`` blow up with a confusing
    ``TypeError: ... not NoneType`` — the underlying decode error is
    only visible as a ``PytestUnhandledThreadExceptionWarning`` in the
    log tail.

    Use this helper for *any* test that captures stdio from a child
    cataforge process or other UTF-8-emitting tool. It pins
    ``encoding="utf-8"``, ``errors="replace"`` (so a stray byte never
    crashes the test), and ``PYTHONUTF8=1`` in the child env.
    """
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd is not None else None,
        check=check,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        env=env,
        **kwargs,
    )


@pytest.fixture
def run_utf8_subprocess():
    """Pytest-fixture form of :func:`run_utf8` for tests that prefer DI."""
    return run_utf8
