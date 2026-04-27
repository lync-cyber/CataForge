"""Top-level pytest configuration.

Probes for dev-only dependencies up-front and short-circuits the run with
a friendly install hint instead of letting an e2e test deep in the suite
fail with an opaque ``ModuleNotFoundError`` 60 seconds in. This is the
fix for the "I cloned the repo and ran pytest but `build` was missing"
class of issue.
"""

from __future__ import annotations

import importlib.util
import sys

import pytest

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
