#!/usr/bin/env python3
"""CataForge load_section — 按章节/条目从 Markdown 文档精准提取内容。

doc-nav Skill 的执行后端，替代"Read 全文 + 人眼定位"方案。
通过解析 `doc_id#§N[.item]` 引用，在对应 doc_type 目录下定位文件和章节，
仅输出目标章节内容（含嵌套子节），显著降低上下文占用。

用法 (CLI):
  python .claude/scripts/load_section.py <ref> [<ref> ...]
  python .claude/scripts/load_section.py --project-root /path/to/proj <ref>

  支持的引用格式:
    doc_id#§N              # 顶级章节，如 prd#§2
    doc_id#§N.M            # 子章节，如 prd#§1.1
    doc_id#§N.ITEM-xxx     # 条目，如 prd#§2.F-003, arch#§3.API-001

  退出码:
    0  全部引用成功提取
    2  至少一个引用无法解析或定位失败（错误信息写入 stderr）

用法 (Python 导入):
  from load_section import extract, resolve_file, parse_ref
  content = extract("prd#§2.F-003", project_root="/path/to/proj")
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

# 共享工具
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import build_doc_type_map, ensure_utf8_stdio, find_project_root
from _patterns import HEADING_RE, ITEM_ID_RE, REF_RE, SECTION_PATH_RE


# ============================================================================
# 索引缓存 (进程生命周期内单例)
# ============================================================================

_INDEX_CACHE: Optional[Dict[str, Any]] = None
_INDEX_FILENAME = ".doc-index.json"


def _load_index(project_root: str) -> Optional[Dict[str, Any]]:
    """加载 docs/.doc-index.json，进程内缓存。"""
    global _INDEX_CACHE
    if _INDEX_CACHE is not None:
        return _INDEX_CACHE
    index_path = os.path.join(project_root, "docs", _INDEX_FILENAME)
    if not os.path.isfile(index_path):
        return None
    try:
        with open(index_path, "r", encoding="utf-8") as f:
            _INDEX_CACHE = json.load(f)
        return _INDEX_CACHE
    except (json.JSONDecodeError, OSError):
        return None


def _is_stale(file_path: str, generated_at: Optional[str]) -> bool:
    """检查文件是否比索引更新（索引过期）。"""
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
    index: Dict[str, Any],
    doc_id: str,
    section_path: str,
    item_id: Optional[str],
) -> Optional[Dict[str, Any]]:
    """在索引中查找章节/条目，返回含 file_path, line_start, line_end 的字典。"""
    documents = index.get("documents", {})

    # 直接匹配 doc_id
    doc_entry = documents.get(doc_id)

    # 尝试前缀匹配（如 doc_id="prd" 匹配 "prd-myapp-v1"）
    if not doc_entry:
        prefix = doc_id + "-"
        for did, entry in documents.items():
            if did == doc_id or did.startswith(prefix):
                doc_entry = entry
                break

    if not doc_entry:
        return None

    sections = doc_entry.get("sections", {})

    # 查找目标 section
    top_sec = section_path.split(".")[0] if "." in section_path else section_path
    sec_data = sections.get(top_sec)
    if not sec_data:
        return None

    file_path = doc_entry["file_path"]

    if item_id:
        # 在 section 的 items 中查找
        item_data = sec_data.get("items", {}).get(item_id)
        if item_data:
            return {
                "file_path": file_path,
                "line_start": item_data["line_start"],
                "line_end": item_data["line_end"],
                "est_tokens": item_data.get("est_tokens", 0),
            }
        # item 可能在其他文档（分卷）中
        xref = index.get("xref", {})
        if item_id in xref:
            for ref_entry in xref[item_id]:
                other_doc = documents.get(ref_entry["doc_id"])
                if not other_doc:
                    # 前缀搜索
                    for did, d in documents.items():
                        if did.startswith(ref_entry["doc_id"] + "-"):
                            other_doc = d
                            break
                if other_doc:
                    other_sec = other_doc.get("sections", {}).get(
                        ref_entry["section"], {}
                    )
                    other_item = other_sec.get("items", {}).get(item_id)
                    if other_item:
                        return {
                            "file_path": ref_entry["file_path"],
                            "line_start": other_item["line_start"],
                            "line_end": other_item["line_end"],
                            "est_tokens": other_item.get("est_tokens", 0),
                        }
        return None

    # 子章节（如 1.1）
    if "." in section_path:
        sub_data = sec_data.get("items", {}).get(section_path)
        if sub_data:
            return {
                "file_path": file_path,
                "line_start": sub_data["line_start"],
                "line_end": sub_data["line_end"],
                "est_tokens": sub_data.get("est_tokens", 0),
            }
        return None

    # 顶级章节
    return {
        "file_path": file_path,
        "line_start": sec_data["line_start"],
        "line_end": sec_data["line_end"],
        "est_tokens": sec_data.get("est_tokens", 0),
    }


# doc_id → doc_type 目录映射 (延迟加载，避免 import 时产生 I/O 副作用)
_DOC_TYPE_MAP_CACHE: Optional[Dict[str, str]] = None


def _get_doc_type_map() -> Dict[str, str]:
    global _DOC_TYPE_MAP_CACHE
    if _DOC_TYPE_MAP_CACHE is None:
        _DOC_TYPE_MAP_CACHE = build_doc_type_map()
    return _DOC_TYPE_MAP_CACHE


# Regex patterns imported from _patterns.py (single source of truth)


class LoadSectionError(Exception):
    """load_section 的基类异常。"""


class RefParseError(LoadSectionError):
    """引用格式非法。"""


class DocResolveError(LoadSectionError):
    """doc_id 无法定位到文件。"""


class SectionNotFoundError(LoadSectionError):
    """引用合法但在任何候选文件中均未找到匹配章节。"""


def parse_ref(ref: str) -> Tuple[str, str, Optional[str]]:
    """拆分引用字符串为 (doc_id, section_path, item_id)。

    规则:
      - prd#§2          → ("prd", "2", None)
      - prd#§1.1        → ("prd", "1.1", None)
      - prd#§2.F-003    → ("prd", "2", "F-003")
      - arch#§3.API-001 → ("arch", "3", "API-001")

    无法解析时抛出 RefParseError。
    """
    if not isinstance(ref, str) or not ref.strip():
        raise RefParseError(f"引用为空或类型错误: {ref!r}")

    m = REF_RE.match(ref.strip())
    if not m:
        raise RefParseError(f"引用格式非法: {ref!r}，应为 doc_id#§<section>[.item]")

    doc_id = m.group("doc_id")
    section_part = m.group("section")

    # 尝试识别 "section.item" 形式
    # item_id 至少包含一个大写字母和一个 '-'，以此与 "1.1" 子节区分
    item_match = re.match(
        r"^(?P<sec>\d+(?:\.\d+)*)\.(?P<item>[A-Z]+-\d+)$", section_part
    )
    if item_match:
        return doc_id, item_match.group("sec"), item_match.group("item")

    # 纯节路径
    if SECTION_PATH_RE.match(section_part):
        return doc_id, section_part, None

    raise RefParseError(
        f"无法解析节路径 {section_part!r}，应为 N / N.M / N.ITEM-xxx 形式"
    )


def _candidate_filenames(doc_id: str) -> List[str]:
    """根据 doc_id 返回优先级排序的候选文件名 glob 模式。

    优先命中主卷；若未命中则搜索同 doc_type 目录下的分卷。
    """
    # 优先匹配 doc_id-*.md 形式（与 doc-gen 文件命名约定一致）
    patterns = [f"{doc_id}-*.md"]
    # 同时允许 doc_id 与分卷（如 arch 搜索 arch-api-*.md 不必要，分卷文件本身命名为
    # arch-{project}-{ver}-api.md，也以 arch- 开头，故同一个 pattern 已覆盖）
    return patterns


def resolve_file(
    doc_id: str,
    project_root: str,
    section_path: str = "",
    item_id: Optional[str] = None,
) -> str:
    """根据 doc_id 定位文件路径，返回绝对路径。

    1. 从 _get_doc_type_map() 推断 doc_type 子目录
    2. 在 docs/{doc_type}/ 下查找以 doc_id 开头的 .md 文件
    3. 多文件场景下，基于 section_path/item_id 探测匹配章节所在文件

    找不到文件或目录时抛出 DocResolveError。
    """
    if doc_id not in _get_doc_type_map():
        raise DocResolveError(
            f"未知的 doc_id: {doc_id!r}，"
            f"支持的前缀见 _get_doc_type_map()（{sorted(_get_doc_type_map().keys())[:5]}...）"
        )

    doc_type = _get_doc_type_map()[doc_id]
    doc_dir = os.path.join(project_root, "docs", doc_type)

    if not os.path.isdir(doc_dir):
        raise DocResolveError(f"文档目录不存在: {doc_dir}")

    candidates: List[str] = []
    for pattern in _candidate_filenames(doc_id):
        for path in sorted(glob.glob(os.path.join(doc_dir, pattern))):
            if path not in candidates:
                candidates.append(path)

    if not candidates:
        raise DocResolveError(f"在 {doc_dir} 下未找到匹配 {doc_id}-*.md 的文件")

    # 若只有一个候选，直接返回
    if len(candidates) == 1:
        return candidates[0]

    # 多卷场景: 依次在每个候选文件中查找目标章节
    for path in candidates:
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
        except OSError:
            continue
        if _find_heading_line(content.splitlines(), section_path, item_id) is not None:
            return path

    # 所有候选都没找到，则保守返回第一个候选（让下游报 SectionNotFoundError）
    return candidates[0]


def _find_heading_line(
    lines: List[str], section_path: str, item_id: Optional[str]
) -> Optional[Tuple[int, int]]:
    """在行列表中查找目标标题行。

    返回 (行索引, 标题级别) 或 None。
    """
    for i, line in enumerate(lines):
        m = HEADING_RE.match(line)
        if not m:
            continue
        level = len(m.group(1))
        title = m.group(2).strip()

        if item_id:
            # 匹配 "F-001: ..." / "F-001 ..." / "F-001"
            if title == item_id:
                return i, level
            if title.startswith(item_id):
                nxt = title[len(item_id) : len(item_id) + 1]
                if nxt in ("", ":", " ", "\t"):
                    return i, level
        elif "." in section_path:
            # 子章节: "1.1 背景与动机" / "1.1. 背景" / "1.1"
            if title == section_path:
                return i, level
            if title.startswith(section_path):
                nxt = title[len(section_path) : len(section_path) + 1]
                if nxt in ("", " ", ".", "\t"):
                    return i, level
        else:
            # 顶级节: "2. 功能需求" / "2 功能需求" / "2"
            if title == section_path:
                return i, level
            if title.startswith(section_path):
                nxt = title[len(section_path) : len(section_path) + 1]
                if nxt in ("", ".", " ", "\t"):
                    return i, level

    return None


def _extract_section_from_lines(lines: List[str], start_idx: int, level: int) -> str:
    """从 start_idx 开始提取章节内容，直到遇到同级或更高级标题。

    包含起始标题行本身。
    """
    result = [lines[start_idx]]
    for i in range(start_idx + 1, len(lines)):
        line = lines[i]
        m = HEADING_RE.match(line)
        if m and len(m.group(1)) <= level:
            break
        result.append(line)
    # 去除结尾多余空行
    while result and result[-1].strip() == "":
        result.pop()
    return "\n".join(result)


def extract(ref: str, project_root: str) -> str:
    """按引用提取 Markdown 章节内容（不含文件路径前缀）。

    优先使用 .doc-index.json 索引实现 O(1) 定位，
    索引不存在或过期时回退到全文扫描。

    异常:
      RefParseError:       引用格式非法
      DocResolveError:     doc_id 无法定位文件
      SectionNotFoundError: 章节/条目在文件中不存在
    """
    doc_id, section_path, item_id = parse_ref(ref)

    # 索引优先路径 — O(1) 查找
    index = _load_index(project_root)
    if index:
        entry = _lookup_in_index(index, doc_id, section_path, item_id)
        if entry:
            abs_path = os.path.join(project_root, entry["file_path"])
            if os.path.isfile(abs_path) and not _is_stale(
                abs_path, index.get("generated_at")
            ):
                with open(abs_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                start = entry["line_start"] - 1  # 转为 0-based
                end = entry["line_end"]
                result = "".join(lines[start:end]).rstrip()
                if result:
                    return result

    # 回退: 全文扫描
    file_path = resolve_file(doc_id, project_root, section_path, item_id)

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    lines = content.splitlines()
    found = _find_heading_line(lines, section_path, item_id)
    if found is None:
        target = f"§{section_path}" + (f".{item_id}" if item_id else "")
        raise SectionNotFoundError(
            f"在 {file_path} 中未找到 {target}（来自引用 {ref}）"
        )
    start_idx, level = found
    return _extract_section_from_lines(lines, start_idx, level)


def extract_batch(
    refs: List[str], project_root: str
) -> Tuple[List[Tuple[str, str]], List[Tuple[str, str]]]:
    """批量提取，返回 (成功列表, 错误列表)。

    成功项: (ref, content)
    错误项: (ref, error_message)
    """
    successes: List[Tuple[str, str]] = []
    errors: List[Tuple[str, str]] = []
    for ref in refs:
        try:
            content = extract(ref, project_root)
            successes.append((ref, content))
        except LoadSectionError as e:
            errors.append((ref, str(e)))
    return successes, errors


def plan_load(
    refs: List[str], project_root: str, token_budget: int
) -> Tuple[List[str], List[str]]:
    """根据 Token 预算规划加载顺序。

    按 refs 给定顺序累计 est_tokens，超出预算的引用放入 deferred。

    返回 (loadable_refs, deferred_refs)。
    """
    index = _load_index(project_root)
    loadable: List[str] = []
    deferred: List[str] = []
    remaining = token_budget
    for ref in refs:
        est = 200  # 默认估算
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


def resolve_deps(ref: str, project_root: str, max_depth: int = 2) -> List[str]:
    """从索引解析章节的传递性依赖，返回有序 ref 列表（不含自身）。

    max_depth 限制递归深度，防止循环引用。
    """
    index = _load_index(project_root)
    if not index:
        return []

    visited: set[str] = set()
    result: List[str] = []

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


def main(argv: Optional[List[str]] = None) -> int:
    ensure_utf8_stdio()
    parser = argparse.ArgumentParser(
        description="CataForge load_section — 按 doc_id#§... 引用提取 Markdown 章节",
    )
    parser.add_argument(
        "refs",
        nargs="+",
        help="引用列表，如 prd#§2 prd#§2.F-001 arch#§3.API-001",
    )
    parser.add_argument(
        "--project-root",
        default=None,
        help="项目根目录（默认自动推断）",
    )
    args = parser.parse_args(argv)

    project_root = args.project_root or find_project_root()

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
