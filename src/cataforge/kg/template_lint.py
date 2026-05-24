"""Static checker for KG render templates (Jinja2 + embedded SPARQL).

C5 implementation — the CLI in :mod:`cataforge.cli.kg_cmd` already
declares ``cataforge kg template-lint`` and consumes
:func:`lint_template_roots` / :class:`Finding`.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import jinja2

# ---- rule registry ----

RULE_SPARQL_REQUIRES_ORDER_BY = "SPARQL01-order-by-required"
RULE_JINJA_SYNTAX_VALID = "JINJA01-syntax"
RULE_DEPRECATED_PLACEHOLDER = "TPL01-deprecated-placeholder"

# Deprecated v0.4 doc-gen scaffold placeholders. The .md.j2 successor
# uses SPARQL-driven variables (``{{ kg.get_attr(doc, ...) }}``) so the
# old curly-only tokens should not survive the migration.
_DEPRECATED_PLACEHOLDERS = (
    re.compile(r"\{project\}"),
    re.compile(r"\{ver\}"),
    re.compile(r"\{NNN\}"),
    re.compile(r"\{role\}"),
)

# Detect SPARQL strings embedded inside ``kg.query("...")`` /
# ``sparql("...")`` calls. The inner regex permits single or triple
# quotes, balanced — Jinja templates routinely use both.
_QUERY_CALL_RE = re.compile(
    r"""
    (?:kg\.query|sparql)
    \s*\(\s*
    (?P<q>'''.+?'''|\"\"\".+?\"\"\"|'[^']*'|"[^"]*")
    """,
    re.VERBOSE | re.DOTALL,
)

_ORDER_BY_RE = re.compile(r"\bORDER\s+BY\b", re.IGNORECASE)
_ASK_RE = re.compile(r"\bASK\b", re.IGNORECASE)


@dataclass(frozen=True)
class Finding:
    """A single lint finding."""

    path: Path
    line: int
    rule_id: str
    message: str


def _line_of_char_offset(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _check_jinja_syntax(path: Path, source: str) -> list[Finding]:
    env = jinja2.Environment()  # noqa: S701 — no autoescape needed for lint
    try:
        env.parse(source)
    except jinja2.TemplateSyntaxError as exc:
        return [
            Finding(
                path=path,
                line=exc.lineno or 1,
                rule_id=RULE_JINJA_SYNTAX_VALID,
                message=str(exc.message),
            ),
        ]
    return []


def _check_sparql_order_by(path: Path, source: str) -> list[Finding]:
    findings: list[Finding] = []
    for m in _QUERY_CALL_RE.finditer(source):
        quoted = m.group("q")
        body = quoted.strip("'\"")
        # ASK queries return a single boolean — ORDER BY would be a syntax error.
        if _ASK_RE.search(body):
            continue
        if not _ORDER_BY_RE.search(body):
            findings.append(Finding(
                path=path,
                line=_line_of_char_offset(source, m.start()),
                rule_id=RULE_SPARQL_REQUIRES_ORDER_BY,
                message=(
                    "SPARQL embedded in render templates must include "
                    "ORDER BY for deterministic output (R-07 / R-03)."
                ),
            ))
    return findings


def _check_deprecated_placeholders(path: Path, source: str) -> list[Finding]:
    findings: list[Finding] = []
    for pat in _DEPRECATED_PLACEHOLDERS:
        for m in pat.finditer(source):
            findings.append(Finding(
                path=path,
                line=_line_of_char_offset(source, m.start()),
                rule_id=RULE_DEPRECATED_PLACEHOLDER,
                message=(
                    f"deprecated v0.4 placeholder {m.group()!r}; replace with "
                    "SPARQL-driven Jinja expressions (kg.get_attr / kg.query)."
                ),
            ))
    return findings


def lint_template(path: Path) -> list[Finding]:
    """Run every rule against a single template file."""
    source = path.read_text(encoding="utf-8")
    findings: list[Finding] = []
    findings.extend(_check_jinja_syntax(path, source))
    # Skip downstream rules if syntax already failed — they'd just be noise.
    if any(f.rule_id == RULE_JINJA_SYNTAX_VALID for f in findings):
        return findings
    findings.extend(_check_sparql_order_by(path, source))
    findings.extend(_check_deprecated_placeholders(path, source))
    return findings


def lint_template_roots(
    roots: Sequence[Path],
    *,
    scan_all: bool = False,
) -> list[Finding]:
    """Recursively lint every ``*.md.j2`` under *roots*.

    ``scan_all`` is reserved for the future case where we also want to
    lint legacy ``*.md`` scaffolds; today it has no effect since the
    legacy scaffolds use ``{placeholder}`` syntax that would trigger
    DEPRECATED_PLACEHOLDER findings everywhere."""
    del scan_all  # reserved for future use
    findings: list[Finding] = []
    for root in roots:
        for path in sorted(root.rglob("*.md.j2")):
            findings.extend(lint_template(path))
    return findings
