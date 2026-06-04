"""Doctor summary service — runs ``cataforge doctor`` and extracts FAIL/WARN.

Runs ``cataforge doctor`` as a subprocess and parses its rendered output for
failure/warning lines. The subprocess boundary keeps this service from importing
the ``interface`` CLI surface, so feedback assemblers (which call it) stay free
of an upward dependency edge.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from cataforge.utils.run_subprocess import run as run_proc

_DOCTOR_FAIL_RE = re.compile(r"^\s*(?:FAIL|✖|ERROR|missing|MISSING)\b", re.MULTILINE)
_DOCTOR_WARN_RE = re.compile(r"^\s*(?:WARN|⚠)\b", re.MULTILINE)


def collect_doctor_summary(project_root: Path) -> dict[str, Any]:
    """Run ``cataforge doctor`` and extract failure/warning lines.

    Spawns ``python -m cataforge --project-dir <root> doctor`` so the call
    stays clear of the ``interface`` import surface. Failures inside doctor are
    captured but never raised — the assembler should always be able to produce
    a partial bundle.
    """
    out: dict[str, Any] = {"exit_code": -1, "fails": [], "warns": [], "full": ""}
    try:
        result = run_proc(
            [sys.executable, "-m", "cataforge", "--project-dir", str(project_root), "doctor"],
        )
    except (OSError, subprocess.SubprocessError) as e:
        out["fails"] = [f"(could not run doctor: {e})"]
        return out

    text = (result.stdout or "") + (result.stderr or "")
    out["exit_code"] = result.returncode
    out["full"] = text
    if _DOCTOR_FAIL_RE.search(text):
        out["fails"] = [line for line in text.splitlines() if _DOCTOR_FAIL_RE.match(line)]
    else:
        out["fails"] = []
    out["warns"] = [line for line in text.splitlines() if _DOCTOR_WARN_RE.match(line)]
    return out
