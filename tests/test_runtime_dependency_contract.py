"""Wheel dependency contract — the runtime tree must stay pip-installable.

`[project] dependencies` must not pull the linkml stack: linkml-runtime →
prefixcommons declares pytest-logging (a 2015-sdist-only test plugin that
fails to build under modern setuptools) as a runtime dependency, which breaks
plain `pip install cataforge`. pip ignores `[tool.uv] override-dependencies`,
so the only protection for pip consumers is keeping the chain out of the
published metadata entirely; the linkml toolchain lives in the `dev` extra
for schema codegen only.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_runtime_dependencies_exclude_linkml_stack() -> None:
    with (REPO_ROOT / "pyproject.toml").open("rb") as fh:
        pyproject = tomllib.load(fh)

    runtime_deps = pyproject["project"]["dependencies"]
    offenders = [dep for dep in runtime_deps if dep.lower().startswith(("linkml", "prefixcommons"))]
    assert not offenders, f"runtime dependencies must not include the linkml stack: {offenders}"
