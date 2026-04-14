"""Document-type-specific validation rules (PRD, ARCH, …)."""

from __future__ import annotations

import re
from collections import defaultdict


class TypedDocChecksMixin:
    """Mixin providing ``check_<doc_type>`` methods used by ``DocChecker``."""

    # ---- PRD ----

    def check_prd(self) -> None:
        if self.volume_type == "main":
            f_count = len(re.findall(r"^### F-\d+", self.content, re.MULTILINE))
            us_count = len(re.findall(r"用户故事|User Story", self.content))
            if f_count > us_count:
                self.fail(f"{f_count}个功能仅{us_count}个有用户故事")
        if self.volume_type == "main":
            ac_count = len(re.findall(r"AC-\d+", self.content))
            if ac_count == 0:
                self.fail("无验收标准 (AC-NNN)")
        if self.volume_type in ("main",):
            nfr_match = re.search(
                r"## 3\. 非功能需求(.*?)(?=\n## \d|\Z)", self.content, re.DOTALL
            )
            if not nfr_match or len(nfr_match.group(1).strip().splitlines()) < 3:
                self.fail("非功能需求章节过短 (至少3行)")
        f_sections = re.findall(
            r"^### F-\d+.*?(?=^### F-\d+|^## |\Z)",
            self.content,
            re.MULTILINE | re.DOTALL,
        )
        missing_priority = sum(
            1
            for section in f_sections
            if not re.search(r"优先级.*?P[012]|Priority.*?P[012]", section)
        )
        if missing_priority > 0:
            self.fail(f"{missing_priority}个功能缺少优先级标注 (P0/P1/P2)")

    # ---- ARCH ----

    def check_arch(self) -> None:
        if self.volume_type in ("main", "api"):
            api_sections = re.findall(
                r"^### API-\d+.*?(?=^### API-\d+|^## |\Z)",
                self.content,
                re.MULTILINE | re.DOTALL,
            )
            missing_request = sum(
                1
                for section in api_sections
                if not re.search(r"type:\s*event-stream", section)
                and not re.search(r"request:", section)
            )
            if missing_request > 0:
                self.fail(f"{len(api_sections)}个API中{missing_request}个缺少request定义")
        if self.volume_type in ("main", "modules"):
            m_sections = re.findall(
                r"^### M-\d+.*?(?=^### M-\d+|^## |\Z)",
                self.content,
                re.MULTILINE | re.DOTALL,
            )
            missing_mapping = sum(
                1 for section in m_sections if not re.search(r"F-\d+", section)
            )
            if missing_mapping > 0:
                self.fail(f"{missing_mapping}个模块缺少功能映射 (F-NNN引用)")
        if self.volume_type in ("main", "data"):
            e_sections = re.findall(
                r"^### E-\d+.*?(?=^### E-\d+|^## |\Z)",
                self.content,
                re.MULTILINE | re.DOTALL,
            )
            missing_fields = sum(1 for section in e_sections if "|" not in section)
            if missing_fields > 0:
                self.fail(f"{missing_fields}个实体缺少字段定义表")
        if self.volume_type == "main":
            tech_table = re.search(
                r"技术栈(.*?)(?=^## |\Z)", self.content, re.DOTALL | re.MULTILINE
            )
            if tech_table:
                rows = re.findall(r"^\|(?![-\s])", tech_table.group(1), re.MULTILINE)
                for row in rows:
                    if "选型理由" not in row and row.count("|") >= 4:
                        cells = [c.strip() for c in row.split("|")]
                        if sum(1 for c in cells if c == "") > 2:
                            self.warn("技术栈表格可能有空的选型理由")

    # ---- DEV-PLAN ----

    def check_dev_plan(self) -> None:
        t_count = len(re.findall(r"^### T-\d+", self.content, re.MULTILINE))
        t_sections = re.findall(
            r"^### T-\d+.*?(?=^### T-\d+|^## |\Z)",
            self.content,
            re.MULTILINE | re.DOTALL,
        )
        missing_deliverables = sum(
            1
            for s in t_sections
            if not re.search(r"deliverables|交付物", s, re.IGNORECASE)
        )
        missing_tdd = sum(
            1
            for s in t_sections
            if not re.search(r"tdd_acceptance|验收标准", s, re.IGNORECASE)
        )
        missing_context = sum(
            1 for s in t_sections if not re.search(r"context_load", s, re.IGNORECASE)
        )
        if missing_deliverables > 0:
            self.fail(f"{t_count}个任务中{missing_deliverables}个缺少deliverables定义")
        if missing_tdd > 0:
            self.fail(f"{t_count}个任务中{missing_tdd}个缺少tdd_acceptance定义")
        if missing_context > 0:
            self.warn(f"{t_count}个任务中{missing_context}个缺少context_load定义")
        deps: dict[str, list[str]] = defaultdict(list)
        for line in self.lines:
            dep_match = re.match(r"\s*(T-\d+)\s*[─→>\-]+\s*(T-\d+)", line)
            if dep_match:
                deps[dep_match.group(2)].append(dep_match.group(1))
        if deps:
            visited: set[str] = set()
            path_set: set[str] = set()

            def has_cycle(node: str) -> bool:
                if node in path_set:
                    return True
                if node in visited:
                    return False
                visited.add(node)
                path_set.add(node)
                for dep in deps.get(node, []):
                    if has_cycle(dep):
                        return True
                path_set.discard(node)
                return False

            all_nodes = set(deps.keys())
            for vs in deps.values():
                all_nodes.update(vs)
            if any(has_cycle(n) for n in all_nodes):
                self.fail("依赖图存在循环")

    # ---- UI-SPEC ----

    def check_ui_spec(self) -> None:
        if self.volume_type == "main":
            if not re.search(r"##\s*0\.\s*设计方向", self.content):
                self.fail("缺少§0设计方向章节")
            else:
                dir_match = re.search(
                    r"##\s*0\.\s*设计方向(.*?)(?=^## |\Z)",
                    self.content,
                    re.MULTILINE | re.DOTALL,
                )
                if dir_match and re.search(
                    r"\{.*调性.*\}|\{.*关键词.*\}", dir_match.group(1)
                ):
                    self.fail("§0设计方向仍为占位符，未填写实际内容")
        c_sections = re.findall(
            r"^### C-\d+.*?(?=^### C-\d+|^### P-\d+|^## |\Z)",
            self.content,
            re.MULTILINE | re.DOTALL,
        )
        c_count = len(c_sections)
        mv = sum(
            1 for s in c_sections if not re.search(r"变体|variant", s, re.IGNORECASE)
        )
        mp = sum(
            1 for s in c_sections if not re.search(r"Props|props|属性", s, re.IGNORECASE)
        )
        vd_pat = r"视觉差异|视觉变化|visual diff"
        mvd = sum(1 for s in c_sections if not re.search(vd_pat, s, re.IGNORECASE))
        if mv > 0:
            self.fail(f"{c_count}个组件中{mv}个缺少变体定义")
        if mp > 0:
            self.fail(f"{c_count}个组件中{mp}个缺少Props定义")
        if mvd > 0:
            self.warn(f"{c_count}个组件中{mvd}个缺少状态视觉差异描述")
        p_sections = re.findall(
            r"^### P-\d+.*?(?=^### P-\d+|^## |\Z)",
            self.content,
            re.MULTILINE | re.DOTALL,
        )
        p_count = len(p_sections)
        mr = sum(
            1 for s in p_sections if not re.search(r"路由|route|/\w+", s, re.IGNORECASE)
        )
        mc = sum(
            1 for s in p_sections if not re.search(r"C-\d+|组件", s, re.IGNORECASE)
        )
        sp_pat = r"空间构成|视觉重心|留白"
        ms = sum(1 for s in p_sections if not re.search(sp_pat, s, re.IGNORECASE))
        if mr > 0:
            self.fail(f"{p_count}个页面中{mr}个缺少路由定义")
        if mc > 0:
            self.fail(f"{p_count}个页面中{mc}个缺少组件引用")
        if ms > 0:
            self.warn(f"{p_count}个页面中{ms}个缺少空间构成说明")
        if self.volume_type == "main":
            if not re.search(r"色彩|[Cc]olor", self.content):
                self.warn("设计系统缺少色彩定义")
            if not re.search(r"排版|[Tt]ypography", self.content):
                self.warn("设计系统缺少排版定义")
            color_tokens = re.findall(
                r"\|\s*\S+.*?\|.*?#[0-9a-fA-F]{3,8}", self.content
            )
            if 0 < len(color_tokens) < 5:
                self.warn(
                    f"仅定义了{len(color_tokens)}个色彩Token，建议至少包含主色、语义色和中性色"
                )

    # ---- TEST-REPORT ----

    def check_test_report(self) -> None:
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
        table_match = re.search(
            r"^## .*测试用例矩阵(.*?)(?=^## |\Z)",
            self.content,
            re.DOTALL | re.MULTILINE,
        )
        if table_match:
            rows = re.findall(r"^\|(?![-\s])", table_match.group(1), re.MULTILINE)
            if max(0, len(rows) - 1) == 0:
                self.fail("测试用例矩阵为空 (无数据行)")
        cov_match = re.search(
            r"^## .*覆盖率目标(.*?)(?=^## |\Z)",
            self.content,
            re.DOTALL | re.MULTILINE,
        )
        if cov_match and not re.search(r"\d+%", cov_match.group(1)):
            self.warn("覆盖率目标缺少具体数值 (如 80%)")

    # ---- DEPLOY-SPEC ----

    def check_deploy_spec(self) -> None:
        build_match = re.search(
            r"^## .*构建流程(.*?)(?=^## |\Z)",
            self.content,
            re.DOTALL | re.MULTILINE,
        )
        if build_match and len(build_match.group(1).strip()) < 10:
            self.fail("构建流程章节内容过短")
        env_match = re.search(
            r"^## .*环境配置(.*?)(?=^## |\Z)",
            self.content,
            re.DOTALL | re.MULTILINE,
        )
        if env_match:
            env_text = env_match.group(1)
            if not (
                re.search(r"dev|开发", env_text, re.IGNORECASE)
                and re.search(r"prod|生产", env_text, re.IGNORECASE)
            ):
                self.warn("环境配置应至少包含 dev 和 prod 环境")
        checklist_match = re.search(
            r"^## .*发布检查清单(.*?)(?=^## |\Z)",
            self.content,
            re.DOTALL | re.MULTILINE,
        )
        if checklist_match:
            checks = re.findall(r"\[[ x]\]", checklist_match.group(1))
            if len(checks) < 2:
                self.fail("发布检查清单过少 (至少2项)")

    # ---- RESEARCH ----

    def check_research(self) -> None:
        if not re.search(
            r"web-search|doc-lookup|user-interview", self.content, re.IGNORECASE
        ):
            self.warn("调研方法未指明具体模式 (web-search/doc-lookup/user-interview)")
        conclusion_match = re.search(
            r"## 结论(.*?)(?=^## |\Z)", self.content, re.DOTALL | re.MULTILINE
        )
        if conclusion_match and len(conclusion_match.group(1).strip()) < 10:
            self.fail("结论章节内容过短")

    # ---- CHANGELOG ----

    def check_changelog(self) -> None:
        versions = re.findall(r"## \[([^\]]+)\]", self.content)
        if not versions:
            self.fail("CHANGELOG 无版本条目")
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
