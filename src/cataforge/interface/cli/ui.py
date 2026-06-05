"""Unified CLI rendering surface for cataforge.

Every CLI subcommand should import the module-level ``ui`` singleton and
call methods on it (``ui.ok(...)``, ``ui.section(...)``, ``ui.table(...)``)
instead of touching ``click.echo`` / ``click.secho`` / raw ANSI directly.

Design constraints:

* **Color & Unicode are auto-detected** from ``NO_COLOR``, ``CLICOLOR_FORCE``,
  ``CATAFORGE_NO_UNICODE``, and ``sys.stdout.isatty()``. The legacy Windows
  cmd.exe falls back to ASCII glyphs (``[OK]`` instead of ``✔``).
* **Stderr split** — ``ui.fail`` and ``ui.warn`` go to ``sys.stderr`` so they
  survive ``cataforge cmd > file``. Everything else goes to stdout.
* **Tests stay deterministic** — colour and Unicode can be overridden at
  ``UI(...)`` construction time so tests don't depend on terminal capability.
"""

from __future__ import annotations

import logging
import os
import re
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Literal, TextIO

from cataforge.utils.console import (
    ChoiceOption,
    DiagPattern,
    pattern_matches,
    set_console,
)

__all__ = [
    "UI",
    "ChoiceOption",
    "DiagPattern",
    "NextStep",
    "CheckResult",
    "ui",
]

_logger = logging.getLogger("cataforge.interface.cli.ui")

# ---------------------------------------------------------------------------
# Terminal capability detection
# ---------------------------------------------------------------------------


def _detect_color() -> bool:
    """Whether to emit ANSI colour escape sequences.

    Follows the `NO_COLOR <https://no-color.org/>`_ informal standard plus
    the click-style ``CLICOLOR_FORCE`` override. Defaults to "on if stdout
    is a TTY", matching what most well-behaved CLIs do.
    """
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("CLICOLOR_FORCE"):
        return True
    if os.environ.get("CATAFORGE_NO_COLOR"):
        return False
    try:
        return sys.stdout.isatty()
    except (AttributeError, ValueError):
        return False


def _detect_unicode() -> bool:
    """Whether to emit Unicode glyphs (✔/✖/⚠/ℹ/━) or ASCII fallbacks."""
    if os.environ.get("CATAFORGE_NO_UNICODE"):
        return False
    encoding = (getattr(sys.stdout, "encoding", "") or "").lower()
    # Modern terminals announce utf-8; legacy cmd.exe announces cp1252/cp936.
    return "utf" in encoding


# ANSI escapes — only emitted when ``UI.color`` is True.
_ANSI = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "cyan": "\033[36m",
}


# ---------------------------------------------------------------------------
# Public dataclasses (used by guidance.py / diagnostics.py too)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NextStep:
    """A single follow-up command to suggest after a subcommand finishes."""

    command: str
    why: str = ""


@dataclass
class CheckResult:
    """One row in a ``doctor``-style diagnostic table.

    Kept dataclass-mutable so check functions can populate it incrementally.
    """

    label: str
    status: Literal["pass", "fail", "warn", "info"] = "pass"
    detail: str = ""
    hint: str | None = None


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------


_GLYPH_UNICODE = {
    "ok": "✔",
    "fail": "✖",
    "warn": "⚠",
    "info": "ℹ",
    "bullet": "•",
    "arrow": "▸",
    "hr": "━",
}
_GLYPH_ASCII = {
    "ok": "[OK]",
    "fail": "[FAIL]",
    "warn": "[WARN]",
    "info": "[INFO]",
    "bullet": "*",
    "arrow": ">",
    "hr": "-",
}


