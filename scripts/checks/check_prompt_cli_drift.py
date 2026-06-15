#!/usr/bin/env python3
"""Anti-rot guard: prompt assets must not reference non-existent CLI verbs.

Agent / skill / protocol prompts invoke ``cataforge context|docs|kg <verb>``.
When a prompt names a verb the CLI does not register (a phantom command, e.g.
a ``write-section`` that was never implemented), the workflow silently breaks
at runtime. This guard introspects the real Click command groups and fails if
any command-styled reference in the prompts names an unknown verb.

Scope of matching — to avoid flagging prose that merely contains the word
"context" (e.g. "context authoring", "the context backend"), a reference only
counts as a command when it is written like one:

  - prefixed with ``cataforge`` — ``cataforge context finalize``
  - or the group word is opened with a backtick — `` `context read` ``

Write commands one of those two ways and the guard validates them; write
"context" as a concept word and it is ignored.

Escape hatch: append ``<!-- allow-cli-verb: <reason> -->`` to the line.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

for _stream_name in ("stdout", "stderr"):
    _stream = getattr(sys, _stream_name)
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parents[2]

SCAN_GLOBS: list[tuple[Path, str]] = [
    (REPO_ROOT / ".cataforge" / "agents", "**/AGENT.md"),
    (REPO_ROOT / ".cataforge" / "agents", "**/*PROTOCOLS*.md"),
    (REPO_ROOT / ".cataforge" / "skills", "**/*.md"),
    (REPO_ROOT / ".cataforge" / "rules", "**/*.md"),
]

GROUPS = ("context", "docs", "kg", "setup")

# cataforge-prefixed: `cataforge context finalize`
_CATAFORGE = re.compile(rf"\bcataforge\s+({'|'.join(GROUPS)})\s+([a-z][a-z-]+)")
# backtick-opened group word: `` `context read` `` / `` `context write-doc --flag` ``
_BACKTICK = re.compile(rf"`({'|'.join(GROUPS)})\s+([a-z][a-z-]+)")

ALLOW_MARKER = re.compile(r"<!--\s*allow-cli-verb")
CODE_FENCE = re.compile(r"^\s*```")


def real_verbs() -> dict[str, set[str]]:
    """Introspect the registered subcommands of each Click group."""
    from cataforge.interface.cli.main import _register_commands, cli

    _register_commands()
    out: dict[str, set[str]] = {}
    for name in GROUPS:
        grp = cli.commands.get(name)
        out[name] = set(getattr(grp, "commands", {}).keys()) if grp is not None else set()
    return out


def iter_files() -> list[Path]:
    files: list[Path] = []
    seen: set[Path] = set()
    for root, pattern in SCAN_GLOBS:
        if not root.exists():
            continue
        for p in root.glob(pattern):
            if p.is_file() and p not in seen:
                seen.add(p)
                files.append(p)
    return files


def main() -> int:
    try:
        verbs = real_verbs()
    except Exception as exc:  # pragma: no cover - import/registration failure
        print(f"prompt-cli-drift: cannot introspect CLI verbs: {exc}", file=sys.stderr)
        return 2

    fails: list[str] = []
    scanned = 0
    for path in iter_files():
        scanned += 1
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        in_code_fence = False
        for lineno, line in enumerate(text.splitlines(), 1):
            if CODE_FENCE.match(line):
                in_code_fence = not in_code_fence
                continue
            if in_code_fence or ALLOW_MARKER.search(line):
                continue
            for pattern in (_CATAFORGE, _BACKTICK):
                for group, verb in pattern.findall(line):
                    if verb not in verbs[group]:
                        rel = path.relative_to(REPO_ROOT)
                        fails.append(f"{rel}:{lineno}: `{group} {verb}` is not a real CLI verb")

    if fails:
        print("Anti-rot: prompt assets reference non-existent CLI verbs", file=sys.stderr)
        for f in sorted(set(fails)):
            print(f"  {f}", file=sys.stderr)
        print(
            "\nFix: use a registered verb (see `cataforge <group> --help`) or, "
            "if the reference is intentional prose, append "
            "`<!-- allow-cli-verb: <reason> -->` to the line.",
            file=sys.stderr,
        )
        return 1

    print(f"OK: scanned {scanned} prompt files, no phantom CLI verbs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
