"""Routed context-read facade + the ``cataforge docs load`` CLI orchestration.

These wrap the :class:`FidelityRouter` so callers (the CLI, other
application services) get strategy-aware reads without knowing which
backend served them. The doc-only primitives still live in
``domain.docs.loader``; here they are composed with the graph backend.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from cataforge.application.context.router import build_router
from cataforge.core.paths import find_project_root
from cataforge.domain.docs.index_ops import LoadSectionError
from cataforge.domain.docs.loader import (
    _emit_stale_warning,
    _index_lookup_or_none,
    _load_index,
)
from cataforge.utils.common import ensure_utf8


def extract(ref: str, project_root: str, file_cache: dict[str, Any] | None = None) -> str:
    """Strategy-routed read of a single ``doc_id#§N[.item]`` reference."""
    return build_router(project_root).read_section(ref, project_root, file_cache=file_cache)


def extract_batch(
    refs: list[str], project_root: str
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    successes: list[tuple[str, str]] = []
    errors: list[tuple[str, str]] = []
    file_cache: dict[str, list[str]] = {}
    router = build_router(project_root)
    for ref in refs:
        try:
            successes.append((ref, router.read_section(ref, project_root, file_cache=file_cache)))
        except LoadSectionError as e:
            errors.append((ref, str(e)))
    return successes, errors


def plan_load(refs: list[str], project_root: str, token_budget: int) -> tuple[list[str], list[str]]:
    return build_router(project_root).plan_load(refs, project_root, token_budget)


def resolve_deps(ref: str, project_root: str, max_depth: int = 2) -> list[str]:
    return build_router(project_root).deps(ref, project_root, max_depth)


def main(argv: list[str] | None = None) -> int:
    ensure_utf8()
    parser = argparse.ArgumentParser(
        description="CataForge load_section — extract Markdown sections by reference",
    )
    parser.add_argument("refs", nargs="+", help="doc_id#§N references")
    parser.add_argument("--project-root", default=None)
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Emit a JSON array instead of '=== <ref> ===' separators",
    )
    parser.add_argument(
        "--with-deps",
        action="store_true",
        help="Also load dependency refs declared in .doc-index.json (depth ≤ 2)",
    )
    parser.add_argument(
        "--budget",
        type=int,
        default=None,
        metavar="TOKENS",
        help="Token budget; refs exceeding budget are listed under [DEFERRED] on stderr",
    )
    args = parser.parse_args(argv)

    project_root = args.project_root or str(find_project_root())

    _emit_stale_warning(project_root)

    refs: list[str] = list(args.refs)

    if args.with_deps:
        seen = set(refs)
        expanded: list[str] = list(refs)
        for ref in refs:
            for dep in resolve_deps(ref, project_root):
                if dep not in seen:
                    seen.add(dep)
                    expanded.append(dep)
        if expanded != refs:
            extras = expanded[len(refs) :]
            print(
                f"[DEPS] resolved {len(extras)} dependency ref(s): {' '.join(extras)}",
                file=sys.stderr,
            )
        refs = expanded

    deferred: list[str] = []
    if args.budget is not None:
        loadable, deferred = plan_load(refs, project_root, args.budget)
        refs = loadable
        if deferred:
            print(
                f"[DEFERRED] {len(deferred)} ref(s) exceed budget {args.budget}: "
                f"{' '.join(deferred)}",
                file=sys.stderr,
            )

    successes, errors = extract_batch(refs, project_root)

    if args.json_output:
        index = _load_index(project_root)
        out: list[dict[str, Any]] = []
        for ref, content in successes:
            entry = _index_lookup_or_none(index, ref)
            out.append(
                {
                    "ref": ref,
                    "status": "ok",
                    "content": content,
                    "file_path": (entry or {}).get("file_path"),
                    "line_start": (entry or {}).get("line_start"),
                    "line_end": (entry or {}).get("line_end"),
                }
            )
        for ref, msg in errors:
            out.append({"ref": ref, "status": "error", "error": msg})
        for ref in deferred:
            out.append({"ref": ref, "status": "deferred"})
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        for ref, content in successes:
            print(f"=== {ref} ===")
            print(content)
            print()

        if errors:
            for ref, msg in errors:
                print(f"[ERROR] {ref}: {msg}", file=sys.stderr)

    return 2 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
