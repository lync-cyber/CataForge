"""Codex-shaped hook payload handling.

Codex serializes hook ``tool_name`` with canonical names (``Bash`` /
``apply_patch`` / ``spawn_agent``) that differ from the model-facing
``tool_map`` names, and ``apply_patch`` payloads carry the patch text in
``tool_input.command`` instead of a ``file_path``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from cataforge.runtime.hook.base import (
    clear_tool_map_cache,
    extract_edited_paths,
    matches_capability,
)

_PATCH = """*** Begin Patch
*** Update File: docs/prd/prd.md
@@
-old line
+new line
*** Add File: src/new_module.py
+print("hi")
*** End Patch
"""


@pytest.fixture
def codex_platform(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CATAFORGE_PLATFORM", "codex")
    clear_tool_map_cache()
    yield
    clear_tool_map_cache()


@pytest.mark.usefixtures("codex_platform")
@pytest.mark.parametrize(
    ("tool_name", "capability", "expected"),
    [
        ("Bash", "shell_exec", True),  # hook payload canonical name (tool_overrides)
        ("shell", "shell_exec", False),  # model-facing name — overrides take precedence
        ("apply_patch", "file_edit", True),
        ("apply_patch", "file_write", True),
        ("spawn_agent", "agent_dispatch", True),
        ("Bash", "file_edit", False),
        ("anything", "user_question", False),  # user_question unmapped on codex
    ],
)
def test_matches_capability_codex_names(tool_name: str, capability: str, expected: bool) -> None:
    assert matches_capability({"tool_name": tool_name}, capability) is expected


def test_extract_edited_paths_explicit_path_wins() -> None:
    data = {"tool_name": "apply_patch", "tool_input": {"file_path": "a/b.py", "command": _PATCH}}
    assert extract_edited_paths(data) == ["a/b.py"]


def test_extract_edited_paths_apply_patch_command() -> None:
    data = {"tool_name": "apply_patch", "tool_input": {"command": _PATCH}}
    assert extract_edited_paths(data) == ["docs/prd/prd.md", "src/new_module.py"]


def test_extract_edited_paths_move_to_counts() -> None:
    patch = (
        "*** Begin Patch\n*** Update File: docs/arch/arch.md\n"
        "*** Move to: docs/arch/renamed.md\n*** End Patch\n"
    )
    data = {"tool_name": "apply_patch", "tool_input": {"command": patch}}
    assert extract_edited_paths(data) == ["docs/arch/arch.md", "docs/arch/renamed.md"]


def test_extract_edited_paths_non_apply_patch_command_ignored() -> None:
    data = {"tool_name": "Bash", "tool_input": {"command": "*** Update File: x.md"}}
    assert extract_edited_paths(data) == []


def _run_script(
    module: str, payload: dict, *, unattended: bool = False
) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "CATAFORGE_PLATFORM": "codex", "PYTHONUTF8": "1"}
    env.pop("CATAFORGE_UNATTENDED", None)
    if unattended:
        env["CATAFORGE_UNATTENDED"] = "1"
    return subprocess.run(
        [sys.executable, "-m", f"cataforge.runtime.hook.scripts.{module}"],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
    )


def test_guard_frozen_docs_blocks_apply_patch_to_frozen_doc() -> None:
    payload = {"tool_name": "apply_patch", "tool_input": {"command": _PATCH}}
    r = _run_script("guard_frozen_docs", payload, unattended=True)
    assert r.returncode == 2
    assert "docs/prd/prd.md" in r.stderr


def test_guard_frozen_docs_allows_apply_patch_elsewhere() -> None:
    patch = "*** Begin Patch\n*** Update File: src/app.py\n*** End Patch\n"
    payload = {"tool_name": "apply_patch", "tool_input": {"command": patch}}
    r = _run_script("guard_frozen_docs", payload, unattended=True)
    assert r.returncode == 0


def test_guard_dangerous_handles_argv_list_command() -> None:
    payload = {"tool_name": "Bash", "tool_input": {"command": ["bash", "-lc", "rm -rf /"]}}
    r = _run_script("guard_dangerous", payload, unattended=True)
    assert r.returncode == 2


def test_log_agent_dispatch_reads_agent_type_and_message() -> None:
    payload = {
        "tool_name": "spawn_agent",
        "tool_input": {"agent_type": "reviewer", "message": "任务类型: revision\n..."},
    }
    r = _run_script("log_agent_dispatch", payload)
    assert r.returncode == 0
    assert "agent=reviewer" in r.stderr
    assert "task_type=revision" in r.stderr


def test_validate_agent_result_reads_tool_response() -> None:
    payload = {
        "tool_name": "spawn_agent",
        "tool_input": {"agent_type": "implementer"},
        "tool_response": "no agent-result tag here",
    }
    r = _run_script("validate_agent_result", payload)
    assert r.returncode == 0
    assert "missing <agent-result> tag" in r.stderr


def test_notify_permission_message_falls_back_to_tool_description() -> None:
    from cataforge.runtime.hook.scripts.notify_permission import _resolve_message

    assert _resolve_message({"message": "explicit"}) == "explicit"
    assert (
        _resolve_message({"tool_name": "Bash", "tool_input": {"description": "rm -rf guard"}})
        == "rm -rf guard"
    )
    assert _resolve_message({"tool_name": "Bash", "tool_input": {}}) == "Bash requires approval"
    assert _resolve_message({}) == "Action requires approval"
