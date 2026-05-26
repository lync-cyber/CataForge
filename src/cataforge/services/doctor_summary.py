"""Doctor summary service — runs ``cataforge doctor`` and extracts FAIL/WARN.

Lives in ``services/`` (not ``core/``) because it depends on Click's
``CliRunner`` and on ``cataforge.cli.main``. Keeping this dependency edge
out of ``core/`` lets feedback assemblers stay import-cycle-free and lets
tests mock the doctor summary by passing a plain dict.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_DOCTOR_FAIL_RE = re.compile(r"^\s*(?:FAIL|✖|ERROR|missing|MISSING)\b", re.MULTILINE)
_DOCTOR_WARN_RE = re.compile(r"^\s*(?:WARN|⚠)\b", re.MULTILINE)


def collect_doctor_summary(project_root: Path) -> dict[str, Any]:
    """Run ``cataforge doctor`` in-process and extract failure/warning lines.

    Uses Click's ``CliRunner`` rather than spawning a subprocess so the call
    stays fast (no fork) and so unit tests can stub the project root without
    PATH gymnastics. Failures inside doctor are captured but never raised —
    the assembler should always be able to produce a partial bundle.
    """
    out: dict[str, Any] = {"exit_code": -1, "fails": [], "warns": [], "full": ""}
    try:
        from click.testing import CliRunner

        from cataforge.cli.main import cli
    except Exception as e:
        out["fails"] = [f"(could not import doctor: {e})"]
        return out

    # ``mix_stderr`` was the default on Click ≤ 8.1 and was removed as a
    # constructor kwarg in 8.2 (now controlled via ``invoke(..., catch_exceptions)``).
    # We fall back to the keyword-less constructor so we work across both;
    # output capture mixes stderr+stdout either way under our pinned floor.
    try:
        runner = CliRunner(mix_stderr=True)  # type: ignore[call-arg]
    except TypeError:
        runner = CliRunner()
    result = runner.invoke(
        cli,
        ["--project-dir", str(project_root), "doctor"],
        catch_exceptions=True,
    )
    text = result.output or ""
    out["exit_code"] = result.exit_code
    out["full"] = text
    out["fails"] = _DOCTOR_FAIL_RE.findall(text) and [
        line for line in text.splitlines() if _DOCTOR_FAIL_RE.match(line)
    ] or []
    out["warns"] = [line for line in text.splitlines() if _DOCTOR_WARN_RE.match(line)]
    return out
