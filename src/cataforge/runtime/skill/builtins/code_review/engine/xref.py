"""Set-difference cross-reference kernel (declare × consume).

The shared shape behind several Layer 1 checks: a *declaration* pattern
captures keys defined in the reviewed files, a *consumption* pattern
captures keys referenced anywhere in the corpus, and declarations whose
key has zero consumers are the findings. Instantiated by ``ui_fidelity``
(dead token / unloaded font / ghost class) and ``config_keys``
(declared-but-never-read config keys).

Every pattern must carry exactly one capture group — group 1 is the raw
key. An optional ``normalize`` callable maps one raw capture to zero or
more canonical keys (splitting class lists, stripping quotes, dropping
generic values).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass

Normalize = Callable[[str], Iterable[str]]


@dataclass(frozen=True)
class Occurrence:
    """One declared key with its location."""

    key: str
    file: str
    line: int


def collect_keys(
    text: str,
    patterns: tuple[re.Pattern[str], ...],
    normalize: Normalize | None = None,
) -> set[str]:
    """Canonical key set captured by *patterns* over *text*."""
    out: set[str] = set()
    for pattern in patterns:
        for raw in pattern.findall(text):
            if normalize is None:
                out.add(raw)
            else:
                out.update(normalize(raw))
    return out


def collect_occurrences(
    display_path: str,
    text: str,
    patterns: tuple[re.Pattern[str], ...],
    normalize: Normalize | None = None,
) -> list[Occurrence]:
    """Line-resolved occurrences (dedup per ``(key, line)``); patterns are
    matched per line, so use line-anchored declaration patterns."""
    out: list[Occurrence] = []
    seen: set[tuple[str, int]] = set()
    for lineno, line in enumerate(text.splitlines(), start=1):
        for pattern in patterns:
            for match in pattern.finditer(line):
                raw = match.group(1)
                keys = [raw] if normalize is None else list(normalize(raw))
                for key in keys:
                    if (key, lineno) in seen:
                        continue
                    seen.add((key, lineno))
                    out.append(Occurrence(key=key, file=display_path, line=lineno))
    return out


def dead_keys(declared: Iterable[Occurrence], consumed: set[str]) -> list[Occurrence]:
    """Declarations whose key never appears in the consumed set."""
    return [occ for occ in declared if occ.key not in consumed]
