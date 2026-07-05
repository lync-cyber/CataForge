"""Index *construction* primitives for :mod:`cataforge.domain.docs.indexer`.

Leaf module: turns ``docs/**/*.md`` into the ``.doc-index.json`` structure
(document entries, xref, aliases, dep-hash snapshots). Holds no validation
logic and imports nothing from ``indexer`` — the validators in ``indexer``
depend on these builders, never the reverse, which keeps the split acyclic.
"""

from __future__ import annotations

import glob
import hashlib
import json
import os
import re
from datetime import UTC, datetime
from typing import Any

from cataforge.core.io import read_json
from cataforge.utils.frontmatter import split_yaml_frontmatter as _split_fm
from cataforge.utils.md_parse import iter_markdown_headings
from cataforge.utils.patterns import (
    ITEM_ID_RE,
    SECTION_NUM_RE,
    SUBSECTION_NUM_RE,
)

SECTION_META_RE = re.compile(r"<!--\s*section_meta:\s*\{(.*?)\}\s*-->", re.DOTALL)
INDEX_FILENAME = ".doc-index.json"


def _parse_section_meta(lines: list[str], start: int, end: int) -> dict[str, Any]:
    for i in range(start, min(end, start + 5)):
        if i >= len(lines):
            break
        m = SECTION_META_RE.search(lines[i])
        if m:
            meta_text = m.group(1).strip()
            result: dict[str, Any] = {}
            for part in re.split(r",\s*(?=[a-z_]+:)", meta_text):
                kv = part.split(":", 1)
                if len(kv) == 2:
                    k = kv[0].strip()
                    v = kv[1].strip()
                    if v.startswith("[") and v.endswith("]"):
                        items = v[1:-1].split(",")
                        result[k] = [i.strip().strip('"').strip("'") for i in items if i.strip()]
                    elif v.isdigit():
                        result[k] = int(v)
                    else:
                        result[k] = v.strip('"').strip("'")
            return result
    return {}


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // 3)


def _content_hash(content: str) -> str:
    """Compute short hash of document body (post-frontmatter)."""
    _, body = _split_fm(content)
    text = body if body is not None else content
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


def _extract_item_id(title: str) -> str | None:
    m = re.match(r"^([A-Z]+-\d+)", title)
    return m.group(1) if m else None


def _extract_section_number(title: str) -> str | None:
    m = SUBSECTION_NUM_RE.match(title)
    if m:
        return m.group(1)
    m = SECTION_NUM_RE.match(title)
    return m.group(1) if m else None


def _build_sections(
    content: str,
    lines: list[str],
    total_lines: int,
) -> dict[str, Any]:
    """Extract the heading-based section map from *content*."""
    sections: dict[str, Any] = {}
    headings: list[tuple[int, int, str]] = []
    for i, level, title in iter_markdown_headings(content):
        headings.append((i, level, title.strip()))

    for idx, (line_idx, level, title) in enumerate(headings):
        line_end = total_lines
        for j in range(idx + 1, len(headings)):
            next_line_idx, next_level, _ = headings[j]
            if next_level <= level:
                line_end = next_line_idx
                break
        if level == 1:
            continue

        section_text = "\n".join(lines[line_idx:line_end])
        est_tokens = estimate_tokens(section_text)
        meta = _parse_section_meta(lines, line_idx + 1, line_end)
        if "est_tokens" in meta:
            est_tokens = meta["est_tokens"]

        sec_num = _extract_section_number(title)
        item_id = _extract_item_id(title)
        item_entry = {
            "heading": lines[line_idx].rstrip(),
            "line_start": line_idx + 1,
            "line_end": line_end,
            "est_tokens": est_tokens,
            "deps": meta.get("deps", []),
        }

        if level == 2 and sec_num:
            sections[sec_num] = {**item_entry, "level": level, "items": {}}
        elif level >= 3 and item_id:
            parent_sec = _find_parent_section(sections, line_idx)
            if parent_sec:
                parent_sec["items"][item_id] = item_entry
        elif level >= 3 and sec_num:
            parent_sec = _find_parent_section(sections, line_idx)
            if parent_sec:
                parent_sec["items"][sec_num] = item_entry

    return sections


