#!/usr/bin/env python3
"""build_doc_index — 构建文档章节级 JSON 索引。

扫描 docs/ 下所有 .md 文件，解析 YAML Front Matter 和 Markdown 标题结构，
生成 docs/.doc-index.json 供 load_section.py 实现 O(1) 章节定位。

用法:
  python .claude/scripts/build_doc_index.py [--project-root DIR]
  python .claude/scripts/build_doc_index.py --doc-file docs/arch/arch-myapp-v1.md

全量构建: 扫描 docs/**/*.md，重建完整索引。
增量更新: --doc-file 仅更新指定文件的条目。
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import ensure_utf8_stdio, find_project_root
from _patterns import HEADING_RE, ITEM_ID_RE, SECTION_NUM_RE, SUBSECTION_NUM_RE
from _yaml_parser import parse_yaml_frontmatter

SECTION_META_RE = re.compile(r"<!--\s*section_meta:\s*\{(.*?)\}\s*-->", re.DOTALL)

INDEX_FILENAME = ".doc-index.json"


_parse_yaml_frontmatter = parse_yaml_frontmatter


def _parse_section_meta(lines: List[str], start: int, end: int) -> Dict[str, Any]:
    """在指定行范围内查找 section_meta 注释并解析。"""
    for i in range(start, min(end, start + 5)):  # 只在前 5 行查找
        if i >= len(lines):
            break
        m = SECTION_META_RE.search(lines[i])
        if m:
            meta_text = m.group(1).strip()
            result: Dict[str, Any] = {}
            # 简单解析 key: value 对
            for part in re.split(r",\s*(?=[a-z_]+:)", meta_text):
                kv = part.split(":", 1)
                if len(kv) == 2:
                    k = kv[0].strip()
                    v = kv[1].strip()
                    if v.startswith("[") and v.endswith("]"):
                        items = v[1:-1].split(",")
                        result[k] = [
                            i.strip().strip('"').strip("'") for i in items if i.strip()
                        ]
                    elif v.isdigit():
                        result[k] = int(v)
                    else:
                        result[k] = v.strip('"').strip("'")
            return result
    return {}


def _estimate_tokens(text: str) -> int:
    """估算文本的 Token 数（混合中英文按字符数 / 2.5 估算）。"""
    if not text:
        return 0
    return max(1, len(text) // 3)


def _extract_item_id(title: str) -> Optional[str]:
    """从标题文本中提取 item ID（如 F-001, M-002, API-001）。"""
    # 匹配标题开头的 item ID
    m = re.match(r"^([A-Z]+-\d+)", title)
    if m:
        return m.group(1)
    return None


def _extract_section_number(title: str) -> Optional[str]:
    """从标题文本中提取章节编号（如 1, 1.1, 2）。"""
    m = SUBSECTION_NUM_RE.match(title)
    if m:
        return m.group(1)
    m = SECTION_NUM_RE.match(title)
    if m:
        return m.group(1)
    return None


def build_document_entry(
    file_path: str, rel_path: str
) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    """为单个文档文件构建索引条目。

    返回 (doc_id, entry_dict) 或 (None, None) 如果无法解析。
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return None, None

    lines = content.splitlines()
    total_lines = len(lines)

    # 解析 YAML Front Matter
    fm = _parse_yaml_frontmatter(content)
    doc_id = fm.get("id", "")
    if not doc_id or "{" in doc_id:
        # 模板文件或无效 ID，跳过
        return None, None

    doc_type = fm.get("doc_type", "")
    volume = fm.get("volume", "main")
    status = fm.get("status", "draft")
    split_from = fm.get("split_from", "")
    deps_raw = fm.get("deps", [])
    if isinstance(deps_raw, str):
        deps_raw = [d.strip() for d in deps_raw.split(",") if d.strip()]

    # 构建 sections 树
    sections: Dict[str, Any] = {}
    # 记录所有标题行: (line_idx, level, title_text)
    headings: List[Tuple[int, int, str]] = []
    for i, line in enumerate(lines):
        m = HEADING_RE.match(line)
        if m:
            headings.append((i, len(m.group(1)), m.group(2).strip()))

    # 为每个标题计算 line_end
    for idx, (line_idx, level, title) in enumerate(headings):
        # line_end 为下一个同级或更高级标题行 - 1，或 EOF
        line_end = total_lines
        for j in range(idx + 1, len(headings)):
            next_line_idx, next_level, _ = headings[j]
            if next_level <= level:
                line_end = next_line_idx
                break

        # 跳过 level 1 标题（文档标题）
        if level == 1:
            continue

        section_text = "\n".join(lines[line_idx:line_end])
        est_tokens = _estimate_tokens(section_text)

        # 解析 section_meta
        meta = _parse_section_meta(lines, line_idx + 1, line_end)
        if "est_tokens" in meta:
            est_tokens = meta["est_tokens"]

        sec_num = _extract_section_number(title)
        item_id = _extract_item_id(title)

        if level == 2 and sec_num:
            # 顶级章节
            section_entry = {
                "heading": lines[line_idx].rstrip(),
                "level": level,
                "line_start": line_idx + 1,  # 1-based
                "line_end": line_end,  # exclusive, 0-based lines → 1-based end
                "est_tokens": est_tokens,
                "deps": meta.get("deps", []),
                "items": {},
            }
            sections[sec_num] = section_entry
        elif level >= 3 and item_id:
            # item 级条目 — 归入父章节
            parent_sec = _find_parent_section(sections, line_idx)
            if parent_sec:
                item_deps = meta.get("deps", [])
                parent_sec["items"][item_id] = {
                    "heading": lines[line_idx].rstrip(),
                    "line_start": line_idx + 1,
                    "line_end": line_end,
                    "est_tokens": est_tokens,
                    "deps": item_deps,
                }
        elif level >= 3 and sec_num:
            # 子章节（如 1.1, 4.1）— 归入父章节的 items
            parent_sec = _find_parent_section(sections, line_idx)
            if parent_sec:
                parent_sec["items"][sec_num] = {
                    "heading": lines[line_idx].rstrip(),
                    "line_start": line_idx + 1,
                    "line_end": line_end,
                    "est_tokens": est_tokens,
                    "deps": meta.get("deps", []),
                }

    entry = {
        "file_path": rel_path.replace("\\", "/"),
        "doc_type": doc_type,
        "volume": volume,
        "status": status,
        "total_lines": total_lines,
        "est_tokens": _estimate_tokens(content),
        "sections": sections,
    }
    if split_from:
        entry["split_from"] = split_from
    if deps_raw:
        entry["deps"] = deps_raw

    return doc_id, entry


