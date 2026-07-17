"""Document-type-specific validation rules (PRD, ARCH, …)."""

from __future__ import annotations

import re
from abc import abstractmethod
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from cataforge.core.markdown_sections import parse_markdown_table
from cataforge.utils.yaml_parser import parse_yaml_frontmatter

# AC observability heuristic — every tdd_acceptance entry should describe
# an externally-observable outcome (DOM update, return value, side
# effect). Verbs in this set indicate observability; their absence in an
# AC line is a WARN signal (not FAIL — some legitimately-internal ACs
# describe state machines whose only consumer is another internal
# component, and that's fine when the consumer test is itself observable).
_AC_OBSERVABLE_VERBS = (
    "渲染",
    "返回",
    "显示",
    "抛出",
    "存储",
    "发送",
    "触发",
    "写入",
    "导航",
    "挂载",
    "刷新",
    "更新",
    "记录",
    "落盘",
    "回调",
    "广播",
    "输出",
    "打印",
    "生成",
    "报错",
    "校验",
    "提示",
    "退出",
    "render",
    "return",
    "display",
    "throw",
    "store",
    "send",
    "emit",
    "write",
    "navigate",
    "mount",
    "refresh",
    "update",
    "log",
    "publish",
    "callback",
    "broadcast",
    "raise",
    "show",
    "hide",
    "print",
    "exit",
    "output",
)
_AC_OBSERVABLE_RE = re.compile(
    "(" + "|".join(re.escape(v) for v in _AC_OBSERVABLE_VERBS) + ")",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class _ArchSectionRule:
    """One ARCH per-section-kind requirement: the ``### {prefix}-NNN`` sections
    it inspects, when a section counts as missing the requirement, and the
    failure message built from (missing_ids, total)."""

    prefix: str
    is_missing: Callable[[str], bool]
    message: Callable[[list[str], int], str]


def _format_offending_ids(ids: list[str]) -> str:
    shown = ", ".join(ids[:5])
    suffix = f" (共 {len(ids)} 项)" if len(ids) > 5 else ""
    return f"{shown}{suffix}"


_ARCH_SECTION_RULES: tuple[_ArchSectionRule, ...] = (
    _ArchSectionRule(
        "API",
        lambda s: (
            not re.search(r"type:\s*event-stream", s)
            and not re.search(r"(?:request|input)\s*[:：]", s)
            and "参数" not in s
        ),
        lambda ids, total: (
            f"{total}个API中{len(ids)}个缺少入参定义 (request/input/参数): "
            f"{_format_offending_ids(ids)}"
        ),
    ),
    _ArchSectionRule(
        "M",
        lambda s: not re.search(r"F-\d+", s),
        lambda ids, total: (
            f"{len(ids)}个模块缺少功能映射 (F-NNN引用): {_format_offending_ids(ids)}"
        ),
    ),
    _ArchSectionRule(
        "E",
        lambda s: "|" not in s,
        lambda ids, total: f"{len(ids)}个实体缺少字段定义表: {_format_offending_ids(ids)}",
    ),
)


def _arch_sections(content: str, prefix: str) -> list[str]:
    return re.findall(
        rf"^### {prefix}-\d+.*?(?=^### {prefix}-\d+|^## |\Z)",
        content,
        re.MULTILINE | re.DOTALL,
    )


def _arch_section_id(section: str, prefix: str) -> str:
    m = re.match(rf"### ({prefix}-\d+)", section)
    return m.group(1) if m else f"{prefix}-?"


# Anchored to the field-line form (`- **task_kind**: validation`) so a prose
# mention of the enum value inside a feature card never exempts it.
_TASK_KIND_VALIDATION_RE = re.compile(
    r"^\s*[-*]\s*\**task_kind\**\s*[:：]\s*\**\s*validation\b",
    re.IGNORECASE | re.MULTILINE,
)


def _is_validation_card(section: str) -> bool:
    """A validation task card carries 验证清单 instead of TDD fields."""
    head, _, _rest = section.partition("\n")
    if "[VALIDATION]" in head.upper():
        return True
    return bool(_TASK_KIND_VALIDATION_RE.search(section))


class TypedDocChecksMixin:
    """Mixin providing ``check_<doc_type>`` methods used by ``DocChecker``."""

    content: str
    lines: list[str]

    @abstractmethod
    def fail(self, msg: str, category: str = "doc-structure") -> None: ...

    @abstractmethod
    def warn(self, msg: str, category: str = "doc-structure") -> None: ...

    @abstractmethod
    def _docs_root(self) -> Path: ...

    # ---- PRD ----

    def check_prd(self) -> None:
        f_count = len(re.findall(r"^### F-\d+", self.content, re.MULTILINE))
        us_count = len(re.findall(r"用户故事|User Story", self.content))
        if f_count > us_count:
            self.fail(f"{f_count}个功能仅{us_count}个有用户故事")
        ac_count = len(re.findall(r"AC-\d+", self.content))
        if ac_count == 0:
            self.fail("无验收标准 (AC-NNN)")
        nfr_match = re.search(r"## 3\. 非功能需求(.*?)(?=\n## \d|\Z)", self.content, re.DOTALL)
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
        for rule in _ARCH_SECTION_RULES:
            sections = _arch_sections(self.content, rule.prefix)
            missing_ids = [
                _arch_section_id(section, rule.prefix)
                for section in sections
                if rule.is_missing(section)
            ]
            if missing_ids:
                self.fail(rule.message(missing_ids, len(sections)))
        self._check_tech_stack_rationale()

    def _check_tech_stack_rationale(self) -> None:
        """WARN when the tech-stack table leaves 选型理由 cells blank.

        Anchors on a ``技术栈`` heading (not the NAV pointer that shares the
        word), reads the first pipe table under it, and flags data rows whose
        rationale column — the header containing ``理由`` — is empty. A table
        without such a column (the terser lite ``类别/选型/备注`` schema) carries
        no rationale requirement and is left alone.
        """
        for m in re.finditer(
            r"^#{2,4}\s+[^\n]*技术栈[^\n]*\n(.*?)(?=^#{2,4}\s|\Z)",
            self.content,
            re.MULTILINE | re.DOTALL,
        ):
            table = parse_markdown_table(m.group(1))
            if table is None:
                continue
            idx = next((i for i, h in enumerate(table.headers) if "理由" in h), None)
            if idx is None:
                continue
            missing = sum(1 for row in table.rows if idx >= len(row) or not row[idx].strip())
            if missing > 0:
                self.warn(f"技术栈表格{missing}行缺少选型理由")
            return

    # ---- DEV-PLAN ----

    def check_dev_plan(self) -> None:
        t_count = len(re.findall(r"^### T-\d+", self.content, re.MULTILINE))
        t_sections = re.findall(
            r"^### T-\d+.*?(?=^### T-\d+|^## |\Z)",
            self.content,
            re.MULTILINE | re.DOTALL,
        )
        # A validation card (task_kind: validation / [VALIDATION] heading) does
        # not enter TDD, so deliverables/tdd_acceptance requirements don't apply.
        tdd_sections = [s for s in t_sections if not _is_validation_card(s)]
        missing_deliverables = sum(
            1 for s in tdd_sections if not re.search(r"deliverables|交付物", s, re.IGNORECASE)
        )
        missing_tdd = sum(
            1 for s in tdd_sections if not re.search(r"tdd_acceptance|验收标准", s, re.IGNORECASE)
        )
        missing_context = sum(
            1 for s in t_sections if not re.search(r"context_load", s, re.IGNORECASE)
        )
        if missing_deliverables > 0:
            self.fail(f"{len(tdd_sections)}个TDD任务中{missing_deliverables}个缺少deliverables定义")
        if missing_tdd > 0:
            self.fail(f"{len(tdd_sections)}个TDD任务中{missing_tdd}个缺少tdd_acceptance定义")
        if missing_context > 0:
            self.warn(f"{t_count}个任务中{missing_context}个缺少context_load定义")
        self._check_ac_observability(t_sections)
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
        self._check_walking_skeleton()

    def _check_walking_skeleton(self) -> None:
        """Gate: arch-declared external_oracles require a walking-skeleton card.

        An oracle counts as declared only when an ``EO-NNN`` table row is
        filled in (template placeholder rows with ``{`` braces are ignored).
        """
        docs_root = self._docs_root()
        if not docs_root.exists():
            return
        oracle_ids: set[str] = set()
        for arch_file in sorted(docs_root.glob("**/arch*.md")):
            try:
                text = arch_file.read_text()
            except OSError:
                continue
            section = re.search(
                r"^#{2,3}[^\n]*external_oracles[^\n]*\n(.*?)(?=^#{1,3}\s|\Z)",
                text,
                re.MULTILINE | re.DOTALL,
            )
            if not section:
                continue
            for line in section.group(1).splitlines():
                m = re.match(r"\|\s*(EO-\d+)\s*\|", line)
                if m and "{" not in line:
                    oracle_ids.add(m.group(1))
        if not oracle_ids:
            return
        if re.search(r"walking_skeleton:\s*true", self.content):
            return
        self.fail(
            f"arch 声明外部消费边界({', '.join(sorted(oracle_ids))})但 dev-plan 无 "
            "`walking_skeleton: true` 任务卡——外部真值须在规模化前经真实通道验证，"
            "Sprint 1 应含穿透真实外部系统的最小端到端 tracer 卡",
            category="completeness",
        )

    def _check_ac_observability(self, t_sections: list[str]) -> None:
        """Flag AC entries that lack observable outcomes or GWT structure.

        Two checks per AC line:
        1. Observable verb heuristic — WARN when no verb from
           :data:`_AC_OBSERVABLE_VERBS` appears.
        2. Given-When-Then format — WARN when the AC line contains none
           of the GWT keywords, suggesting it may be a vague "implement X"
           style entry that cannot produce testable assertions.
        """
        unobservable: list[str] = []
        non_gwt: list[str] = []
        gwt_re = re.compile(
            r"\b(Given|When|Then|given|when|then|假设|当|则)\b",
        )
        for sec in t_sections:
            ac_block = re.search(
                r"(tdd_acceptance|验收标准)(.*?)(?=^[-*]\s+\*?\*?(?:deliverables|"
                r"交付物|context_load)|^### |\Z)",
                sec,
                re.IGNORECASE | re.DOTALL | re.MULTILINE,
            )
            if not ac_block:
                continue
            for line in ac_block.group(2).splitlines():
                ac_match = re.search(
                    r"AC-\d+\s*[:：]\s*(.+)",
                    line,
                )
                if not ac_match:
                    continue
                ac_text = ac_match.group(1).strip()
                if not ac_text:
                    continue
                if not _AC_OBSERVABLE_RE.search(ac_text):
                    unobservable.append(ac_text[:80])
                if not gwt_re.search(ac_text):
                    non_gwt.append(ac_text[:80])
        if unobservable:
            self.warn(
                f"{len(unobservable)}条AC描述无可观测动词（如 渲染/返回/抛出/写入），"
                f"建议补充DOM/返回值/副作用等可测终点；首条示例: "
                f"{unobservable[0]!r}"
            )
        if non_gwt:
            self.warn(
                f"{len(non_gwt)}条AC未采用Given-When-Then格式，"
                f"建议重写为 'Given {{前置条件}}, When {{动作}}, Then {{可观测结果}}'；"
                f"首条示例: {non_gwt[0]!r}"
            )

    # ---- UI-SPEC ----

    def _check_page_sections(self, content: str) -> None:
        """Check P-NNN page sections (only in non-lite mode)."""
        p_sections = re.findall(
            r"^### P-\d+.*?(?=^### P-\d+|^## |\Z)",
            content,
            re.MULTILINE | re.DOTALL,
        )
        p_count = len(p_sections)
        mr = sum(1 for s in p_sections if not re.search(r"路由|route|/\w+", s, re.IGNORECASE))
        mc = sum(1 for s in p_sections if not re.search(r"UC-\d+|组件", s, re.IGNORECASE))
        sp_pat = r"空间构成|视觉重心|留白"
        ms = sum(1 for s in p_sections if not re.search(sp_pat, s, re.IGNORECASE))
        if mr > 0:
            self.fail(f"{p_count}个页面中{mr}个缺少路由定义")
        if mc > 0:
            self.fail(f"{p_count}个页面中{mc}个缺少组件引用")
        if ms > 0:
            self.warn(f"{p_count}个页面中{ms}个缺少空间构成说明")

    def check_ui_spec(self) -> None:
        fm = parse_yaml_frontmatter(self.content)
        mode = fm.get("mode", "standard")
        is_lite = mode == "agile-lite"
        min_color_tokens = 3 if is_lite else 5

        if not is_lite:
            if not re.search(r"##\s*0\.\s*设计方向", self.content):
                self.fail("缺少§0设计方向章节")
            else:
                dir_match = re.search(
                    r"##\s*0\.\s*设计方向(.*?)(?=^## |\Z)",
                    self.content,
                    re.MULTILINE | re.DOTALL,
                )
                if dir_match and re.search(r"\{.*调性.*\}|\{.*关键词.*\}", dir_match.group(1)):
                    self.fail("§0设计方向仍为占位符，未填写实际内容")
        legacy_c = re.findall(r"^### C-\d+", self.content, re.MULTILINE)
        if legacy_c:
            self.fail(
                f"ui-spec 组件须用 UC- 前缀 (UIComponent)；发现 {len(legacy_c)} 个 C- 组件 "
                "heading (C-=arch Component，在 ui-spec 中不会被抽取为实体)",
                category="convention",
            )
        uc_sections = re.findall(
            r"^### UC-\d+.*?(?=^### UC-\d+|^### P-\d+|^## |\Z)",
            self.content,
            re.MULTILINE | re.DOTALL,
        )
        uc_count = len(uc_sections)
        mv = sum(1 for s in uc_sections if not re.search(r"变体|variant", s, re.IGNORECASE))
        mp = sum(1 for s in uc_sections if not re.search(r"Props|props|属性", s, re.IGNORECASE))
        vd_pat = r"视觉差异|视觉变化|visual diff"
        mvd = sum(1 for s in uc_sections if not re.search(vd_pat, s, re.IGNORECASE))
        if mv > 0:
            self.fail(f"{uc_count}个组件中{mv}个缺少变体定义")
        if mp > 0:
            self.fail(f"{uc_count}个组件中{mp}个缺少Props定义")
        if mvd > 0:
            self.warn(f"{uc_count}个组件中{mvd}个缺少状态视觉差异描述")
        if not is_lite:
            self._check_page_sections(self.content)
        if not re.search(r"色彩|[Cc]olor", self.content):
            self.warn("设计系统缺少色彩定义")
        if not re.search(r"排版|[Tt]ypography", self.content):
            self.warn("设计系统缺少排版定义")
        color_tokens = re.findall(r"\|\s*\S+.*?\|.*?#[0-9a-fA-F]{3,8}", self.content)
        if len(color_tokens) < min_color_tokens:
            mode_label = "agile-lite" if is_lite else "standard"
            if len(color_tokens) == 0:
                self.fail(
                    f"设计系统缺少色彩Token定义表（{mode_label}模式至少需要"
                    f"{min_color_tokens}个Token：主色、语义色、中性色）"
                )
            else:
                self.fail(
                    f"仅定义了{len(color_tokens)}个色彩Token，{mode_label}模式"
                    f"至少需要{min_color_tokens}个（主色、语义色、中性色）"
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
            table = parse_markdown_table(table_match.group(1))
            if table is None or not table.rows:
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
        if not re.search(r"web-search|doc-lookup|user-interview", self.content, re.IGNORECASE):
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
