"""guard_dangerous PreToolUse hook — the unattended deny layer.

The tool-level deny net must block merge / PR-merge / push-to-main only when
the building-loop marker ``CATAFORGE_UNATTENDED`` is set, and be a no-op
otherwise. Driven through the real module entry point over stdin.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys


def _run_guard(command: str, *, unattended: bool) -> subprocess.CompletedProcess[str]:
    env = {**os.environ}
    env.pop("CATAFORGE_UNATTENDED", None)
    if unattended:
        env["CATAFORGE_UNATTENDED"] = "1"
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    return subprocess.run(
        [sys.executable, "-m", "cataforge.runtime.hook.scripts.guard_dangerous"],
        input=payload,
        capture_output=True,
        text=True,
        env=env,
    )


def test_unattended_blocks_merge() -> None:
    r = _run_guard("git merge feat-x", unattended=True)
    assert r.returncode == 2
    assert "merge" in r.stderr


def test_unattended_blocks_pr_merge() -> None:
    r = _run_guard("gh pr merge 12 --squash", unattended=True)
    assert r.returncode == 2


def test_unattended_blocks_push_main() -> None:
    r = _run_guard("git push origin main", unattended=True)
    assert r.returncode == 2


def test_merge_allowed_when_not_unattended() -> None:
    r = _run_guard("git merge feat-x", unattended=False)
    assert r.returncode == 0


def test_unattended_allows_benign_command() -> None:
    r = _run_guard("git status", unattended=True)
    assert r.returncode == 0


def test_still_blocks_baseline_dangerous_command() -> None:
    r = _run_guard("rm -rf /tmp/x", unattended=False)
    assert r.returncode == 2
