"""Console port — the structured-output surface every layer programs against.

The full-featured renderer (colour, Unicode glyphs, tables, interactive
menus) lives in the interface layer. Foundational layers (utils, adapter,
application) must not import that renderer directly — that would invert the
dependency direction — so they program against the :class:`Console` Protocol
declared here and resolve the active implementation through
:func:`get_console`.

The interface layer installs its rich renderer at CLI start-up via
:func:`set_console`; outside a CLI process the default :class:`PlainConsole`
prints unstyled lines to stdout/stderr.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# Pure data carried across the port
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ChoiceOption:
    """One row in an interactive ``prompt_choice`` list."""

    key: str
    label: str
    icon: str = ""
    description: str = ""


@dataclass(frozen=True)
class DiagPattern:
    """Match-and-explain entry for log/error diagnosis.

    ``needle`` is either a literal substring or a compiled regex. When a
    pattern matches, ``diagnosis`` is shown to the user along with
    ``fix_action`` (free text) and the optional ``fix_command`` (rendered
    in bold so it's copy-pasteable).
    """

    needle: str | re.Pattern[str]
    diagnosis: str
    fix_action: str
    fix_command: str | None = None
    severity: Literal["error", "warn"] = "error"


def pattern_matches(needle: str | re.Pattern[str], blob: str) -> bool:
    if isinstance(needle, str):
        return needle in blob
    return needle.search(blob) is not None


# ---------------------------------------------------------------------------
# Port
# ---------------------------------------------------------------------------


@runtime_checkable
class Console(Protocol):
    """Structured single-line output + interactive choice prompt."""

    def section(self, msg: str) -> None: ...
    def info(self, msg: str) -> None: ...
    def ok(self, msg: str) -> None: ...
    def warn(self, msg: str) -> None: ...
    def fail(self, msg: str) -> None: ...
    def prompt_choice(
        self,
        question: str,
        options: list[ChoiceOption],
        *,
        default: str | None = None,
    ) -> str: ...


class PlainConsole:
    """Dependency-free default — unstyled lines to stdout/stderr.

    ``fail`` and ``warn`` go to stderr so they survive ``cmd > file``,
    matching the rich renderer's stream split.
    """

    def _write(self, line: str, *, err: bool = False) -> None:
        stream = sys.stderr if err else sys.stdout
        try:
            stream.write(line + "\n")
            stream.flush()
        except (BrokenPipeError, ValueError):
            pass

    def section(self, msg: str) -> None:
        self._write(f"\n[*] {msg}")

    def info(self, msg: str) -> None:
        self._write(f"  [INFO] {msg}")

    def ok(self, msg: str) -> None:
        self._write(f"  [OK] {msg}")

    def warn(self, msg: str) -> None:
        self._write(f"  [WARN] {msg}", err=True)

    def fail(self, msg: str) -> None:
        self._write(f"  [FAIL] {msg}", err=True)

    def prompt_choice(
        self,
        question: str,
        options: list[ChoiceOption],
        *,
        default: str | None = None,
    ) -> str:
        if not options:
            raise ValueError("prompt_choice requires at least one option")
        default_key = default if default is not None else options[0].key
        self._write(question)
        for opt in options:
            self._write(f"  {opt.key}) {opt.label}")
            if opt.description:
                self._write(f"       {opt.description}")
        keys = "/".join(o.key for o in options)
        valid = {o.key for o in options}
        prompt = f"\n  选择 [{keys}] (默认 {default_key}): "
        while True:
            try:
                raw = input(prompt).strip()
            except (EOFError, KeyboardInterrupt):
                self._write("")
                return default_key
            raw = raw or default_key
            if raw in valid:
                return raw
            self.warn(f"无效输入 {raw!r}，请输入 {keys}")


# ---------------------------------------------------------------------------
# Active console registry
# ---------------------------------------------------------------------------

_console: Console = PlainConsole()


def get_console() -> Console:
    """Return the active console (the rich renderer once a CLI installed it)."""
    return _console


def set_console(console: Console) -> None:
    """Install *console* as the active implementation."""
    global _console
    _console = console


# ---------------------------------------------------------------------------
# Terminal colour constants (ANSI escape codes)
# ---------------------------------------------------------------------------

BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
NC = "\033[0m"  # No Color / reset

# ---------------------------------------------------------------------------
# Structured terminal output helpers
# ---------------------------------------------------------------------------


# The five primitives below are thin wrappers over the active console so every
# caller (CLI subcommands, integrations, hook scripts) shares the same
# renderer. The interface layer installs its rich renderer at CLI start-up;
# outside a CLI process the default unstyled console handles output.


def section(msg: str) -> None:
    get_console().section(msg)


def info(msg: str) -> None:
    get_console().info(msg)


def ok(msg: str) -> None:
    get_console().ok(msg)


def warn(msg: str) -> None:
    get_console().warn(msg)


def fail(msg: str) -> None:
    get_console().fail(msg)
