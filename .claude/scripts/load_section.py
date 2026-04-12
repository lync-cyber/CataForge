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
import os
import re
import sys
from typing import List, Optional, Tuple

# 共享工具
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import ensure_utf8_stdio, find_project_root


# doc_id → doc_type 目录映射
# doc_type 与 doc-gen SKILL.md §template_id 映射表保持同步
DOC_TYPE_MAP = {
    "prd": "prd",
    "prd-lite": "prd",
    "prd-volume": "prd",
    "arch": "arch",
    "arch-lite": "arch",
    "arch-modules": "arch",
    "arch-api": "arch",
    "arch-data": "arch",
    "ui-spec": "ui-spec",
    "ui-spec-components": "ui-spec",
    "ui-spec-pages": "ui-spec",
    "dev-plan": "dev-plan",
    "dev-plan-lite": "dev-plan",
    "dev-plan-sprint": "dev-plan",
    "test-report": "test-report",
    "deploy-spec": "deploy-spec",
    "brief": "brief",
    "research": "research",
    "research-note": "research",
    "changelog": "changelog",
}


# 条目 ID 模式: 大写字母 + 数字后缀，如 F-001, API-001, M-003, E-012, T-042, C-007, P-001, AC-015
ITEM_ID_RE = re.compile(r"^[A-Z]+-\d+$")

# 节路径模式: 纯数字或点分数字，如 1, 1.1, 2.3.4
SECTION_PATH_RE = re.compile(r"^\d+(?:\.\d+)*$")

# 引用拆分: doc_id#§<section>[.<item>]
REF_RE = re.compile(r"^(?P<doc_id>[a-z][a-z0-9\-]*)#§(?P<section>.+)$")

# Markdown 标题行
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


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
        raise RefParseError(
            f"引用格式非法: {ref!r}，应为 doc_id#§<section>[.item]"
        )

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
    doc_id: str, project_root: str, section_path: str = "", item_id: Optional[str] = None
) -> str:
    """根据 doc_id 定位文件路径，返回绝对路径。

    1. 从 DOC_TYPE_MAP 推断 doc_type 子目录
    2. 在 docs/{doc_type}/ 下查找以 doc_id 开头的 .md 文件
    3. 多文件场景下，基于 section_path/item_id 探测匹配章节所在文件

    找不到文件或目录时抛出 DocResolveError。
    """
    if doc_id not in DOC_TYPE_MAP:
        raise DocResolveError(
            f"未知的 doc_id: {doc_id!r}，"
            f"支持的前缀见 DOC_TYPE_MAP（{sorted(DOC_TYPE_MAP.keys())[:5]}...）"
        )

    doc_type = DOC_TYPE_MAP[doc_id]
    doc_dir = os.path.join(project_root, "docs", doc_type)

    if not os.path.isdir(doc_dir):
        raise DocResolveError(f"文档目录不存在: {doc_dir}")

    candidates: List[str] = []
    for pattern in _candidate_filenames(doc_id):
        for path in sorted(glob.glob(os.path.join(doc_dir, pattern))):
            if path not in candidates:
                candidates.append(path)

    if not candidates:
        raise DocResolveError(
            f"在 {doc_dir} 下未找到匹配 {doc_id}-*.md 的文件"
        )

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


def _extract_section_from_lines(
    lines: List[str], start_idx: int, level: int
) -> str:
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

    异常:
      RefParseError:       引用格式非法
      DocResolveError:     doc_id 无法定位文件
      SectionNotFoundError: 章节/条目在文件中不存在
    """
    doc_id, section_path, item_id = parse_ref(ref)
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
