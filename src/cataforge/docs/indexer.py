"""build_doc_index — build chapter-level JSON index for docs/.

Invoked via ``python -m cataforge.docs.indexer`` or ``cataforge docs index``.

Scans docs/**/*.md, parses YAML Front Matter and Markdown heading structure,
produces docs/.doc-index.json for O(1) section lookup.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from datetime import datetime, timezone
from typing import Any

from cataforge.core.paths import find_project_root
from cataforge.utils.common import ensure_utf8_stdio
from cataforge.utils.md_parse import iter_markdown_headings
from cataforge.utils.patterns import ITEM_ID_RE, SECTION_NUM_RE, SUBSECTION_NUM_RE
from cataforge.utils.yaml_parser import parse_yaml_frontmatter

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


def _estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // 3)


def _extract_item_id(title: str) -> str | None:
    m = re.match(r"^([A-Z]+-\d+)", title)
    return m.group(1) if m else None


def _extract_section_number(title: str) -> str | None:
    m = SUBSECTION_NUM_RE.match(title)
    if m:
        return m.group(1)
    m = SECTION_NUM_RE.match(title)
    return m.group(1) if m else None


def build_document_entry(
    file_path: str, rel_path: str
) -> tuple[str | None, dict[str, Any] | None]:
    try:
        with open(file_path, encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return None, None

    lines = content.splitlines()
    total_lines = len(lines)

    fm = parse_yaml_frontmatter(content)
    doc_id = fm.get("id", "")
    if not doc_id or "{" in doc_id:
        return None, None

    doc_type = fm.get("doc_type", "")
    volume = fm.get("volume", "main")
    status = fm.get("status", "draft")
    split_from = fm.get("split_from", "")
    deps_raw = fm.get("deps", [])
    if isinstance(deps_raw, str):
        deps_raw = [d.strip() for d in deps_raw.split(",") if d.strip()]

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
        est_tokens = _estimate_tokens(section_text)
        meta = _parse_section_meta(lines, line_idx + 1, line_end)
        if "est_tokens" in meta:
            est_tokens = meta["est_tokens"]

        sec_num = _extract_section_number(title)
        item_id = _extract_item_id(title)

        if level == 2 and sec_num:
            sections[sec_num] = {
                "heading": lines[line_idx].rstrip(), "level": level,
                "line_start": line_idx + 1, "line_end": line_end,
                "est_tokens": est_tokens, "deps": meta.get("deps", []),
                "items": {},
            }
        elif level >= 3 and item_id:
            parent_sec = _find_parent_section(sections, line_idx)
            if parent_sec:
                parent_sec["items"][item_id] = {
                    "heading": lines[line_idx].rstrip(),
                    "line_start": line_idx + 1, "line_end": line_end,
                    "est_tokens": est_tokens, "deps": meta.get("deps", []),
                }
        elif level >= 3 and sec_num:
            parent_sec = _find_parent_section(sections, line_idx)
            if parent_sec:
                parent_sec["items"][sec_num] = {
                    "heading": lines[line_idx].rstrip(),
                    "line_start": line_idx + 1, "line_end": line_end,
                    "est_tokens": est_tokens, "deps": meta.get("deps", []),
                }

    entry: dict[str, Any] = {
        "file_path": rel_path.replace("\\", "/"),
        "doc_type": doc_type, "volume": volume, "status": status,
        "total_lines": total_lines, "est_tokens": _estimate_tokens(content),
        "sections": sections,
    }
    if split_from:
        entry["split_from"] = split_from
    if deps_raw:
        entry["deps"] = deps_raw
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
                    xref[item_id].append({
                        "doc_id": doc_id, "section": sec_num, "file_path": file_path,
                    })
    return xref


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
    return _make_index(documents)


def find_orphan_docs(project_root: str) -> list[str]:
    """Return rel-paths of ``docs/**/*.md`` that the indexer cannot ingest.

    A file is "orphan" when it is missing YAML front matter, or its ``id``
    field is empty/contains a ``{...}`` template placeholder. Such files are
    silently skipped by :func:`build_full_index` and never appear in
    ``.doc-index.json``, which means downstream consumers (``cataforge docs
    load``, ``--with-deps``, agent prose) cannot resolve them. Surfacing them
    is the only way to catch this whole class of rot.

    Files under ``.archive/`` are excluded — those are intentional snapshots
    of historical NAV-INDEX content kept by ``cataforge docs migrate-nav``.
    """
    docs_dir = os.path.join(project_root, "docs")
    if not os.path.isdir(docs_dir):
        return []
    orphans: list[str] = []
    for md_path in sorted(glob.glob(os.path.join(docs_dir, "**", "*.md"), recursive=True)):
        rel_path = os.path.relpath(md_path, project_root)
        rel_posix = rel_path.replace("\\", "/")
        if "/.archive/" in rel_posix or rel_posix.startswith("docs/.archive/"):
            continue
        doc_id, entry = build_document_entry(md_path, rel_path)
        if not (doc_id and entry):
            orphans.append(rel_posix)
    return orphans


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
        with open(index_path, encoding="utf-8") as f:
            index = json.load(f)
    except (OSError, json.JSONDecodeError):
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


def update_single_doc(
    project_root: str, doc_file: str, existing_index: dict[str, Any] | None = None
) -> dict[str, Any]:
    if existing_index is None:
        index_path = os.path.join(project_root, "docs", INDEX_FILENAME)
        if os.path.isfile(index_path):
            with open(index_path, encoding="utf-8") as f:
                existing_index = json.load(f)
        else:
            existing_index = _make_index({})

    documents = existing_index.get("documents", {})
    abs_path = os.path.join(project_root, doc_file) if not os.path.isabs(doc_file) else doc_file
    rel_path = os.path.relpath(abs_path, project_root)

    old_ids = [did for did, d in documents.items()
               if d.get("file_path") == rel_path.replace("\\", "/")]
    for old_id in old_ids:
        del documents[old_id]

    doc_id, entry = build_document_entry(abs_path, rel_path)
    if doc_id and entry:
        documents[doc_id] = entry
    return _make_index(documents)


def _make_index(documents: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": "1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "documents": documents,
        "xref": build_xref(documents),
    }


def write_index(index: dict[str, Any], project_root: str) -> str:
    docs_dir = os.path.join(project_root, "docs")
    os.makedirs(docs_dir, exist_ok=True)
    out_path = os.path.join(docs_dir, INDEX_FILENAME)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    return out_path


def main(argv: list[str] | None = None) -> int:
    ensure_utf8_stdio()
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
