"""build_doc_index — build chapter-level JSON index for docs/.

Invoked via ``python -m cataforge.domain.docs.indexer`` or ``cataforge docs index``.

Scans docs/**/*.md, parses YAML Front Matter and Markdown heading structure,
produces docs/.doc-index.json for O(1) section lookup.

Index *construction* lives in the leaf :mod:`._index_build` module (builders
re-exported below for the public surface); this module holds the *validation*
surface (orphan / stale / xref / alias / invalid-id checks) plus the CLI entry.
"""

from __future__ import annotations

import argparse
import glob
import os
import sys
from typing import Any

from cataforge.core.errors import ConfigError
from cataforge.core.io import read_json
from cataforge.core.paths import find_project_root
from cataforge.domain.docs._index_build import INDEX_FILENAME as INDEX_FILENAME
from cataforge.domain.docs._index_build import build_aliases as build_aliases
from cataforge.domain.docs._index_build import build_document_entry as build_document_entry
from cataforge.domain.docs._index_build import build_full_index as build_full_index
from cataforge.domain.docs._index_build import build_xref as build_xref
from cataforge.domain.docs._index_build import update_single_doc as update_single_doc
from cataforge.domain.docs._index_build import write_index as write_index
from cataforge.utils.common import ensure_utf8
from cataforge.utils.patterns import DOC_ID_RE


def _load_docignore_patterns(docs_dir: str) -> list[str]:
    """Read ``docs/.docignore`` exclusion globs (gitignore-flavoured subset).

    One pattern per line; ``#`` comments and blank lines are skipped. Patterns
    match against the doc path relative to ``docs/`` (posix). A trailing ``/``
    means "this directory and everything under it"; otherwise the line is an
    ``fnmatch`` glob whose ``*`` also crosses ``/``.
    """
    path = os.path.join(docs_dir, ".docignore")
    if not os.path.isfile(path):
        return []
    patterns: list[str] = []
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            patterns.append(line.replace("\\", "/"))
    return patterns


def _docignore_matches(rel_under_docs: str, patterns: list[str]) -> bool:
    from fnmatch import fnmatchcase

    for pat in patterns:
        if pat.endswith("/"):
            base = pat[:-1]
            if rel_under_docs == base or rel_under_docs.startswith(base + "/"):
                return True
        elif fnmatchcase(rel_under_docs, pat):
            return True
    return False


def _scan_docs_orphans(project_root: str) -> tuple[list[str], list[str]]:
    """Walk ``docs/**/*.md`` once, splitting un-ingestable files into
    ``(orphans, ignored)``.

    A file is un-ingestable when it is missing YAML front matter, or its ``id``
    field is empty/contains a ``{...}`` template placeholder — such files are
    skipped by :func:`build_full_index` and never appear in ``.doc-index.json``,
    so ``cataforge docs load`` / ``--with-deps`` / agent prose cannot resolve
    them. ``orphans`` are surfaced as failures; ``ignored`` are un-ingestable
    files a ``docs/.docignore`` pattern claims as intentional (published prose
    that is not an SDLC artefact), reported but not gating.

    Files under ``.archive/`` are excluded outright — intentional snapshots of
    historical NAV-INDEX content kept by ``cataforge docs migrate-nav``.
    """
    docs_dir = os.path.join(project_root, "docs")
    if not os.path.isdir(docs_dir):
        return [], []
    patterns = _load_docignore_patterns(docs_dir)
    orphans: list[str] = []
    ignored: list[str] = []
    for md_path in sorted(glob.glob(os.path.join(docs_dir, "**", "*.md"), recursive=True)):
        rel_path = os.path.relpath(md_path, project_root)
        rel_posix = rel_path.replace("\\", "/")
        if "/.archive/" in rel_posix or rel_posix.startswith("docs/.archive/"):
            continue
        doc_id, entry = build_document_entry(md_path, rel_path)
        if doc_id and entry:
            continue
        rel_under_docs = rel_posix[len("docs/") :]
        if patterns and _docignore_matches(rel_under_docs, patterns):
            ignored.append(rel_posix)
        else:
            orphans.append(rel_posix)
    return orphans, ignored