def build_document_entry(file_path: str, rel_path: str) -> tuple[str | None, dict[str, Any] | None]:
    try:
        with open(file_path) as f:
            content = f.read()
    except OSError:
        return None, None

    lines = content.splitlines()
    total_lines = len(lines)

    fm = _split_fm(content)[0] or {}
    doc_id = fm.get("id", "")
    if not doc_id or "{" in doc_id:
        return None, None

    doc_type = fm.get("doc_type", "")
    status = fm.get("status", "draft")
    deps_raw = fm.get("deps", [])
    if isinstance(deps_raw, str):
        deps_raw = [d.strip() for d in deps_raw.split(",") if d.strip()]

    aliases_raw = fm.get("aliases", [])
    if isinstance(aliases_raw, str):
        aliases_raw = [a.strip() for a in aliases_raw.split(",") if a.strip()]
    if not isinstance(aliases_raw, list):
        aliases_raw = []
    aliases_clean = [str(a).strip() for a in aliases_raw if str(a).strip()]

    sections = _build_sections(content, lines, total_lines)

    entry: dict[str, Any] = {
        "file_path": rel_path.replace("\\", "/"),
        "doc_type": doc_type,
        "status": status,
        "total_lines": total_lines,
        "est_tokens": estimate_tokens(content),
        "content_hash": _content_hash(content),
        "sections": sections,
    }
    if deps_raw:
        entry["deps"] = deps_raw
    if aliases_clean:
        entry["aliases"] = aliases_clean
    return doc_id, entry


def _find_parent_section(sections: dict[str, Any], line_idx: int) -> dict[str, Any] | None:
    best = None
    best_start = -1
    for _sec_num, sec_data in sections.items():
        start = sec_data["line_start"] - 1
        end = sec_data["line_end"]
        if start <= line_idx < end and start > best_start:
            best = sec_data
            best_start = start
    return best


def build_xref(documents: dict[str, Any]) -> dict[str, list[dict[str, str]]]:
    xref: dict[str, list[dict[str, str]]] = {}
    for doc_id, doc_entry in documents.items():
        file_path = doc_entry["file_path"]
        for sec_num, sec_data in doc_entry.get("sections", {}).items():
            for item_id in sec_data.get("items", {}):
                if ITEM_ID_RE.match(item_id):
                    if item_id not in xref:
                        xref[item_id] = []
                    xref[item_id].append(
                        {
                            "doc_id": doc_id,
                            "section": sec_num,
                            "file_path": file_path,
                        }
                    )
    return xref


def _fill_dep_hashes(documents: dict[str, Any]) -> None:
    """Snapshot each upstream doc's ``content_hash`` into ``dep_hashes``."""
    for _doc_id, entry in documents.items():
        deps = entry.get("deps") or []
        if not isinstance(deps, list) or not deps:
            continue
        dep_hashes: dict[str, str] = {}
        for dep in deps:
            bare_id = dep.split("#")[0] if "#" in dep else dep
            upstream = documents.get(bare_id)
            if upstream and upstream.get("content_hash"):
                dep_hashes[bare_id] = upstream["content_hash"]
        if dep_hashes:
            entry["dep_hashes"] = dep_hashes


def _fill_dep_hashes_single(documents: dict[str, Any], target_id: str) -> None:
    """Refresh ``dep_hashes`` for *only* the given document."""
    entry = documents.get(target_id)
    if not entry:
        return
    deps = entry.get("deps") or []
    if not isinstance(deps, list) or not deps:
        return
    dep_hashes: dict[str, str] = {}
    for dep in deps:
        bare_id = dep.split("#")[0] if "#" in dep else dep
        upstream = documents.get(bare_id)
        if upstream and upstream.get("content_hash"):
            dep_hashes[bare_id] = upstream["content_hash"]
    if dep_hashes:
        entry["dep_hashes"] = dep_hashes


