"""CataForge load_section — extract Markdown sections by doc_id#§N references.

Invoked via ``python -m cataforge.domain.docs.loader`` or ``cataforge docs load``.

Supported reference formats:
    doc_id#§N              top-level section (e.g. prd#§2)
    doc_id#§N.M            sub-section (e.g. prd#§1.1)
    doc_id#§N.ITEM-xxx     item (e.g. prd#§2.F-003)

Exit codes:
    0  all refs extracted successfully
    2  at least one ref failed
"""

from __future__ import annotations

import glob
import os
import sys
import threading
from datetime import UTC, datetime
from typing import Any

from cataforge.core.errors import ConfigError
from cataforge.core.io import read_json
from cataforge.domain.docs._index_build import _content_hash
from cataforge.domain.docs._loader_kg import (
    _entity_id_to_ref as _entity_id_to_ref,
)
from cataforge.domain.docs.index_ops import (
    _DOC_TYPE_MAP_CACHE as _DOC_TYPE_MAP_CACHE,
)
from cataforge.domain.docs.index_ops import (  # re-export: shared index primitives
    DEFAULT_DOC_TYPE_MAP as DEFAULT_DOC_TYPE_MAP,
)
from cataforge.domain.docs.index_ops import (
    AmbiguousRefError as AmbiguousRefError,
)
from cataforge.domain.docs.index_ops import (
    DocResolveError as DocResolveError,
)
from cataforge.domain.docs.index_ops import (
    LoadSectionError as LoadSectionError,
)
from cataforge.domain.docs.index_ops import (
    RefParseError as RefParseError,
)
from cataforge.domain.docs.index_ops import (
    SectionNotFoundError as SectionNotFoundError,
)
from cataforge.domain.docs.index_ops import (
    _get_doc_type_map as _get_doc_type_map,
)
from cataforge.domain.docs.index_ops import (
    _load_doc_type_map as _load_doc_type_map,
)
from cataforge.domain.docs.index_ops import (
    _lookup_in_index as _lookup_in_index,
)
from cataforge.domain.docs.index_ops import (
    _resolve_doc_entry as _resolve_doc_entry,
)
from cataforge.domain.docs.index_ops import (
    parse_ref as parse_ref,
)
from cataforge.utils.md_parse import iter_markdown_headings
from cataforge.utils.patterns import HEADING_RE

# ---------------------------------------------------------------------------
# doc_id → doc_type mapping
#
# Built-in defaults cover the standard CataForge document set. Downstream
# projects extend or override via ``.cataforge/framework.json``:
#
#     { "docs": { "doc_types": { "<doc_id>": "<sub-directory under docs/>" } } }
#
# Custom entries are merged on top of the defaults; pass an empty mapping to
# replace all defaults.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Index cache
# ---------------------------------------------------------------------------

_INDEX_CACHE: dict[str, Any] | None = None
_INDEX_CACHE_ROOT: str | None = None
_INDEX_CACHE_LOCK = threading.Lock()
_INDEX_FILENAME = ".doc-index.json"
_STALE_DAYS_WARN = 7


def _load_index(project_root: str) -> dict[str, Any] | None:
    """Load the chapter index, per-root cached to avoid leakage between roots."""
    global _INDEX_CACHE, _INDEX_CACHE_ROOT
    with _INDEX_CACHE_LOCK:
        if _INDEX_CACHE is not None and project_root == _INDEX_CACHE_ROOT:
            return _INDEX_CACHE
        index_path = os.path.join(project_root, "docs", _INDEX_FILENAME)
        if not os.path.isfile(index_path):
            _INDEX_CACHE = None
            _INDEX_CACHE_ROOT = project_root
            return None
        try:
            _INDEX_CACHE = read_json(index_path)
            _INDEX_CACHE_ROOT = project_root
            return _INDEX_CACHE
        except ConfigError:
            return None


def clear_index_cache() -> None:
    global _INDEX_CACHE, _INDEX_CACHE_ROOT
    with _INDEX_CACHE_LOCK:
        _INDEX_CACHE = None
        _INDEX_CACHE_ROOT = None


def _is_stale(file_path: str, content_hash: str | None, generated_at: str | None) -> bool:
    """Decide whether the indexed slice for ``file_path`` can still be trusted.

    Prefers a content-hash comparison: git checkout/merge/pull rewrites
    working-tree mtimes without changing bytes, so an mtime heuristic flags a
    byte-identical file as stale on every branch operation. Falls back to the
    mtime-vs-``generated_at`` comparison only for indexes built before
    per-document ``content_hash`` was recorded.
    """
    if content_hash:
        try:
            with open(file_path) as f:
                return _content_hash(f.read()) != content_hash
        except OSError:
            return True
    if not generated_at:
        return True
    try:
        file_mtime = os.path.getmtime(file_path)
        gen_dt = datetime.fromisoformat(generated_at)
        file_dt = datetime.fromtimestamp(file_mtime, tz=UTC)
        return file_dt > gen_dt
    except (ValueError, OSError):
        return True


