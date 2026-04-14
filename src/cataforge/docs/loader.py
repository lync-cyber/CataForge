"""CataForge load_section — extract Markdown sections by doc_id#§N references.

Invoked via ``python -m cataforge.docs.loader`` or ``cataforge docs load``.

Supported reference formats:
    doc_id#§N              top-level section (e.g. prd#§2)
    doc_id#§N.M            sub-section (e.g. prd#§1.1)
    doc_id#§N.ITEM-xxx     item (e.g. prd#§2.F-003)

Exit codes:
    0  all refs extracted successfully
    2  at least one ref failed
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
from cataforge.utils.patterns import HEADING_RE, REF_RE, SECTION_PATH_RE

# ---------------------------------------------------------------------------
# doc_id → doc_type mapping (inlined from the former _config.build_doc_type_map)
# ---------------------------------------------------------------------------

_DOC_TYPE_MAP: dict[str, str] = {
    "prd": "prd", "arch": "arch", "ui-spec": "ui-spec",
    "dev-plan": "dev-plan", "test-report": "test-report",
    "deploy-spec": "deploy-spec", "research": "research",
    "changelog": "changelog", "brief": "brief",
}


def _get_doc_type_map() -> dict[str, str]:
    return _DOC_TYPE_MAP


# ---------------------------------------------------------------------------
# Index cache
# ---------------------------------------------------------------------------

_INDEX_CACHE: dict[str, Any] | None = None
_INDEX_FILENAME = ".doc-index.json"


def _load_index(project_root: str) -> dict[str, Any] | None:
    global _INDEX_CACHE
    if _INDEX_CACHE is not None:
        return _INDEX_CACHE
    index_path = os.path.join(project_root, "docs", _INDEX_FILENAME)
    if not os.path.isfile(index_path):
        return None
    try:
        with open(index_path, encoding="utf-8") as f:
            _INDEX_CACHE = json.load(f)
        return _INDEX_CACHE
    except (json.JSONDecodeError, OSError):
        return None


def _is_stale(file_path: str, generated_at: str | None) -> bool:
    if not generated_at:
        return True
    try:
        file_mtime = os.path.getmtime(file_path)
        gen_dt = datetime.fromisoformat(generated_at)
        file_dt = datetime.fromtimestamp(file_mtime, tz=timezone.utc)
        return file_dt > gen_dt
    except (ValueError, OSError):
        return True


def _lookup_in_index(
    index: dict[str, Any], doc_id: str, section_path: str, item_id: str | None
) -> dict[str, Any] | None:
    documents = index.get("documents", {})
    doc_entry = documents.get(doc_id)
    if not doc_entry:
        prefix = doc_id + "-"
        for did, entry in documents.items():
            if did == doc_id or did.startswith(prefix):
                doc_entry = entry
                break
    if not doc_entry:
        return None

    sections = doc_entry.get("sections", {})
    top_sec = section_path.split(".")[0] if "." in section_path else section_path
    sec_data = sections.get(top_sec)
    if not sec_data:
        return None

    file_path = doc_entry["file_path"]

    if item_id:
        item_data = sec_data.get("items", {}).get(item_id)
        if item_data:
            return {"file_path": file_path, "line_start": item_data["line_start"],
                    "line_end": item_data["line_end"], "est_tokens": item_data.get("est_tokens", 0)}
        xref = index.get("xref", {})
        if item_id in xref:
            for ref_entry in xref[item_id]:
                other_doc = documents.get(ref_entry["doc_id"])
                if not other_doc:
                    for did, d in documents.items():
                        if did.startswith(ref_entry["doc_id"] + "-"):
                            other_doc = d
                            break
                if other_doc:
                    other_sec = other_doc.get("sections", {}).get(ref_entry["section"], {})
                    other_item = other_sec.get("items", {}).get(item_id)
                    if other_item:
                        return {"file_path": ref_entry["file_path"],
                                "line_start": other_item["line_start"],
                                "line_end": other_item["line_end"],
                                "est_tokens": other_item.get("est_tokens", 0)}
        return None

    if "." in section_path:
        sub_data = sec_data.get("items", {}).get(section_path)
        if sub_data:
            return {"file_path": file_path, "line_start": sub_data["line_start"],
                    "line_end": sub_data["line_end"], "est_tokens": sub_data.get("est_tokens", 0)}
        return None

    return {"file_path": file_path, "line_start": sec_data["line_start"],
            "line_end": sec_data["line_end"], "est_tokens": sec_data.get("est_tokens", 0)}


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class LoadSectionError(Exception):
    pass


class RefParseError(LoadSectionError):
    pass


class DocResolveError(LoadSectionError):
    pass


class SectionNotFoundError(LoadSectionError):
    pass


# ---------------------------------------------------------------------------
# Ref parsing
# ---------------------------------------------------------------------------


def parse_ref(ref: str) -> tuple[str, str, str | None]:
    if not isinstance(ref, str) or not ref.strip():
        raise RefParseError(f"引用为空或类型错误: {ref!r}")
    m = REF_RE.match(ref.strip())
    if not m:
        raise RefParseError(f"引用格式非法: {ref!r}，应为 doc_id#§<section>[.item]")
    doc_id = m.group("doc_id")
    section_part = m.group("section")

    item_match = re.match(r"^(?P<sec>\d+(?:\.\d+)*)\.(?P<item>[A-Z]+-\d+)$", section_part)
    if item_match:
        return doc_id, item_match.group("sec"), item_match.group("item")

    if SECTION_PATH_RE.match(section_part):
        return doc_id, section_part, None

    raise RefParseError(f"无法解析节路径 {section_part!r}")


# ---------------------------------------------------------------------------
# File resolution
# ---------------------------------------------------------------------------


def resolve_file(
    doc_id: str, project_root: str, section_path: str = "", item_id: str | None = None
) -> str:
    doc_type_map = _get_doc_type_map()
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
            with open(path, encoding="utf-8") as f:
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
                nxt = title[len(item_id): len(item_id) + 1]
                if nxt in ("", ":", " ", "\t"):
                    return i, level
        elif "." in section_path:
            if title == section_path or (
                title.startswith(section_path)
                and title[len(section_path): len(section_path) + 1] in ("", " ", ".", "\t")
            ):
                return i, level
        else:
            if title == section_path or (
                title.startswith(section_path)
                and title[len(section_path): len(section_path) + 1] in ("", ".", " ", "\t")
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


def extract(ref: str, project_root: str) -> str:
    doc_id, section_path, item_id = parse_ref(ref)

    index = _load_index(project_root)
    if index:
        entry = _lookup_in_index(index, doc_id, section_path, item_id)
        if entry:
            abs_path = os.path.join(project_root, entry["file_path"])
            if os.path.isfile(abs_path) and not _is_stale(abs_path, index.get("generated_at")):
                with open(abs_path, encoding="utf-8") as f:
                    lines = f.readlines()
                start = entry["line_start"] - 1
                end = entry["line_end"]
                result = "".join(lines[start:end]).rstrip()
                if result:
                    return result

    file_path = resolve_file(doc_id, project_root, section_path, item_id)
    with open(file_path, encoding="utf-8") as f:
        content = f.read()

    lines = content.splitlines()
    found = _find_heading_line(content, section_path, item_id)
    if found is None:
        target = f"§{section_path}" + (f".{item_id}" if item_id else "")
        raise SectionNotFoundError(f"在 {file_path} 中未找到 {target}")
    start_idx, level = found
    return _extract_section_from_lines(lines, start_idx, level)


def extract_batch(
    refs: list[str], project_root: str
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    successes: list[tuple[str, str]] = []
    errors: list[tuple[str, str]] = []
    for ref in refs:
        try:
            content = extract(ref, project_root)
            successes.append((ref, content))
        except LoadSectionError as e:
            errors.append((ref, str(e)))
    return successes, errors


def plan_load(
    refs: list[str], project_root: str, token_budget: int
) -> tuple[list[str], list[str]]:
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


# ---------------------------------------------------------------------------
# CLI entry
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ensure_utf8_stdio()
    parser = argparse.ArgumentParser(
        description="CataForge load_section — extract Markdown sections by reference",
    )
    parser.add_argument("refs", nargs="+", help="doc_id#§N references")
    parser.add_argument("--project-root", default=None)
    args = parser.parse_args(argv)

    project_root = args.project_root or str(find_project_root())

    successes, errors = extract_batch(args.refs, project_root)
    for ref, content in successes:
        print(f"=== {ref} ===")
        print(content)
        print()

    if errors:
        for ref, msg in errors:
            print(f"[ERROR] {ref}: {msg}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
