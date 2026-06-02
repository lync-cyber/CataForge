"""Verify validate_agent_result imports cleanly outside a project root."""

from __future__ import annotations

import subprocess
import sys


def test_validate_agent_result_importable_outside_project(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import cataforge.runtime.hook.scripts.validate_agent_result",
        ],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"import failed (rc={result.returncode}):\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