def _index_age_days(generated_at: str | None) -> float | None:
    if not generated_at:
        return None
    try:
        gen_dt = datetime.fromisoformat(generated_at)
        return (datetime.now(UTC) - gen_dt).total_seconds() / 86400.0
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# File resolution
# ---------------------------------------------------------------------------


def resolve_file(
    doc_id: str, project_root: str, section_path: str = "", item_id: str | None = None
) -> str:
    doc_type_map = _get_doc_type_map(project_root)
    if doc_id not in doc_type_map:
        raise DocResolveError(f"未知的 doc_id: {doc_id!r}")
    doc_type = doc_type_map[doc_id]
    doc_dir = os.path.join(project_root, "docs", doc_type)
    if not os.path.isdir(doc_dir):
        raise DocResolveError(f"文档目录不存在: {doc_dir}")

    candidates: list[str] = []
    for path in sorted(glob.glob(os.path.join(doc_dir, f"{doc_id}-*.md"))):
        if path not in candidates:
            candidates.append(path)
    if not candidates:
        raise DocResolveError(f"在 {doc_dir} 下未找到匹配 {doc_id}-*.md 的文件")
    if len(candidates) == 1:
        return candidates[0]

    for path in candidates:
        try:
            with open(path) as f:
                content = f.read()
        except OSError:
            continue
        if _find_heading_line(content, section_path, item_id) is not None:
            return path
    return candidates[0]


def _find_heading_line(
    content: str, section_path: str, item_id: str | None
) -> tuple[int, int] | None:
    for i, level, title in iter_markdown_headings(content):
        title = title.strip()

        if item_id:
            if title == item_id:
                return i, level
            if title.startswith(item_id):
                nxt = title[len(item_id) : len(item_id) + 1]
                if nxt in ("", ":", " ", "\t"):
                    return i, level
        elif "." in section_path:
            if title == section_path or (
                title.startswith(section_path)
                and title[len(section_path) : len(section_path) + 1] in ("", " ", ".", "\t")
            ):
                return i, level
        else:
            if title == section_path or (
                title.startswith(section_path)
                and title[len(section_path) : len(section_path) + 1] in ("", ".", " ", "\t")
            ):
                return i, level
    return None


def _extract_section_from_lines(lines: list[str], start_idx: int, level: int) -> str:
    result = [lines[start_idx]]
    for i in range(start_idx + 1, len(lines)):
        m = HEADING_RE.match(lines[i])
        if m and len(m.group(1)) <= level:
            break
        result.append(lines[i])
    while result and result[-1].strip() == "":
        result.pop()
    return "\n".join(result)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def extract(
    ref: str,
    project_root: str,
    file_cache: dict[str, list[str]] | None = None,
) -> str:
    """File/index-backed section read — the ``doc`` backend primitive.

    Resolves ``ref`` through ``.doc-index.json`` when fresh, else falls
    back to a Markdown heading scan. Raises ``SectionNotFoundError`` when
    the section genuinely cannot be located. Strategy-aware routing
    (graph vs file) lives one layer up in
    :mod:`cataforge.application.context`; this function never consults the
    knowledge graph. ``file_cache`` is an optional ``{absolute_file_path:
    lines}`` map used to avoid duplicate reads across many refs.
    """
    doc_id, section_path, item_id = parse_ref(ref)

    index = _load_index(project_root)
    if index:
        entry = _lookup_in_index(index, doc_id, section_path, item_id)
        if entry:
            abs_path = os.path.join(project_root, entry["file_path"])
            if os.path.isfile(abs_path):
                if not _is_stale(abs_path, entry.get("content_hash"), index.get("generated_at")):
                    lines = _read_lines_cached(abs_path, file_cache)
                    start = entry["line_start"] - 1
                    end = entry["line_end"]
                    result = "".join(lines[start:end]).rstrip()
                    if result:
                        return result
                # Stale slice: the file changed, but the index already named the
                # backing file. Re-scan it by heading rather than re-deriving the
                # path from the doc_type map, which cannot resolve a frontmatter
                # id (e.g. a split volume's ``prd-keel``).
                rescanned = _read_splitlines_cached(abs_path, file_cache)
                found = _find_heading_line_in_lines(rescanned, section_path, item_id)
                if found is not None:
                    start_idx, level = found
                    return _extract_section_from_lines(rescanned, start_idx, level)

    file_path = resolve_file(doc_id, project_root, section_path, item_id)
    splitlines = _read_splitlines_cached(file_path, file_cache)
    found = _find_heading_line_in_lines(splitlines, section_path, item_id)
    if found is None:
        target = f"§{section_path}" + (f".{item_id}" if item_id else "")
        raise SectionNotFoundError(f"在 {file_path} 中未找到 {target}")
    start_idx, level = found
    return _extract_section_from_lines(splitlines, start_idx, level)