def find_orphan_docs(project_root: str) -> list[str]:
    """Return rel-paths of ``docs/**/*.md`` the indexer cannot ingest, minus
    any a ``docs/.docignore`` pattern excludes. See :func:`_scan_docs_orphans`.
    """
    return _scan_docs_orphans(project_root)[0]


def validate_docs(project_root: str) -> dict[str, list]:
    """Run all docs validations and return a unified result.

    Single source of truth for both ``cataforge docs validate`` and
    ``cataforge doctor`` — enhancements (e.g. cross-ref resolution) added here
    flow into both call sites without duplication.
    """
    orphans, ignored = _scan_docs_orphans(project_root)
    return {
        "orphans": orphans,
        "ignored": ignored,
        "stale": find_stale_index_entries(project_root),
        "xref_errors": find_xref_errors(project_root),
        "alias_conflicts": find_alias_conflicts(project_root),
        "invalid_ids": find_invalid_doc_ids(project_root),
        "stale_deps": find_stale_deps(project_root),
    }


def format_stale_deps_warning(stale_deps: list[dict[str, str]]) -> list[str]:
    """Render the stale-dependency WARN block shared by ``docs validate`` and
    ``doctor``.

    Returns an empty list when there are no stale deps. Stale deps are a
    warning, not a gating failure, so both call sites display these lines
    without counting them toward an exit-code tally.
    """
    if not stale_deps:
        return []
    lines = [
        f"WARN · {len(stale_deps)} stale dependency(ies) — "
        "upstream content changed since downstream was written:"
    ]
    for sd in stale_deps:
        lines.append(
            f"  - {sd['doc_id']} depends on {sd['upstream_id']} "
            f"(pinned={sd['pinned_hash']}, current={sd['current_hash']})"
        )
    return lines


def find_stale_deps(project_root: str) -> list[dict[str, str]]:
    """Return deps whose upstream ``content_hash`` changed since last index build.

    Each document with a ``dep_hashes`` snapshot is compared against its
    upstream documents' current ``content_hash``. A mismatch signals that
    the upstream was revised after the downstream was written against it —
    the downstream may need updating to reflect the upstream changes.
    """
    index_path = os.path.join(project_root, "docs", INDEX_FILENAME)
    if not os.path.isfile(index_path):
        return []
    try:
        index = read_json(index_path)
    except ConfigError:
        return []

    stale: list[dict[str, str]] = []
    documents = index.get("documents") or {}

    for doc_id, entry in documents.items():
        dep_hashes = entry.get("dep_hashes") or {}
        if not dep_hashes:
            continue
        for upstream_id, pinned_hash in dep_hashes.items():
            upstream = documents.get(upstream_id)
            if not upstream:
                continue
            current_hash = upstream.get("content_hash", "")
            if pinned_hash and current_hash and pinned_hash != current_hash:
                stale.append({
                    "doc_id": doc_id,
                    "file_path": entry.get("file_path", ""),
                    "upstream_id": upstream_id,
                    "pinned_hash": pinned_hash,
                    "current_hash": current_hash,
                })
    return stale


