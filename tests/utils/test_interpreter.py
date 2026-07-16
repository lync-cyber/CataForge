"""Hook interpreter resolution — commands pin the deploying ``sys.executable``."""

from __future__ import annotations

import sys
from pathlib import Path

from cataforge.utils.interpreter import (
    hook_command_template,
    interpreter_command,
    interpreter_path,
)


def test_interpreter_path_is_forward_slash_sys_executable() -> None:
    path = interpreter_path()
    assert path == Path(sys.executable).as_posix()
    assert "\\" not in path


def test_interpreter_command_is_quoted() -> None:
    cmd = interpreter_command()
    assert cmd == f'"{interpreter_path()}"'
    assert cmd.startswith('"') and cmd.endswith('"')


def test_hook_command_template_formats_module() -> None:
    template = hook_command_template()
    cmd = template.format(module="guard_dangerous")
    assert cmd == (f"{interpreter_command()} -m cataforge.runtime.hook.scripts.guard_dangerous")


def test_hook_command_template_survives_braces_in_interpreter_path(
    monkeypatch,
) -> None:
    # 分隔符中立的路径：反斜杠仅在 Windows 上是路径分隔符，POSIX 上
    # as_posix() 不会转换它；本测试只关心大括号能否穿过 str.format。
    monkeypatch.setattr(sys, "executable", "C:/odd{dir}/python.exe")
    cmd = hook_command_template().format(module="lint_format")
    assert cmd == '"C:/odd{dir}/python.exe" -m cataforge.runtime.hook.scripts.lint_format'
