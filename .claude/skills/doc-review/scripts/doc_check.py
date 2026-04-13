#!/usr/bin/env python3
"""doc_check.py — 文档结构自动检查

用法: python doc_check.py <doc-type> <doc-file> [--docs-dir docs/] [--volume-type <type>]
doc-type: prd | arch | dev-plan | ui-spec | test-report | deploy-spec | research | changelog
volume-type: main | features | api | data | modules | sprint | components | pages
返回: exit 0=全部通过, exit 1=有失败项
"""

import json
import os
import sys
import re
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "scripts"))
from _common import build_template_path_map, get_constant

# ========================================
# 分卷常量
# ========================================

VOLUME_TYPES = {
    "main",
    "features",
    "api",
    "data",
    "modules",
    "sprint",
    "components",
    "pages",
}

# 模板目录路径 (相对于本脚本)
_SCRIPT_DIR = Path(__file__).resolve().parent
_TEMPLATES_DIR = _SCRIPT_DIR.parent.parent / "doc-gen" / "templates"

# doc_type → {volume_type → template_filename} 映射
# 从 _registry.yaml 动态构建
_TEMPLATE_MAP: dict[str, dict[str, str]] = build_template_path_map()


def _parse_required_sections(headings: list[str]) -> list[tuple[str, str]]:
    """将 heading 列表 (如 ["## 1. 概述"]) 转为 (heading, name) 元组列表。"""
    result = []
    for h in headings:
        # 从 "## 1. 概述" 提取 "概述"；从 "## 问题" 提取 "问题"
        m = re.match(r"##\s+(?:\d+\.\s*)?(.+)", h)
        name = m.group(1).strip() if m else h.replace("## ", "").strip()
        result.append((h, name))
    return result


def _load_template_required_sections(
    doc_type: str, volume_type: str
) -> list[tuple[str, str]] | None:
    """从模板文件的 YAML Front Matter required_sections 字段读取必填章节列表。
    返回 None 表示未找到对应模板或模板中无 required_sections 声明。"""
    type_map = _TEMPLATE_MAP.get(doc_type)
    if not type_map:
        return None
    filename = type_map.get(volume_type)
    if not filename:
        return None
    template_path = _TEMPLATES_DIR / filename
    try:
        content = template_path.read_text(encoding="utf-8")
    except OSError:
        return None
    # Parse YAML Front Matter
    fm_match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not fm_match:
        return None
    fm_text = fm_match.group(1)
    # Extract required_sections list from YAML
    headings: list[str] = []
    in_required_sections = False
    for line in fm_text.splitlines():
        if re.match(r"^required_sections\s*:", line):
            in_required_sections = True
            # Check for inline list: required_sections: ["## 1. Foo"]
            inline = re.search(r":\s*(\[.*\])", line)
            if inline:
                try:
                    headings = json.loads(inline.group(1))
                except json.JSONDecodeError:
                    pass
                break
            continue
        if in_required_sections:
            list_item = re.match(r'^\s+-\s+"(.*)"', line) or re.match(
                r"^\s+-\s+'(.*)'", line
            )
            if list_item:
                headings.append(list_item.group(1))
            elif re.match(r"^\s+-\s+", line):
                # Unquoted list item
                val = re.match(r"^\s+-\s+(.*)", line)
                if val:
                    headings.append(val.group(1).strip())
            else:
                break  # End of list
    if not headings:
        return None
    return _parse_required_sections(headings)