def find_invalid_doc_ids(project_root: str) -> list[dict[str, str]]:
    """Return doc_ids / aliases whose slug violates ``DOC_ID_RE``.

    The loader's ``REF_RE`` only accepts ``[\\w-]+`` in the doc_id position,
    so any id or alias containing ``.`` (e.g. version strings like
    ``0.1.0``) silently breaks every cross-reference targeting it.
    Reporting them here turns the silent failure into a hard validate
    error so doc-gen template misuse surfaces immediately.
    """
    index_path = os.path.join(project_root, "docs", INDEX_FILENAME)
    if not os.path.isfile(index_path):
        return []
    try:
        index = read_json(index_path)
    except ConfigError:
        return []

    errors: list[dict[str, str]] = []
    documents = index.get("documents") or {}
    for doc_id, entry in documents.items():
        rel_path = entry.get("file_path", "")
        if not DOC_ID_RE.match(doc_id):
            errors.append({
                "kind": "doc_id", "value": doc_id, "file_path": rel_path,
                "reason": (
                    f"非法 doc_id {doc_id!r}: 仅允许 [A-Za-z0-9_-]，"
                    f"含 '.' 等字符会让 REF_RE 拒绝任何指向本文档的引用"
                ),
            })
        for alias in entry.get("aliases") or []:
            if not isinstance(alias, str) or not DOC_ID_RE.match(alias):
                errors.append({
                    "kind": "alias", "value": str(alias), "file_path": rel_path,
                    "reason": (
                        f"非法 alias {alias!r} (claimed by {doc_id!r}): "
                        f"仅允许 [A-Za-z0-9_-]"
                    ),
                })
    return errors


def find_alias_conflicts(project_root: str) -> list[dict[str, Any]]:
    """Return frontmatter alias conflicts recorded in the index.

    Two docs claiming the same alias, or an alias that shadows an existing
    doc_id, are first-claim-wins at index time and recorded here so the
    second claim's silent no-op surfaces at validate time.
    """
    index_path = os.path.join(project_root, "docs", INDEX_FILENAME)
    if not os.path.isfile(index_path):
        return []
    try:
        index = read_json(index_path)
    except ConfigError:
        return []
    conflicts = index.get("alias_conflicts") or []
    return list(conflicts) if isinstance(conflicts, list) else []


def find_xref_errors(project_root: str) -> list[dict[str, str]]:
    """Return cross-reference resolution errors for all docs in the index.

    Each entry's frontmatter ``deps:`` is parsed; every ``doc_id#§N[.item]``
    is resolved against the index (with prefix fallback + aliases). Refs that
    cannot resolve, or that resolve ambiguously to multiple docs, are reported
    here so the failure surfaces at validation time instead of at
    ``cataforge docs load`` time.
    """
    from cataforge.domain.docs.index_ops import (
        AmbiguousRefError,
        LoadSectionError,
        _lookup_in_index,
        parse_ref,
    )

    index_path = os.path.join(project_root, "docs", INDEX_FILENAME)
    if not os.path.isfile(index_path):
        return []
    try:
        index = read_json(index_path)
    except ConfigError:
        return []

    errors: list[dict[str, str]] = []
    documents = index.get("documents") or {}
    for doc_id, entry in documents.items():
        rel_path = entry.get("file_path", "")
        deps = entry.get("deps") or []
        if not isinstance(deps, list):
            continue
        for dep in deps:
            if not isinstance(dep, str) or "#§" not in dep:
                continue
            try:
                ref_doc, section_path, item_id = parse_ref(dep)
            except LoadSectionError as e:
                errors.append({"doc_id": doc_id, "file_path": rel_path,
                               "ref": dep, "reason": f"parse error: {e}"})
                continue
            try:
                hit = _lookup_in_index(index, ref_doc, section_path, item_id)
            except AmbiguousRefError as e:
                errors.append({"doc_id": doc_id, "file_path": rel_path,
                               "ref": dep, "reason": str(e)})
                continue
            if hit is None:
                errors.append({
                    "doc_id": doc_id, "file_path": rel_path, "ref": dep,
                    "reason": (
                        f"未找到引用目标 {ref_doc!r}"
                        "（短别名？参考 frontmatter aliases:）"
                    ),
                })
    return errors