def _read_lines_cached(abs_path: str, file_cache: dict[str, list[str]] | None) -> list[str]:
    if file_cache is not None and abs_path in file_cache:
        return file_cache[abs_path]
    with open(abs_path) as f:
        lines = f.readlines()
    if file_cache is not None:
        file_cache[abs_path] = lines
    return lines


def _read_splitlines_cached(file_path: str, file_cache: dict[str, list[str]] | None) -> list[str]:
    """Like ``_read_lines_cached`` but returns ``str.splitlines()`` form (no trailing newlines).

    Stored under a separate key suffix so the two read modes do not collide.
    """
    cache_key = file_path + "::splitlines"
    if file_cache is not None and cache_key in file_cache:
        return file_cache[cache_key]
    with open(file_path) as f:
        content = f.read()
    splitlines = content.splitlines()
    if file_cache is not None:
        file_cache[cache_key] = splitlines
    return splitlines


def _find_heading_line_in_lines(
    lines: list[str], section_path: str, item_id: str | None
) -> tuple[int, int] | None:
    """Variant of ``_find_heading_line`` that takes pre-split lines (cached)."""
    return _find_heading_line("\n".join(lines), section_path, item_id)


def extract_batch(
    refs: list[str], project_root: str
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    successes: list[tuple[str, str]] = []
    errors: list[tuple[str, str]] = []
    file_cache: dict[str, list[str]] = {}
    for ref in refs:
        try:
            content = extract(ref, project_root, file_cache=file_cache)
            successes.append((ref, content))
        except LoadSectionError as e:
            errors.append((ref, str(e)))
    return successes, errors


def plan_load(refs: list[str], project_root: str, token_budget: int) -> tuple[list[str], list[str]]:
    """Index-backed budgeted plan-load — the ``doc`` backend primitive."""
    index = _load_index(project_root)
    loadable: list[str] = []
    deferred: list[str] = []
    remaining = token_budget
    for ref in refs:
        est = 200
        if index:
            try:
                doc_id, section_path, item_id = parse_ref(ref)
                entry = _lookup_in_index(index, doc_id, section_path, item_id)
                if entry:
                    est = entry.get("est_tokens", 200)
            except LoadSectionError:
                pass
        if est <= remaining:
            loadable.append(ref)
            remaining -= est
        else:
            deferred.append(ref)
    return loadable, deferred


def resolve_deps(ref: str, project_root: str, max_depth: int = 2) -> list[str]:
    """Index-backed transitive dependency walk — the ``doc`` backend primitive."""
    index = _load_index(project_root)
    if not index:
        return []

    visited: set[str] = set()
    result: list[str] = []

    def _resolve(r: str, depth: int) -> None:
        if depth > max_depth or r in visited:
            return
        visited.add(r)
        try:
            doc_id, section_path, item_id = parse_ref(r)
        except LoadSectionError:
            return
        entry = _lookup_in_index(index, doc_id, section_path, item_id)
        if not entry:
            return
        deps = entry.get("deps", [])
        if isinstance(deps, list):
            for dep_ref in deps:
                if dep_ref not in visited:
                    _resolve(dep_ref, depth + 1)
                    result.append(dep_ref)

    _resolve(ref, 0)
    return result


def _index_lookup_or_none(
    index: dict[str, Any] | None,
    ref: str,
) -> dict[str, Any] | None:
    if not index:
        return None
    try:
        doc_id, section_path, item_id = parse_ref(ref)
    except LoadSectionError:
        return None
    return _lookup_in_index(index, doc_id, section_path, item_id)


def _emit_stale_warning(project_root: str) -> None:
    """If the index exists but is older than ``_STALE_DAYS_WARN``, warn on stderr."""
    index_path = os.path.join(project_root, "docs", _INDEX_FILENAME)
    if not os.path.isfile(index_path):
        return
    index = _load_index(project_root)
    if not index:
        return
    age = _index_age_days(index.get("generated_at"))
    if age is not None and age >= _STALE_DAYS_WARN:
        print(
            f"[WARN] docs/.doc-index.json 已 {age:.0f} 天未更新，建议运行 `cataforge docs index`",
            file=sys.stderr,
        )