class UI:
    """Render structured CLI output to stdout/stderr with consistent style."""

    def __init__(
        self,
        *,
        color: bool | None = None,
        unicode: bool | None = None,
        stdout: TextIO | None = None,
        stderr: TextIO | None = None,
    ) -> None:
        self.color = color if color is not None else _detect_color()
        self.unicode = unicode if unicode is not None else _detect_unicode()
        # Explicit stream overrides are pinned (tests pass StringIO). When
        # neither is given, ``_write`` dynamically reads ``sys.stdout`` /
        # ``sys.stderr`` so pytest's ``capsys`` (which swaps those between
        # calls) and host apps that wrap stdio after import both work.
        self._stdout_override = stdout
        self._stderr_override = stderr

    # ── colour helpers ─────────────────────────────────────────────────
    def _c(self, code: str, text: str) -> str:
        if not self.color:
            return text
        return f"{_ANSI[code]}{text}{_ANSI['reset']}"

    def _glyph(self, key: str) -> str:
        return (_GLYPH_UNICODE if self.unicode else _GLYPH_ASCII)[key]

    def _write(self, line: str, *, err: bool = False) -> None:
        if err:
            stream = self._stderr_override if self._stderr_override is not None else sys.stderr
        else:
            stream = self._stdout_override if self._stdout_override is not None else sys.stdout
        try:
            stream.write(line + "\n")
            stream.flush()
        except BrokenPipeError:
            # Downstream of a closed pipe (``cataforge … | head``). The
            # canonical CLI response is to stop writing silently rather
            # than spam errors on every subsequent line.
            pass
        except ValueError as e:
            # Typically ``I/O operation on closed file`` — happens in
            # pytest's CliRunner when the captured stream is swapped
            # between invocations. Log at DEBUG so it's recoverable in
            # tracing without polluting normal output, but don't lump
            # it together with BrokenPipeError (different cause; if a
            # real ValueError ever escapes from a stream write we want
            # to see it, not just swallow it forever).
            _logger.debug("ui write got ValueError: %s", e)

    # ── section structure ──────────────────────────────────────────────
    def header(self, title: str, *, subtitle: str | None = None) -> None:
        """Render a top-of-output banner: ``━━ Title ━━━ … ━━━``."""
        bar_char = self._glyph("hr")
        bar = bar_char * max(len(title) + 4, 50)
        self._write("")
        self._write(self._c("bold", self._c("cyan", f"{bar_char * 2} {title} {bar}")))
        if subtitle:
            self._write("  " + self._c("dim", subtitle))
        self._write("")

    def section(self, title: str) -> None:
        """Render a mid-output section header: ``[*] Title``."""
        self._write("")
        self._write(self._c("bold", f"[*] {title}"))

    def hr(self) -> None:
        """Render a horizontal rule (50 chars)."""
        self._write(self._c("dim", self._glyph("hr") * 50))

    # ── single-line status ─────────────────────────────────────────────
    def ok(self, msg: str) -> None:
        self._write(f"  {self._c('green', self._glyph('ok'))} {msg}")

    def fail(self, msg: str) -> None:
        self._write(f"  {self._c('red', self._glyph('fail'))} {msg}", err=True)

    def warn(self, msg: str) -> None:
        self._write(f"  {self._c('yellow', self._glyph('warn'))} {msg}", err=True)

    def info(self, msg: str) -> None:
        glyph = self._glyph("info")
        self._write("  " + self._c("dim", f"{glyph} {msg}"))

    def step(
        self,
        n: int,
        total: int,
        msg: str,
        *,
        state: Literal["run", "skip", "done", "fail"] = "run",
    ) -> None:
        """Render an ``[i/N] msg`` step line; colour follows state."""
        colour = {"run": "cyan", "skip": "dim", "done": "green", "fail": "red"}[state]
        marker = self._c(colour, f"[{n}/{total}]")
        self._write(f"  {marker} {msg}")

    # ── structured ─────────────────────────────────────────────────────
    def table(
        self,
        headers: Sequence[str],
        rows: Sequence[Sequence[str]],
        *,
        align: Sequence[Literal["l", "r", "c"]] | None = None,
    ) -> None:
        """Pretty-print an aligned text table.

        ``rows`` cells may contain ANSI escapes; column widths are computed
        on the *visible* width (escapes stripped) so coloured cells still
        align with their plain neighbours.
        """
        if not headers and not rows:
            return
        ncols = max(len(headers), max((len(r) for r in rows), default=0))
        align_spec = list(align) if align else ["l"] * ncols
        while len(align_spec) < ncols:
            align_spec.append("l")

        norm_rows = [list(r) + [""] * (ncols - len(r)) for r in rows]
        norm_headers = list(headers) + [""] * (ncols - len(headers))

        widths = [
            max(
                _visible_width(norm_headers[i]),
                max((_visible_width(r[i]) for r in norm_rows), default=0),
            )
            for i in range(ncols)
        ]

        def _pad(cell: str, width: int, how: str) -> str:
            pad = width - _visible_width(cell)
            if pad <= 0:
                return cell
            if how == "r":
                return " " * pad + cell
            if how == "c":
                left = pad // 2
                return " " * left + cell + " " * (pad - left)
            return cell + " " * pad

        sep = "  "
        head = sep.join(
            self._c("bold", _pad(norm_headers[i], widths[i], align_spec[i])) for i in range(ncols)
        )
        self._write("  " + head)
        rule = sep.join(self._glyph("hr") * widths[i] for i in range(ncols))
        self._write("  " + self._c("dim", rule))
        for row in norm_rows:
            line = sep.join(_pad(row[i], widths[i], align_spec[i]) for i in range(ncols))
            self._write("  " + line)

    def kv(self, pairs: dict[str, str], *, indent: int = 2) -> None:
        """Render aligned key-value pairs (``key  : value``)."""
        if not pairs:
            return
        width = max(len(k) for k in pairs)
        pad = " " * indent
        for k, v in pairs.items():
            self._write(f"{pad}{self._c('bold', k.ljust(width))}  {v}")

    def bullets(self, items: Iterable[str], *, indent: int = 2) -> None:
        bullet = self._glyph("bullet")
        pad = " " * indent
        for item in items:
            self._write(f"{pad}{self._c('cyan', bullet)} {item}")

    def code(self, content: str) -> None:
        """Render a shell snippet — indented + dim, copy-pasteable."""
        for line in content.splitlines():
            self._write("    " + self._c("dim", line))

    # ── guidance ───────────────────────────────────────────────────────
    def next_steps(self, steps: Sequence[str | NextStep]) -> None:
        """Print a ``下一步:`` block listing follow-up commands."""
        if not steps:
            return
        self._write("")
        self._write("  " + self._c("bold", "下一步:"))
        arrow = self._glyph("arrow")
        for s in steps:
            if isinstance(s, NextStep):
                cmd = self._c("bold", s.command)
                if s.why:
                    self._write(f"  {self._c('cyan', arrow)} {cmd}   {self._c('dim', s.why)}")
                else:
                    self._write(f"  {self._c('cyan', arrow)} {cmd}")
            else:
                self._write(f"  {self._c('cyan', arrow)} {self._c('bold', s)}")
        self._write("")

    def diagnose(
        self,
        blob: str,
        patterns: Sequence[DiagPattern],
    ) -> list[DiagPattern]:
        """Match *blob* against *patterns*; print diagnosis lines.

        Returns the list of patterns that matched, so the caller can decide
        on its exit code without re-running the matching logic.
        """
        matched: list[DiagPattern] = []
        for p in patterns:
            if pattern_matches(p.needle, blob):
                matched.append(p)
        if not matched:
            return matched
        for p in matched:
            sev = self._c("yellow" if p.severity == "warn" else "red", "诊断")
            fix = self._c("yellow", "修复")
            self._write(f"  {sev}: {p.diagnosis}")
            self._write(f"  {fix}: {p.fix_action}")
            if p.fix_command:
                arrow = self._c("cyan", self._glyph("arrow"))
                self._write(f"         {arrow} {self._c('bold', p.fix_command)}")
        return matched

    # ── interactive ────────────────────────────────────────────────────
    def prompt_choice(
        self,
        question: str,
        options: Sequence[ChoiceOption],
        *,
        default: str | None = None,
    ) -> str:
        """Render a card-style menu and return the chosen ``key``.

        EOFError / KeyboardInterrupt fall back to ``default``. If ``default``
        is not provided, the first option's key is used.
        """
        if not options:
            raise ValueError("prompt_choice requires at least one option")
        default_key = default if default is not None else options[0].key
        self._write("")
        for opt in options:
            head = f"{self._c('bold', opt.key + ')')} "
            icon = (self._c("cyan", opt.icon) + "  ") if opt.icon else ""
            self._write(f"  {head} {opt.label}    {icon}")
            if opt.description:
                self._write("       " + self._c("dim", opt.description))
        keys = "/".join(o.key for o in options)
        prompt = f"\n  选择 [{keys}] (默认 {default_key}): "
        valid = {o.key for o in options}
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

    def prompt_confirm(self, question: str, *, default: bool = True) -> bool:
        """Yes/no prompt; EOF/Ctrl-C → default."""
        suffix = " [Y/n]" if default else " [y/N]"
        try:
            raw = input(question + suffix + ": ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            self._write("")
            return default
        if not raw:
            return default
        return raw in ("y", "yes")

    # ── plain passthrough ──────────────────────────────────────────────
    def print(self, msg: str = "", *, err: bool = False) -> None:
        """Escape hatch — pass-through for content that doesn't fit a helper."""
        self._write(msg, err=err)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _visible_width(text: str) -> int:
    """Visual width of *text* ignoring ANSI escapes.

    A naive ``len()`` overcounts when cells contain colour escapes; this
    keeps table alignment working with mixed coloured/plain cells.
    """
    return len(_ANSI_RE.sub("", text))


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

ui = UI()
"""The default ``UI`` instance — every subcommand imports this.

Reconfiguration at test time::

    from cataforge.interface.cli import ui as ui_mod
    ui_mod.ui = ui_mod.UI(color=False, unicode=True, stdout=io.StringIO())
"""

# Lower layers (utils/adapter/application) reach this renderer through
# ``cataforge.utils.console.get_console()`` rather than importing it; install
# it as the active console so their output keeps the rich CLI styling.
set_console(ui)