def build_full_index(project_root: str) -> dict[str, Any]:
    docs_dir = os.path.join(project_root, "docs")
    documents: dict[str, Any] = {}
    if not os.path.isdir(docs_dir):
        return _make_index(documents)
    for md_path in sorted(glob.glob(os.path.join(docs_dir, "**", "*.md"), recursive=True)):
        rel_path = os.path.relpath(md_path, project_root)
        doc_id, entry = build_document_entry(md_path, rel_path)
        if doc_id and entry:
            documents[doc_id] = entry
    _fill_dep_hashes(documents)
    return _make_index(documents)


def update_single_doc(
    project_root: str, doc_file: str, existing_index: dict[str, Any] | None = None
) -> dict[str, Any]:
    if existing_index is None:
        index_path = os.path.join(project_root, "docs", INDEX_FILENAME)
        existing_index = read_json(index_path) if os.path.isfile(index_path) else _make_index({})

    documents = existing_index.get("documents", {})
    abs_path = os.path.join(project_root, doc_file) if not os.path.isabs(doc_file) else doc_file
    rel_path = os.path.relpath(abs_path, project_root)

    old_ids = [
        did for did, d in documents.items() if d.get("file_path") == rel_path.replace("\\", "/")
    ]
    for old_id in old_ids:
        del documents[old_id]

    doc_id, entry = build_document_entry(abs_path, rel_path)
    if doc_id and entry:
        documents[doc_id] = entry
        _fill_dep_hashes_single(documents, doc_id)
    return _make_index(documents)


def _make_index(documents: dict[str, Any]) -> dict[str, Any]:
    aliases, alias_conflicts = build_aliases(documents)
    index: dict[str, Any] = {
        "version": "1",
        "generated_at": datetime.now(UTC).isoformat(),
        "documents": documents,
        "xref": build_xref(documents),
        "aliases": aliases,
    }
    if alias_conflicts:
        index["alias_conflicts"] = alias_conflicts
    return index


def build_aliases(
    documents: dict[str, Any],
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    """Build the top-level ``alias → doc_id`` map.

    Each doc's frontmatter ``aliases:`` list contributes alias names that
    point at its own ``id``. The resolver consults this map after exact and
    prefix lookups (see :func:`cataforge.domain.docs.loader._resolve_doc_entry`).

    First-claim wins on conflicts; collisions are recorded in the returned
    ``alias_conflicts`` list and surface in ``cataforge docs validate``.
    Aliases that collide with an actual doc_id are also rejected — a real
    doc_id always shadows an alias, so registering the alias would be a
    silent no-op.
    """
    aliases: dict[str, str] = {}
    conflicts: list[dict[str, Any]] = []
    for doc_id, entry in documents.items():
        for alias in entry.get("aliases") or []:
            if alias in documents:
                conflicts.append(
                    {
                        "alias": alias,
                        "claimed_by": doc_id,
                        "reason": f"shadowed by an existing doc_id {alias!r}",
                    }
                )
                continue
            existing = aliases.get(alias)
            if existing is not None and existing != doc_id:
                conflicts.append(
                    {
                        "alias": alias,
                        "claimed_by": doc_id,
                        "reason": f"already claimed by {existing!r}",
                    }
                )
                continue
            aliases[alias] = doc_id
    return aliases, conflicts


def write_index(index: dict[str, Any], project_root: str) -> str:
    docs_dir = os.path.join(project_root, "docs")
    os.makedirs(docs_dir, exist_ok=True)
    out_path = os.path.join(docs_dir, INDEX_FILENAME)
    with open(out_path, "w") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    return out_path