def read_file(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


class DocChecker:
    def __init__(
        self,
        doc_type: str,
        doc_file: str,
        docs_dir: str = "docs/",
        volume_type: str | None = None,
        quiet: bool = False,
    ):
        self.doc_type = doc_type
        self.doc_file = doc_file
        self.docs_dir = docs_dir
        self.content = read_file(doc_file)
        self.lines = self.content.splitlines()
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self._quiet = quiet
        # volume_type: 外部传入优先，否则自动检测
        self.volume_type = volume_type or self._detect_volume_type()

    @staticmethod
    def _parse_yaml_frontmatter(content: str) -> dict:
        """从文档内容中解析 YAML Front Matter，返回字典。"""
        fm_match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
        if not fm_match:
            return {}
        result: dict = {}
        current_key = None
        current_list: list | None = None
        for line in fm_match.group(1).splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.startswith("- ") and current_key and current_list is not None:
                val = stripped[2:].strip().strip('"').strip("'")
                current_list.append(val)
                result[current_key] = current_list
                continue
            colon_idx = stripped.find(":")
            if colon_idx > 0:
                key = stripped[:colon_idx].strip()
                val_part = stripped[colon_idx + 1 :].strip()
                if not val_part:
                    current_key = key
                    current_list = []
                    result[key] = current_list
                    continue
                current_key = key
                current_list = None
                if val_part.startswith("[") and val_part.endswith("]"):
                    items = val_part[1:-1].split(",")
                    result[key] = [
                        i.strip().strip('"').strip("'") for i in items if i.strip()
                    ]
                else:
                    result[key] = val_part.strip('"').strip("'")
        return result

    def _detect_volume_type(self) -> str:
        """从 YAML Front Matter 的 volume_type 字段提取 volume type，回退到文件名模式匹配，默认返回 main"""
        fm = self._parse_yaml_frontmatter(self.content)
        vt = fm.get("volume_type", "")
        if vt and vt in VOLUME_TYPES:
            return vt
        # volume 字段作为次选（main 文档的 volume 值）
        vol = fm.get("volume", "")
        if vol and vol in VOLUME_TYPES:
            return vol
        # 文件名模式回退
        stem = Path(self.doc_file).stem
        filename_patterns = [
            (r"-api$", "api"),
            (r"-data$", "data"),
            (r"-modules$", "modules"),
            (r"-s\d+$", "sprint"),
            (r"-f\d+-f\d+$", "features"),
            (r"-p\d+-p\d+$", "pages"),
            (r"-c\d+-c\d+$", "components"),
        ]
        for pattern, vol_type in filename_patterns:
            if re.search(pattern, stem):
                return vol_type
        return "main"

    def fail(self, msg: str):
        self.errors.append(msg)
        if not self._quiet:
            print(f"FAIL: {msg}")

    def warn(self, msg: str):
        self.warnings.append(msg)
        if not self._quiet:
            print(f"WARN: {msg}")

    # ========================================
    # 通用检查
    # ========================================

    def check_meta(self):
        """检查文档头 YAML Front Matter 元数据完整性: id, author, status, deps, consumers"""
        fm = self._parse_yaml_frontmatter(self.content)
        if not fm:
            self.fail("缺少 YAML Front Matter (---...---)")
            return
        if not fm.get("id"):
            self.fail("缺少文档ID (YAML id 字段)")
        if not fm.get("author"):
            self.fail("缺少author字段")
        status = fm.get("status", "")
        if status not in ("draft", "review", "approved"):
            self.fail(f"status字段无效: {status!r} (需为 draft|review|approved)")
        if "deps" not in fm:
            self.fail("缺少deps字段")
        if "consumers" not in fm:
            if self.doc_type not in ("research", "changelog"):
                self.fail("缺少consumers字段")

    def check_nav_block(self):
        """检查[NAV]块存在且与实际章节一致"""
        # CHANGELOG 和 RESEARCH-NOTE 不需要 NAV 块
        if self.doc_type in ("changelog", "research"):
            return

        nav_match = re.search(r"\[NAV\](.*?)\[/NAV\]", self.content, re.DOTALL)
        if not nav_match:
            self.fail("缺少[NAV]...[/NAV]块")
            return

        # 提取 NAV 中声明的顶级章节号 (§1, §2, ...)
        nav_text = nav_match.group(1)
        nav_sections = re.findall(r"§(\d+)", nav_text)
        nav_top_sections = sorted(set(nav_sections))

        # 提取文档中实际的顶级 ## 章节号
        actual_sections = re.findall(r"^## (\d+)\.", self.content, re.MULTILINE)
        actual_top_sections = sorted(set(actual_sections))

        if nav_top_sections and actual_top_sections:
            if nav_top_sections != actual_top_sections:
                self.warn(
                    f"[NAV]块章节({','.join('§' + s for s in nav_top_sections)}) "
                    f"与实际章节({','.join('§' + s for s in actual_top_sections)})不一致"
                )

    def check_no_todo(self):
        """检查无未处理 TODO/TBD/FIXME (标注[ASSUMPTION]的除外)"""
        todo_count = len(re.findall(r"TODO|TBD|FIXME", self.content))
        assumption_count = len(re.findall(r"\[ASSUMPTION\]", self.content))
        remaining = todo_count - assumption_count
        if remaining > 0:
            self.fail(f"{remaining}个未处理TODO/TBD/FIXME")

    # 已知的文档类型前缀 — 仅这些前缀的交叉引用会被校验
    KNOWN_DOC_PREFIXES = {
        "prd",
        "arch",
        "dev-plan",
        "ui-spec",
        "test-report",
        "deploy-spec",
        "research-note",
        "changelog",
    }

    @staticmethod
    def _strip_code_blocks(text: str) -> str:
        """剔除代码块(```...```)内容，避免代码示例中的编号被误判为文档引用"""
        return re.sub(r"```.*?```", "", text, flags=re.DOTALL)

    def check_line_count(self):
        """检查文档总行数是否超过 DOC_SPLIT_THRESHOLD_LINES 阈值"""
        threshold = get_constant("DOC_SPLIT_THRESHOLD_LINES", 300)
        line_count = len(self.lines)
        if line_count > threshold:
            self.warn(
                f"文档行数({line_count})超过{threshold}行阈值，建议通过doc-gen拆分为分卷"
            )

    def check_xref(self):
        """检查交叉引用目标文件存在 (仅校验已知文档类型前缀)"""
        # 剔除代码块内容，避免代码示例中的F-001/M-001等编号被误判
        content_no_code = self._strip_code_blocks(self.content)
        refs = re.findall(r"([\w-]+)#([\w§.\-]+)", content_no_code)
        docs_path = Path(self.docs_dir)
        if not docs_path.exists():
            return
        for doc_id, _section in refs:
            # 跳过模板占位符
            if "{" in doc_id or "}" in doc_id:
                continue
            # 仅校验已知文档类型前缀，避免误匹配代码片段(如 C#, CSS#)
            prefix = doc_id.split("-")[0] if "-" in doc_id else doc_id
            if (
                prefix not in self.KNOWN_DOC_PREFIXES
                and doc_id not in self.KNOWN_DOC_PREFIXES
            ):
                continue
            # 先在当前 docs_dir 查找
            matches = list(docs_path.glob(f"{doc_id}*"))
            if not matches:
                # 递归搜索子目录 (适配 docs/{doc_type}/ 结构)
                matches = list(docs_path.glob(f"**/{doc_id}*"))
            if not matches:
                # 向上查找父目录 (当 docs_dir 是子目录时)
                parent = docs_path.parent
                if parent != docs_path:
                    matches = list(parent.glob(f"**/{doc_id}*"))
            if not matches:
                self.fail(f"交叉引用目标 {doc_id} 未找到对应文件")

    def check_required_sections(self):
        """检查必填章节非空 (从模板 frontmatter 的 required_sections 读取)"""
        sections = _load_template_required_sections(self.doc_type, self.volume_type)

        if sections is None:
            # 模板不可用时跳过检查并警告
            if self.doc_type not in ("changelog",):
                self.warn(
                    f"无法从模板加载 required_sections "
                    f"(doc_type={self.doc_type}, volume_type={self.volume_type})"
                )
            return

        for heading, name in sections:
            pattern = re.escape(heading)
            match = re.search(
                pattern + r"(.*?)(?=^## |\Z)", self.content, re.DOTALL | re.MULTILINE
            )
            if not match:
                self.fail(f"缺少必填章节: {name}")
            elif len(match.group(1).strip()) == 0:
                self.fail(f"必填章节为空: {name}")

    def check_id_continuity(self):
        """检查ID编号连续无跳号"""
        id_patterns = {
            "prd": [("F", r"F-(\d+)"), ("AC", r"AC-(\d+)")],
            "arch": [
                ("M", r"M-(\d+)"),
                ("API", r"API-(\d+)"),
                ("E", r"E-(\d+)"),
            ],
            "dev-plan": [("T", r"T-(\d+)")],
            "ui-spec": [("C", r"C-(\d+)"), ("P", r"P-(\d+)")],
        }
        patterns = id_patterns.get(self.doc_type, [])
        for prefix, pattern in patterns:
            ids = [int(m) for m in re.findall(pattern, self.content)]
            if not ids:
                continue
            ids_sorted = sorted(set(ids))
            expected = list(range(ids_sorted[0], ids_sorted[-1] + 1))
            missing = set(expected) - set(ids_sorted)
            if missing:
                missing_str = ", ".join(
                    f"{prefix}-{str(m).zfill(3)}" for m in sorted(missing)
                )
                self.warn(f"ID编号不连续, 缺少: {missing_str}")

    def check_nav_index_registered(self):
        """检查文档是否已注册到 NAV-INDEX"""
        docs_path = Path(self.docs_dir)
        # 在当前 docs_dir 查找 NAV-INDEX.md
        nav_index_path = docs_path / "NAV-INDEX.md"
        if not nav_index_path.exists():
            # 向上级目录查找 (当 docs_dir 是子目录如 docs/prd/ 时)
            parent = docs_path.parent
            nav_index_path = parent / "NAV-INDEX.md"
            if not nav_index_path.exists():
                # 再向上一级
                grandparent = parent.parent
                nav_index_path = grandparent / "NAV-INDEX.md"
        if not nav_index_path.exists():
            self.warn("NAV-INDEX.md不存在，无法验证注册状态")
            return
        nav_content = nav_index_path.read_text(encoding="utf-8")
        doc_filename = Path(self.doc_file).name
        # 从 YAML Front Matter 获取文档 ID
        fm = self._parse_yaml_frontmatter(self.content)
        doc_id = fm.get("id", "")
        if doc_filename not in nav_content and doc_id not in nav_content:
            self.warn(f"文档未注册到NAV-INDEX (文件={doc_filename}, ID={doc_id})")

    # ========================================
    # 分卷检查
    # ========================================

    def check_split_header(self):
        """非 main 分卷必须有 split_from 字段（YAML Front Matter）"""
        if self.volume_type != "main":
            fm = self._parse_yaml_frontmatter(self.content)
            if not fm.get("split_from"):
                self.fail(f"分卷文档 (volume={self.volume_type}) 缺少 split_from 字段")

    def check_split_consistency(self):
        """main 卷检查: 同目录下相关分卷文件是否在主卷中被引用"""
        if self.volume_type != "main":
            return
        doc_dir = Path(self.doc_file).parent
        doc_stem = Path(self.doc_file).stem  # e.g. arch-myproject-v1
        # glob 同目录下同前缀的分卷文件
        volume_files = [
            f
            for f in doc_dir.glob(f"{doc_stem}-*")
            if f.name != Path(self.doc_file).name and f.suffix == ".md"
        ]
        for vf in volume_files:
            # 检查分卷文件名或其stem是否在主卷中被提及
            if vf.stem not in self.content and vf.name not in self.content:
                self.warn(f"主卷未引用分卷文件: {vf.name}")

    # ========================================
    # PRD 专项检查
    # ========================================

    def check_prd(self):
        # 用户故事覆盖 (仅主卷检查，features 分卷不要求完整用户故事)
        if self.volume_type == "main":
            f_count = len(re.findall(r"^### F-\d+", self.content, re.MULTILINE))
            us_count = len(re.findall(r"用户故事|User Story", self.content))
            if f_count > us_count:
                self.fail(f"{f_count}个功能仅{us_count}个有用户故事")

        # 验收标准存在 (仅主卷检查)
        if self.volume_type == "main":
            ac_count = len(re.findall(r"AC-\d+", self.content))
            if ac_count == 0:
                self.fail("无验收标准 (AC-NNN)")

        # 非功能需求章节充实度 (仅主卷或未拆分文档检查)
        if self.volume_type in ("main",):
            nfr_match = re.search(
                r"## 3\. 非功能需求(.*?)(?=\n## \d|\Z)", self.content, re.DOTALL
            )
            if not nfr_match or len(nfr_match.group(1).strip().splitlines()) < 3:
                self.fail("非功能需求章节过短 (至少3行)")

        # 优先级标注
        f_sections = re.findall(
            r"^### F-\d+.*?(?=^### F-\d+|^## |\Z)",
            self.content,
            re.MULTILINE | re.DOTALL,
        )
        missing_priority = 0
        for section in f_sections:
            if not re.search(r"优先级.*?P[012]|Priority.*?P[012]", section):
                missing_priority += 1
        if missing_priority > 0:
            self.fail(f"{missing_priority}个功能缺少优先级标注 (P0/P1/P2)")

    # ========================================
    # ARCH 专项检查
    # ========================================

    def check_arch(self):
        # API 定义完整 (仅 main 或 api 分卷检查)
        if self.volume_type in ("main", "api"):
            api_sections = re.findall(
                r"^### API-\d+.*?(?=^### API-\d+|^## |\Z)",
                self.content,
                re.MULTILINE | re.DOTALL,
            )
            missing_request = 0
            for section in api_sections:
                is_event_stream = re.search(r"type:\s*event-stream", section)
                has_request = re.search(r"request:", section)
                if not is_event_stream and not has_request:
                    missing_request += 1
            if missing_request > 0:
                self.fail(
                    f"{len(api_sections)}个API中{missing_request}个缺少request定义"
                )

        # 功能映射: 模块应引用 PRD 的 F-NNN (仅 main 或 modules 分卷检查)
        if self.volume_type in ("main", "modules"):
            m_sections = re.findall(
                r"^### M-\d+.*?(?=^### M-\d+|^## |\Z)",
                self.content,
                re.MULTILINE | re.DOTALL,
            )
            missing_mapping = 0
            for section in m_sections:
                if not re.search(r"F-\d+", section):
                    missing_mapping += 1
            if missing_mapping > 0:
                self.fail(f"{missing_mapping}个模块缺少功能映射 (F-NNN引用)")

        # 数据模型完整: 实体应有字段表 (仅 main 或 data 分卷检查)
        if self.volume_type in ("main", "data"):
            e_sections = re.findall(
                r"^### E-\d+.*?(?=^### E-\d+|^## |\Z)",
                self.content,
                re.MULTILINE | re.DOTALL,
            )
            missing_fields = 0
            for section in e_sections:
                if "|" not in section:  # 表格标记
                    missing_fields += 1
            if missing_fields > 0:
                self.fail(f"{missing_fields}个实体缺少字段定义表")

        # 选型理由 (仅主卷检查)
        if self.volume_type == "main":
            tech_table = re.search(
                r"技术栈(.*?)(?=^## |\Z)", self.content, re.DOTALL | re.MULTILINE
            )
            if tech_table:
                rows = re.findall(r"^\|(?![-\s])", tech_table.group(1), re.MULTILINE)
                for row in rows:
                    if "选型理由" not in row and row.count("|") >= 4:
                        cells = [c.strip() for c in row.split("|")]
                        empty_cells = [c for c in cells if c == ""]
                        if len(empty_cells) > 2:
                            self.warn("技术栈表格可能有空的选型理由")

    # ========================================
    # DEV-PLAN 专项检查
    # ========================================

    def check_dev_plan(self):
        # 任务数 vs 交付物
        t_count = len(re.findall(r"^### T-\d+", self.content, re.MULTILINE))
        t_sections = re.findall(
            r"^### T-\d+.*?(?=^### T-\d+|^## |\Z)",
            self.content,
            re.MULTILINE | re.DOTALL,
        )

        missing_deliverables = 0
        missing_tdd = 0
        missing_context = 0
        for section in t_sections:
            if not re.search(r"deliverables|交付物", section, re.IGNORECASE):
                missing_deliverables += 1
            if not re.search(r"tdd_acceptance|验收标准", section, re.IGNORECASE):
                missing_tdd += 1
            if not re.search(r"context_load", section, re.IGNORECASE):
                missing_context += 1

        if missing_deliverables > 0:
            self.fail(f"{t_count}个任务中{missing_deliverables}个缺少deliverables定义")
        if missing_tdd > 0:
            self.fail(f"{t_count}个任务中{missing_tdd}个缺少tdd_acceptance定义")
        if missing_context > 0:
            self.warn(f"{t_count}个任务中{missing_context}个缺少context_load定义")

        # 依赖环检测
        deps = defaultdict(list)
        for line in self.lines:
            dep_match = re.match(r"\s*(T-\d+)\s*[─→>\-]+\s*(T-\d+)", line)
            if dep_match:
                deps[dep_match.group(2)].append(dep_match.group(1))
        if deps:
            visited = set()
            path = set()

            def has_cycle(node):
                if node in path:
                    return True
                if node in visited:
                    return False
                visited.add(node)
                path.add(node)
                for dep in deps.get(node, []):
                    if has_cycle(dep):
                        return True
                path.discard(node)
                return False

            all_nodes = set(deps.keys())
            for vs in deps.values():
                all_nodes.update(vs)
            if any(has_cycle(n) for n in all_nodes):
                self.fail("依赖图存在循环")

    # ========================================
    # UI-SPEC 专项检查
    # ========================================

    def check_ui_spec(self):
        # 设计方向: §0 应存在且非空 (仅主卷检查)
        if self.volume_type == "main":
            if not re.search(r"##\s*0\.\s*设计方向", self.content):
                self.fail("缺少§0设计方向章节")
            else:
                # 检查设计方向章节是否有实际内容(非占位符)
                dir_match = re.search(
                    r"##\s*0\.\s*设计方向(.*?)(?=^## |\Z)",
                    self.content,
                    re.MULTILINE | re.DOTALL,
                )
                if dir_match:
                    dir_content = dir_match.group(1)
                    if re.search(r"\{.*调性.*\}|\{.*关键词.*\}", dir_content):
                        self.fail("§0设计方向仍为占位符，未填写实际内容")

        # 组件完整性: 每个 C-NNN 应有变体和 Props
        c_sections = re.findall(
            r"^### C-\d+.*?(?=^### C-\d+|^### P-\d+|^## |\Z)",
            self.content,
            re.MULTILINE | re.DOTALL,
        )
        missing_variants = 0
        missing_props = 0
        missing_visual_diff = 0
        for section in c_sections:
            if not re.search(r"变体|variant", section, re.IGNORECASE):
                missing_variants += 1
            if not re.search(r"Props|props|属性", section, re.IGNORECASE):
                missing_props += 1
            if not re.search(r"视觉差异|视觉变化|visual diff", section, re.IGNORECASE):
                missing_visual_diff += 1
        c_count = len(c_sections)
        if missing_variants > 0:
            self.fail(f"{c_count}个组件中{missing_variants}个缺少变体定义")
        if missing_props > 0:
            self.fail(f"{c_count}个组件中{missing_props}个缺少Props定义")
        if missing_visual_diff > 0:
            self.warn(f"{c_count}个组件中{missing_visual_diff}个缺少状态视觉差异描述")

        # 页面完整性: 每个 P-NNN 应有路由和组件引用
        p_sections = re.findall(
            r"^### P-\d+.*?(?=^### P-\d+|^## |\Z)",
            self.content,
            re.MULTILINE | re.DOTALL,
        )
        missing_route = 0
        missing_components = 0
        missing_spatial = 0
        for section in p_sections:
            if not re.search(r"路由|route|/\w+", section, re.IGNORECASE):
                missing_route += 1
            if not re.search(r"C-\d+|组件", section, re.IGNORECASE):
                missing_components += 1
            if not re.search(r"空间构成|视觉重心|留白", section, re.IGNORECASE):
                missing_spatial += 1
        p_count = len(p_sections)
        if missing_route > 0:
            self.fail(f"{p_count}个页面中{missing_route}个缺少路由定义")
        if missing_components > 0:
            self.fail(f"{p_count}个页面中{missing_components}个缺少组件引用")
        if missing_spatial > 0:
            self.warn(f"{p_count}个页面中{missing_spatial}个缺少空间构成说明")

        # 设计系统: 色彩/排版 token 应存在 (仅主卷检查)
        if self.volume_type == "main":
            if not re.search(r"色彩|[Cc]olor", self.content):
                self.warn("设计系统缺少色彩定义")
            if not re.search(r"排版|[Tt]ypography", self.content):
                self.warn("设计系统缺少排版定义")
            # 色彩Token数量检查: 至少应有主色、语义色、中性色
            color_tokens = re.findall(
                r"\|\s*\S+.*?\|.*?#[0-9a-fA-F]{3,8}", self.content
            )
            if 0 < len(color_tokens) < 5:
                self.warn(
                    f"仅定义了{len(color_tokens)}个色彩Token，建议至少包含主色、语义色(success/warning/error)和中性色"
                )

    # ========================================
    # TEST-REPORT 专项检查
    # ========================================

    def check_test_report(self):
        # 测试金字塔: 应包含 Unit/Integration/E2E
        has_unit = bool(re.search(r"[Uu]nit|单元", self.content))
        has_integration = bool(re.search(r"[Ii]ntegration|集成", self.content))
        has_e2e = bool(re.search(r"E2E|端到端", self.content))
        if not (has_unit and has_integration and has_e2e):
            missing = []
            if not has_unit:
                missing.append("Unit")
            if not has_integration:
                missing.append("Integration")
            if not has_e2e:
                missing.append("E2E")
            self.fail(f"测试金字塔缺少层次: {', '.join(missing)}")

        # 测试用例矩阵: 应有至少一条用例
        table_match = re.search(
            r"^## .*测试用例矩阵(.*?)(?=^## |\Z)",
            self.content,
            re.DOTALL | re.MULTILINE,
        )
        if table_match:
            rows = re.findall(r"^\|(?![-\s])", table_match.group(1), re.MULTILINE)
            # 减去表头行
            data_rows = max(0, len(rows) - 1)
            if data_rows == 0:
                self.fail("测试用例矩阵为空 (无数据行)")

        # 覆盖率目标: 应有具体数值
        cov_match = re.search(
            r"^## .*覆盖率目标(.*?)(?=^## |\Z)", self.content, re.DOTALL | re.MULTILINE
        )
        if cov_match:
            if not re.search(r"\d+%", cov_match.group(1)):
                self.warn("覆盖率目标缺少具体数值 (如 80%)")

    # ========================================
    # DEPLOY-SPEC 专项检查
    # ========================================

    def check_deploy_spec(self):
        # 构建流程: 应有具体命令或步骤
        build_match = re.search(
            r"^## .*构建流程(.*?)(?=^## |\Z)", self.content, re.DOTALL | re.MULTILINE
        )
        if build_match and len(build_match.group(1).strip()) < 10:
            self.fail("构建流程章节内容过短")

        # 环境配置: 应有至少 dev/prod 环境
        env_match = re.search(
            r"^## .*环境配置(.*?)(?=^## |\Z)", self.content, re.DOTALL | re.MULTILINE
        )
        if env_match:
            env_text = env_match.group(1)
            has_dev = bool(re.search(r"dev|开发", env_text, re.IGNORECASE))
            has_prod = bool(re.search(r"prod|生产", env_text, re.IGNORECASE))
            if not (has_dev and has_prod):
                self.warn("环境配置应至少包含 dev 和 prod 环境")

        # 发布检查清单: 应有检查项
        checklist_match = re.search(
            r"^## .*发布检查清单(.*?)(?=^## |\Z)",
            self.content,
            re.DOTALL | re.MULTILINE,
        )
        if checklist_match:
            checks = re.findall(r"\[[ x]\]", checklist_match.group(1))
            if len(checks) < 2:
                self.fail("发布检查清单过少 (至少2项)")

    # ========================================
    # RESEARCH-NOTE 专项检查
    # ========================================

    def check_research(self):
        # 应有调研方法
        if not re.search(
            r"web-search|doc-lookup|user-interview", self.content, re.IGNORECASE
        ):
            self.warn("调研方法未指明具体模式 (web-search/doc-lookup/user-interview)")

        # 应有结论
        conclusion_match = re.search(
            r"## 结论(.*?)(?=^## |\Z)", self.content, re.DOTALL | re.MULTILINE
        )
        if conclusion_match and len(conclusion_match.group(1).strip()) < 10:
            self.fail("结论章节内容过短")

    # ========================================
    # CHANGELOG 专项检查
    # ========================================

    def check_changelog(self):
        # 应有版本号
        versions = re.findall(r"## \[([^\]]+)\]", self.content)
        if not versions:
            self.fail("CHANGELOG 无版本条目")

        # 每个版本应有 Added/Changed/Fixed 之一
        for ver in versions:
            ver_match = re.search(
                re.escape(f"## [{ver}]") + r"(.*?)(?=^## \[|\Z)",
                self.content,
                re.DOTALL | re.MULTILINE,
            )
            if ver_match:
                section = ver_match.group(1)
                if not re.search(r"###\s*(Added|Changed|Fixed)", section):
                    self.warn(f"版本 [{ver}] 缺少 Added/Changed/Fixed 分类")

    # ========================================
    # 主执行
    # ========================================

    def run(self) -> int:
        print(
            f"检查: {self.doc_file} (type={self.doc_type}, volume={self.volume_type})"
        )

        # 通用检查
        self.check_meta()
        self.check_nav_block()
        self.check_no_todo()
        self.check_xref()
        self.check_line_count()
        self.check_required_sections()
        self.check_id_continuity()
        self.check_nav_index_registered()

        # 分卷检查
        self.check_split_header()
        self.check_split_consistency()

        # 专项检查
        checks = {
            "prd": self.check_prd,
            "arch": self.check_arch,
            "dev-plan": self.check_dev_plan,
            "ui-spec": self.check_ui_spec,
            "test-report": self.check_test_report,
            "deploy-spec": self.check_deploy_spec,
            "research": self.check_research,
            "changelog": self.check_changelog,
        }
        if self.doc_type in checks:
            checks[self.doc_type]()
        else:
            print(f"WARN: 未知的文档类型 '{self.doc_type}'，仅执行通用检查")

        # 结果
        if self.warnings:
            print(f"WARNINGS: {len(self.warnings)}")
        if not self.errors:
            print("PASS: 所有检查通过")
            return 0
        else:
            print(f"TOTAL FAILURES: {len(self.errors)}")
            return 1


def _ensure_utf8_stdio():
    """Wrap stdout/stderr with UTF-8 encoding on Windows (CLI use only)."""
    import io

    if sys.stdout.encoding != "utf-8":
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace"
        )
    if sys.stderr.encoding != "utf-8":
        sys.stderr = io.TextIOWrapper(
            sys.stderr.buffer, encoding="utf-8", errors="replace"
        )


if __name__ == "__main__":
    _ensure_utf8_stdio()
    if len(sys.argv) < 3:
        print(
            "用法: python doc_check.py <doc-type> <doc-file> [--docs-dir docs/] [--volume-type <type>]"
        )
        print(
            "doc-type: prd | arch | dev-plan | ui-spec | test-report | deploy-spec | research | changelog"
        )
        print(
            "volume-type: main | features | api | data | modules | sprint | components | pages"
        )
        sys.exit(2)

    doc_type = sys.argv[1]
    doc_file = sys.argv[2]
    docs_dir = "docs/"
    volume_type = None

    if "--docs-dir" in sys.argv:
        idx = sys.argv.index("--docs-dir")
        docs_dir = sys.argv[idx + 1]

    if "--volume-type" in sys.argv:
        idx = sys.argv.index("--volume-type")
        volume_type = sys.argv[idx + 1]

    checker = DocChecker(doc_type, doc_file, docs_dir, volume_type)
    sys.exit(checker.run())
