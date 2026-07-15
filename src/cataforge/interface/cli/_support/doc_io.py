"""Shared CLI orchestration for the document read/index family.

``context read|index|validate`` (canonical) and the ``docs`` deprecated
aliases both call these helpers, so the formatting/exit-code policy lives
in one place and neither command module imports the other.
"""

from __future__ import annotations

import json
import os
from typing import Any

import click

from cataforge.core.errors import CataforgeError
from cataforge.interface.cli._support.helpers import resolve_root


def _raise_on_nonzero(code: int, command_label: str) -> None:
    """Translate a non-zero return code from a sub-CLI main() into a
    :class:`CataforgeError` so the user sees the unified ``Error: …`` prefix."""
    if code == 0:
        return
    err = CataforgeError(f"`{command_label}` failed (exit code {code}).")
    err.exit_code = code
    raise err


def run_load(
    refs: tuple[str, ...],
    project_root: str | None,
    json_output: bool,
    with_deps: bool,
    budget: int | None,
    *,
    command_label: str,
) -> None:
    """Load Markdown sections by ``doc_id#§N`` references and format the output.

    Shared body behind ``context read`` and the ``docs load`` deprecated alias.
    """
    from cataforge.application.context.read import load_sections
    from cataforge.core.paths import find_project_root
    from cataforge.domain.docs.loader import (
        _emit_stale_warning,
        _index_lookup_or_none,
        _load_index,
    )

    root = project_root or str(find_project_root())
    _emit_stale_warning(root)

    result = load_sections(list(refs), root, with_deps=with_deps, budget=budget)

    if result.dep_refs:
        click.echo(
            f"[DEPS] resolved {len(result.dep_refs)} dependency ref(s): "
            f"{' '.join(result.dep_refs)}",
            err=True,
        )
    if result.deferred:
        click.echo(
            f"[DEFERRED] {len(result.deferred)} ref(s) exceed budget {budget}: "
            f"{' '.join(result.deferred)}",
            err=True,
        )

    if json_output:
        index = _load_index(root)
        out: list[dict[str, Any]] = []
        for ref, content in result.successes:
            entry = _index_lookup_or_none(index, ref) or {}
            out.append(
                {
                    "ref": ref,
                    "status": "ok",
                    "content": content,
                    "file_path": entry.get("file_path"),
                    "line_start": entry.get("line_start"),
                    "line_end": entry.get("line_end"),
                }
            )
        out.extend({"ref": ref, "status": "error", "error": msg} for ref, msg in result.errors)
        out.extend({"ref": ref, "status": "deferred"} for ref in result.deferred)
        click.echo(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        for ref, content in result.successes:
            click.echo(f"=== {ref} ===")
            click.echo(content)
            click.echo()
        for ref, msg in result.errors:
            click.echo(f"[ERROR] {ref}: {msg}", err=True)

    if result.errors:
        err = CataforgeError(f"`{command_label}` failed to load {len(result.errors)} ref(s).")
        err.exit_code = 2
        raise err


def run_index(
    project_root: str | None,
    doc_file: str | None,
    strict: bool,
    *,
    dry_run: bool = False,
    command_label: str,
) -> None:
    """Build or update the chapter-level JSON index ``docs/.doc-index.json``.

    Shared body behind ``context index`` and the ``docs index`` deprecated alias.
    With ``dry_run`` the build/write is skipped and the call becomes the
    read-only integrity gate — the single implementation behind
    ``context validate`` — so the two verdicts can never diverge.
    """
    if dry_run:
        run_validate(project_root)
        return

    from cataforge.domain.docs.indexer import main as indexer_main

    argv: list[str] = []
    if project_root:
        argv.extend(["--project-root", str(project_root)])
    if doc_file:
        argv.extend(["--doc-file", doc_file])
    if strict:
        argv.append("--strict")
    _raise_on_nonzero(indexer_main(argv), command_label)


def _emit_validate_failures(
    orphans: list[str],
    stale: list[tuple[str, str]],
    xref_errors: list[dict[str, str]],
    alias_conflicts: list[dict[str, str]],
    invalid_ids: list[dict[str, str]],
) -> None:
    """Echo per-category FAIL lines for ``validate``."""
    if orphans:
        click.echo(f"FAIL · {len(orphans)} orphan(s) — missing YAML front matter:", err=True)
        for rel in orphans:
            click.echo(f"  - {rel}", err=True)
        click.echo(
            "  hint: 面向读者的非 SDLC 文档可在 docs/.docignore 声明豁免 glob（一行一个）",
            err=True,
        )

    if stale:
        click.echo(f"FAIL · {len(stale)} stale index entry(ies):", err=True)
        for doc_id, rel in stale:
            click.echo(f"  - {doc_id} → {rel}", err=True)

    if xref_errors:
        click.echo(f"FAIL · {len(xref_errors)} cross-reference error(s):", err=True)
        for e in xref_errors:
            click.echo(
                f"  - {e['doc_id']} ({e['file_path']}) → {e['ref']}: {e['reason']}", err=True
            )

    if alias_conflicts:
        click.echo(f"FAIL · {len(alias_conflicts)} alias conflict(s):", err=True)
        for c in alias_conflicts:
            click.echo(f"  - {c['alias']} (claimed by {c['claimed_by']}): {c['reason']}", err=True)

    if invalid_ids:
        click.echo(
            f"FAIL · {len(invalid_ids)} invalid id(s) — slug must match [A-Za-z0-9_-]+:",
            err=True,
        )
        for e in invalid_ids:
            click.echo(
                f"  - [{e['kind']}] {e['value']!r} ({e['file_path']}): {e['reason']}",
                err=True,
            )


def run_validate(project_root: str | None) -> None:
    """Validate ``docs/.doc-index.json`` integrity without writing to disk.

    Shared body behind ``context validate`` and the ``docs validate`` alias.
    """
    from cataforge.domain.docs.indexer import (
        INDEX_FILENAME,
        format_stale_deps_warning,
        validate_docs,
    )

    root = project_root or str(resolve_root())
    index_path = os.path.join(root, "docs", INDEX_FILENAME)
    if not os.path.isfile(index_path):
        click.echo(
            f"docs/{INDEX_FILENAME} not found — nothing to validate. "
            "Run `cataforge context index` first if you intend to opt into "
            "CataForge-managed docs.",
            err=True,
        )
        err = CataforgeError(f"docs/{INDEX_FILENAME} not found at {root}")
        err.exit_code = 2
        raise err

    result = validate_docs(root)
    orphans = result["orphans"]
    ignored = result.get("ignored", [])
    stale = result["stale"]
    xref_errors = result["xref_errors"]
    alias_conflicts = result["alias_conflicts"]
    invalid_ids = result.get("invalid_ids", [])
    stale_deps = result.get("stale_deps", [])

    if ignored:
        click.echo(f"{len(ignored)} doc(s) excluded by docs/.docignore")

    if not orphans and not stale and not xref_errors and not alias_conflicts and not invalid_ids:
        summary = (
            "OK · 0 orphans · 0 stale entries · 0 xref errors · 0 alias conflicts · 0 invalid ids"
        )
        if stale_deps:
            summary += f" · {len(stale_deps)} stale dep(s)"
        click.echo(summary)
        for line in format_stale_deps_warning(stale_deps):
            click.echo(line, err=True)
        return

    _emit_validate_failures(orphans, stale, xref_errors, alias_conflicts, invalid_ids)

    for line in format_stale_deps_warning(stale_deps):
        click.echo(line, err=True)

    err = CataforgeError(
        f"docs validate failed ({len(orphans)} orphan, {len(stale)} stale, "
        f"{len(xref_errors)} xref, {len(alias_conflicts)} alias, "
        f"{len(invalid_ids)} invalid-id)",
    )
    err.exit_code = 3
    raise err
