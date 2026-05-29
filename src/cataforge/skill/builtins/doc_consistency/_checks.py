"""Cross-document consistency checks (mixin for CrossDocChecker)."""

from __future__ import annotations

import re

from cataforge.skill.builtins.doc_consistency._parse import (
    _extract_all_ids,
    _extract_sections,
)
from cataforge.utils.md_parse import strip_code_blocks


class _CrossDocChecksMixin:
    """Per-relationship cross-doc checks. Mixed into :class:`CrossDocChecker`;
    relies on the host class for ``self.docs`` / ``self._issue`` / state."""

    def check_prd_arch_ac_coverage(self) -> None:
        """PRD AC-NNN should be referenced or semantically covered in ARCH."""
        if not self._has_content("prd") or not self._has_content("arch"):
            return

        kg_missing = self._kg_uncovered_acs("arch")
        if kg_missing is not None:
            if kg_missing:
                display = ", ".join(sorted(kg_missing)[:8])
                suffix = f" (共 {len(kg_missing)} 项)" if len(kg_missing) > 8 else ""
                self._issue(
                    "HIGH",
                    "ac-traceability",
                    f"PRD 中 {len(kg_missing)} 个 AC 未在 ARCH 中引用: {display}{suffix}",
                )
            return

        prd_content = strip_code_blocks(self._content["prd"])
        arch_content = strip_code_blocks(self._content["arch"])

        prd_acs = set(re.findall(r"AC-\d+", prd_content))
        if not prd_acs:
            return

        arch_acs = set(re.findall(r"AC-\d+", arch_content))
        missing = prd_acs - arch_acs
        if missing:
            display = ", ".join(sorted(missing)[:8])
            suffix = f" (共 {len(missing)} 项)" if len(missing) > 8 else ""
            self._issue(
                "HIGH",
                "ac-traceability",
                f"PRD 中 {len(missing)} 个 AC 未在 ARCH 中引用: {display}{suffix}",
            )

    def check_prd_arch_nfr_mapping(self) -> None:
        """PRD non-functional requirements should map to ARCH §5."""
        if not self._has_content("prd") or not self._has_content("arch"):
            return
        prd_content = self._content["prd"]
        arch_content = self._content["arch"]

        nfr_match = re.search(r"## 3\.\s*非功能需求(.*?)(?=\n## \d|\Z)", prd_content, re.DOTALL)
        if not nfr_match:
            return

        nfr_text = nfr_match.group(1)
        nfr_keywords = []
        for line in nfr_text.splitlines():
            line = line.strip()
            if line.startswith(("-", "*", "###")) and len(line) > 5:
                nfr_keywords.append(line.lstrip("-*# ").split(":", 1)[0].strip()[:30])

        if not nfr_keywords:
            return

        arch_nfa_match = re.search(
            r"## 5\.\s*非功能架构(.*?)(?=\n## \d|\Z)", arch_content, re.DOTALL
        )
        if not arch_nfa_match:
            self._issue(
                "MEDIUM",
                "nfr-mapping",
                "PRD 含非功能需求但 ARCH 缺少 §5 非功能架构章节",
            )

    def check_prd_arch_priority_alignment(self) -> None:
        """PRD P0 features should not be optional in ARCH."""
        if not self._has_content("prd") or not self._has_content("arch"):
            return
        prd_content = self._content["prd"]
        arch_content = strip_code_blocks(self._content["arch"])

        p0_features: set[str] = set()
        f_sections = _extract_sections(prd_content, "F")
        for f_id, section in f_sections.items():
            if re.search(r"P0|优先级.*?P0|Priority.*?P0", section):
                p0_features.add(f_id)

        if not p0_features:
            return

        for f_id in p0_features:
            if f_id not in arch_content:
                self._issue(
                    "CRITICAL",
                    "priority-alignment",
                    f"PRD P0 功能 {f_id} 在 ARCH 中完全缺失",
                )

    def check_arch_devplan_api_contract(self) -> None:
        """ARCH API endpoint paths should match DEV-PLAN AC descriptions."""
        if not self._has_content("arch") or not self._has_content("dev-plan"):
            return
        arch_content = self._content["arch"]
        devplan_content = self._content["dev-plan"]

        api_sections = _extract_sections(arch_content, "API")
        if not api_sections:
            return

        endpoint_re = re.compile(r"(GET|POST|PUT|PATCH|DELETE)\s+(/[\w/{}\-]+)", re.IGNORECASE)
        arch_endpoints: dict[str, set[str]] = {}
        for api_id, section in api_sections.items():
            endpoints = set()
            for m in endpoint_re.finditer(section):
                endpoints.add(f"{m.group(1).upper()} {m.group(2)}")
            if endpoints:
                arch_endpoints[api_id] = endpoints

        if not arch_endpoints:
            return

        devplan_no_code = strip_code_blocks(devplan_content)
        all_devplan_endpoints: set[str] = set()
        for m in endpoint_re.finditer(devplan_no_code):
            all_devplan_endpoints.add(f"{m.group(1).upper()} {m.group(2)}")

        for api_id, endpoints in arch_endpoints.items():
            for ep in endpoints:
                method, path = ep.split(" ", 1)
                path_base = re.sub(r"\{[^}]+\}", "*", path)
                found = False
                for dep in all_devplan_endpoints:
                    dep_method, dep_path = dep.split(" ", 1)
                    dep_path_base = re.sub(r"\{[^}]+\}", "*", dep_path)
                    if dep_method == method and dep_path_base == path_base:
                        found = True
                        break
                if not found:
                    self._issue(
                        "HIGH",
                        "api-contract",
                        f"ARCH {api_id} 定义 {ep} 在 DEV-PLAN 中未找到对应端点引用",
                    )

    def check_arch_devplan_entity_propagation(self) -> None:
        """ARCH entity IDs should be referenced in DEV-PLAN tasks."""
        if not self._has_content("arch") or not self._has_content("dev-plan"):
            return
        arch_content = self._content["arch"]
        devplan_content = strip_code_blocks(self._content["dev-plan"])

        arch_entities = _extract_all_ids(arch_content, "E")
        if not arch_entities:
            return

        missing = {e for e in arch_entities if e not in devplan_content}
        if missing:
            display = ", ".join(sorted(missing)[:5])
            self._issue(
                "MEDIUM",
                "entity-propagation",
                f"ARCH 实体 {display} 未在 DEV-PLAN 任务中引用",
            )

    def check_prd_devplan_ac_traceability(self) -> None:
        """Every PRD AC-NNN should appear in DEV-PLAN tdd_acceptance."""
        if not self._has_content("prd") or not self._has_content("dev-plan"):
            return

        kg_missing = self._kg_uncovered_acs("dev-plan")
        if kg_missing is not None:
            if kg_missing:
                display = ", ".join(sorted(kg_missing)[:8])
                suffix = f" (共 {len(kg_missing)} 项)" if len(kg_missing) > 8 else ""
                self._issue(
                    "HIGH",
                    "ac-traceability",
                    f"PRD 中 {len(kg_missing)} 个 AC 未传播到 DEV-PLAN: {display}{suffix}",
                )
            return

        prd_content = strip_code_blocks(self._content["prd"])
        devplan_content = strip_code_blocks(self._content["dev-plan"])

        prd_acs = set(re.findall(r"AC-\d+", prd_content))
        if not prd_acs:
            return

        devplan_acs = set(re.findall(r"AC-\d+", devplan_content))
        missing = prd_acs - devplan_acs
        if missing:
            display = ", ".join(sorted(missing)[:8])
            suffix = f" (共 {len(missing)} 项)" if len(missing) > 8 else ""
            self._issue(
                "HIGH",
                "ac-traceability",
                f"PRD 中 {len(missing)} 个 AC 未传播到 DEV-PLAN: {display}{suffix}",
            )

    def check_prd_devplan_ac_granularity(self) -> None:
        """Each PRD feature's AC count should roughly match DEV-PLAN coverage."""
        if not self._has_content("prd") or not self._has_content("dev-plan"):
            return
        prd_content = self._content["prd"]
        devplan_content = self._content["dev-plan"]

        f_sections = _extract_sections(prd_content, "F")
        t_sections = _extract_sections(devplan_content, "T")

        if not f_sections or not t_sections:
            return

        for f_id, f_section in f_sections.items():
            prd_ac_count = len(re.findall(r"AC-\d+", f_section))
            if prd_ac_count == 0:
                continue

            related_tasks = [t_text for t_text in t_sections.values() if f_id in t_text]
            if not related_tasks:
                continue

            devplan_ac_count = 0
            for t_text in related_tasks:
                devplan_ac_count += len(re.findall(r"AC-\d+", t_text))

            if devplan_ac_count > 0 and devplan_ac_count < prd_ac_count * 0.5:
                self._issue(
                    "MEDIUM",
                    "ac-granularity",
                    f"{f_id} 在 PRD 中有 {prd_ac_count} 个 AC，"
                    f"但对应 DEV-PLAN 任务仅覆盖 {devplan_ac_count} 个",
                )

    def check_prd_uispec_user_facing_coverage(self) -> None:
        """User-facing PRD features should have UI-SPEC page/component."""
        if not self._has_content("prd") or not self._has_content("ui-spec"):
            return
        prd_content = self._content["prd"]
        uispec_content = strip_code_blocks(self._content["ui-spec"])

        ui_verbs = re.compile(
            r"显示|渲染|展示|输入|点击|导航|页面|表单|列表|弹窗|对话框"
            r"|display|render|show|input|click|navigate|page|form|list|modal|dialog",
            re.IGNORECASE,
        )

        f_sections = _extract_sections(prd_content, "F")
        for f_id, section in f_sections.items():
            if not ui_verbs.search(section):
                continue
            if f_id not in uispec_content:
                self._issue(
                    "MEDIUM",
                    "ui-coverage",
                    f"PRD 中 user-facing 功能 {f_id} 未在 UI-SPEC 中找到对应覆盖",
                )

    def check_orphaned_components(self) -> None:
        """UI-SPEC components should be referenced by at least one page."""
        if not self._has_content("ui-spec"):
            return
        content = self._content["ui-spec"]
        c_ids = _extract_all_ids(content, "C")
        p_sections_text = "\n".join(_extract_sections(content, "P").values())

        if not c_ids or not p_sections_text:
            return

        orphaned = {c for c in c_ids if c not in p_sections_text}
        if orphaned:
            display = ", ".join(sorted(orphaned)[:5])
            self._issue(
                "MEDIUM",
                "orphaned-component",
                f"UI-SPEC 组件 {display} 未被任何页面引用",
            )

    def build_traceability_matrix(self) -> list[dict[str, str]]:
        """Build the F-NNN traceability matrix across all doc types."""
        if not self._has_content("prd"):
            return []
        prd_content = self._content["prd"]
        arch_content = strip_code_blocks(self._content.get("arch", ""))
        devplan_content = strip_code_blocks(self._content.get("dev-plan", ""))
        uispec_content = strip_code_blocks(self._content.get("ui-spec", ""))

        f_sections = _extract_sections(prd_content, "F")
        matrix: list[dict[str, str]] = []

        for f_id in sorted(f_sections.keys()):
            section = f_sections[f_id]
            ac_count = len(re.findall(r"AC-\d+", section))

            arch_modules = (
                sorted(
                    m
                    for m in _extract_all_ids(arch_content, "M")
                    if f_id in _extract_sections(arch_content, "M").get(m, "")
                )
                if arch_content
                else []
            )

            arch_apis = (
                sorted(
                    a
                    for a in _extract_all_ids(arch_content, "API")
                    if f_id in _extract_sections(arch_content, "API").get(a, "")
                )
                if arch_content
                else []
            )

            devplan_tasks = (
                sorted(
                    t
                    for t in _extract_all_ids(devplan_content, "T")
                    if f_id in _extract_sections(devplan_content, "T").get(t, "")
                )
                if devplan_content
                else []
            )

            uispec_pages = (
                sorted(
                    p
                    for p in _extract_all_ids(uispec_content, "P")
                    if f_id in _extract_sections(uispec_content, "P").get(p, "")
                )
                if uispec_content
                else []
            )

            has_arch = bool(arch_modules or arch_apis)
            has_devplan = bool(devplan_tasks)
            has_uispec = bool(uispec_pages) or not self._has_content("ui-spec")

            if has_arch and has_devplan and has_uispec:
                coverage = "full"
            elif has_arch or has_devplan:
                coverage = "partial"
            else:
                coverage = "missing"

            matrix.append(
                {
                    "feature": f_id,
                    "ac_count": str(ac_count),
                    "arch_modules": ", ".join(arch_modules) or "—",
                    "arch_apis": ", ".join(arch_apis) or "—",
                    "devplan_tasks": ", ".join(devplan_tasks) or "—",
                    "uispec_pages": ", ".join(uispec_pages) or "—",
                    "coverage": coverage,
                }
            )

        return matrix