def _find_parent_section(
    sections: Dict[str, Any], line_idx: int
) -> Optional[Dict[str, Any]]:
    """找到包含给定行号的最近父章节。"""
    best = None
    best_start = -1
    for sec_num, sec_data in sections.items():
        start = sec_data["line_start"] - 1  # 转回 0-based
        end = sec_data["line_end"]
        if start <= line_idx < end and start > best_start:
            best = sec_data
            best_start = start
    return best


def build_xref(documents: Dict[str, Any]) -> Dict[str, List[Dict[str, str]]]:
    """构建交叉引用索引: item_id → [{doc_id, section, file_path}]。"""
    xref: Dict[str, List[Dict[str, str]]] = {}
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


def build_full_index(project_root: str) -> Dict[str, Any]:
    """全量构建索引。"""
    docs_dir = os.path.join(project_root, "docs")
    documents: Dict[str, Any] = {}

    if not os.path.isdir(docs_dir):
        return _make_index(documents)

    for md_path in sorted(
        glob.glob(os.path.join(docs_dir, "**", "*.md"), recursive=True)
    ):
        rel_path = os.path.relpath(md_path, project_root)
        doc_id, entry = build_document_entry(md_path, rel_path)
        if doc_id and entry:
            documents[doc_id] = entry

    return _make_index(documents)


def update_single_doc(
    project_root: str, doc_file: str, existing_index: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """增量更新: 仅重新索引指定文件。"""
    if existing_index is None:
        index_path = os.path.join(project_root, "docs", INDEX_FILENAME)
        if os.path.isfile(index_path):
            with open(index_path, "r", encoding="utf-8") as f:
                existing_index = json.load(f)
        else:
            existing_index = _make_index({})

    documents = existing_index.get("documents", {})

    abs_path = (
        os.path.join(project_root, doc_file)
        if not os.path.isabs(doc_file)
        else doc_file
    )
    rel_path = os.path.relpath(abs_path, project_root)

    # 移除旧条目（可能 doc_id 变了）
    old_ids = [
        did
        for did, d in documents.items()
        if d.get("file_path") == rel_path.replace("\\", "/")
    ]
    for old_id in old_ids:
        del documents[old_id]

    # 添加新条目
    doc_id, entry = build_document_entry(abs_path, rel_path)
    if doc_id and entry:
        documents[doc_id] = entry

    return _make_index(documents)


def _make_index(documents: Dict[str, Any]) -> Dict[str, Any]:
    """组装完整索引结构。"""
    return {
        "version": "1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "documents": documents,
        "xref": build_xref(documents),
    }


def write_index(index: Dict[str, Any], project_root: str) -> str:
    """将索引写入 docs/.doc-index.json，返回文件路径。"""
    docs_dir = os.path.join(project_root, "docs")
    os.makedirs(docs_dir, exist_ok=True)
    out_path = os.path.join(docs_dir, INDEX_FILENAME)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    return out_path


def main(argv: Optional[List[str]] = None) -> int:
    ensure_utf8_stdio()
    parser = argparse.ArgumentParser(
        description="CataForge build_doc_index — 构建文档章节级 JSON 索引",
    )
    parser.add_argument(
        "--project-root",
        default=None,
        help="项目根目录（默认自动推断）",
    )
    parser.add_argument(
        "--doc-file",
        default=None,
        help="仅更新指定文件（增量模式）",
    )
    args = parser.parse_args(argv)

    project_root = args.project_root or find_project_root()

    if args.doc_file:
        index = update_single_doc(project_root, args.doc_file)
    else:
        index = build_full_index(project_root)

    out_path = write_index(index, project_root)
    doc_count = len(index.get("documents", {}))
    xref_count = len(index.get("xref", {}))
    print(f"索引已写入: {out_path}")
    print(f"文档数: {doc_count}, 交叉引用条目: {xref_count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