def find_stale_index_entries(project_root: str) -> list[tuple[str, str]]:
    """Return ``(doc_id, file_path)`` pairs whose ``file_path`` is gone from disk.

    Symmetric to :func:`find_orphan_docs`: that function catches files
    on disk the indexer can't read; this one catches index entries that
    survived a manual ``rm`` / rename. Both are silent failure modes
    pre-v0.1.14 — the loader returned "ref not found" instead of
    pointing at the stale entry.
    """
    index_path = os.path.join(project_root, "docs", INDEX_FILENAME)
    if not os.path.isfile(index_path):
        return []
    try:
        index = read_json(index_path)
    except ConfigError:
        return []
    stale: list[tuple[str, str]] = []
    for doc_id, entry in (index.get("documents") or {}).items():
        rel = entry.get("file_path", "")
        if not rel:
            continue
        abs_path = os.path.join(project_root, rel)
        if not os.path.isfile(abs_path):
            stale.append((doc_id, rel))
    return stale


def main(argv: list[str] | None = None) -> int:
    ensure_utf8()
    parser = argparse.ArgumentParser(
        description="CataForge build_doc_index — build chapter-level JSON index",
    )
    parser.add_argument("--project-root", default=None)
    parser.add_argument("--doc-file", default=None, help="Incremental update for a single file")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero if any docs/**/*.md is missing YAML front matter "
             "and gets skipped (useful as a CI gate).",
    )
    args = parser.parse_args(argv)

    project_root = args.project_root or str(find_project_root())

    if args.doc_file:
        index = update_single_doc(project_root, args.doc_file)
    else:
        index = build_full_index(project_root)

    out_path = write_index(index, project_root)
    doc_count = len(index.get("documents", {}))
    xref_count = len(index.get("xref", {}))
    print(f"索引已写入: {out_path}")
    print(f"文档数: {doc_count}, 交叉引用条目: {xref_count}")

    # Orphan scan is a tree-wide property — run it on every invocation,
    # incremental or not. Previously the scan was skipped when --doc-file
    # was set, which made --strict a silent no-op for incremental updates
    # (e.g. PostToolUse hook scenarios) and let bad front matter slip past
    # the gate as long as the offending file wasn't the one being updated.
    orphans = find_orphan_docs(project_root)
    if orphans:
        print(
            f"[WARN] {len(orphans)} 个 docs/**/*.md 文件缺少 YAML "
            f"front matter (id 字段) — 已被 indexer 跳过：",
            file=sys.stderr,
        )
        for rel in orphans:
            print(f"  - {rel}", file=sys.stderr)
        print(
            "  → 补 front matter (id/doc_type/...) 后重跑，或确认这些"
            "文件不应出现在 docs/ 下。",
            file=sys.stderr,
        )
        # Same orphan list also FAILS `cataforge doctor` (orphan count
        # feeds doctor's exit gate, see cli/doctor_cmd.py:_check_orphan_docs),
        # so a missing front matter is already a hard CI gate even without
        # --strict — surface that explicitly so users don't think this is
        # advisory-only.
        print(
            "  注意：同样的 orphan 也会让 `cataforge doctor` 退出非零，"
            "进而 FAIL 任何把 doctor 接入 CI 的工作流（见 "
            ".github/workflows/test.yml）。--strict 只控制本命令是否 FAIL。",
            file=sys.stderr,
        )
        if args.strict:
            return 3

    # Reverse-orphan scan: index entries pointing at deleted/renamed
    # files. The fresh index we just wrote is consistent by construction,
    # so this only matters if `--doc-file` was used (incremental: other
    # entries weren't refreshed).
    if args.doc_file:
        stale = find_stale_index_entries(project_root)
        if stale:
            print(
                f"[WARN] {len(stale)} 个 .doc-index.json 条目指向磁盘"
                f"已不存在的文件：",
                file=sys.stderr,
            )
            for doc_id, rel in stale:
                print(f"  - {doc_id} → {rel}", file=sys.stderr)
            print(
                "  → 跑 `cataforge docs index`（不带 --doc-file）做全量"
                "重建以清掉这些条目。",
                file=sys.stderr,
            )
            if args.strict:
                return 3

    return 0


if __name__ == "__main__":
    sys.exit(main())
