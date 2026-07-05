"""Cross-document consistency checks (mixin for CrossDocChecker)."""

from __future__ import annotations

import re
from abc import abstractmethod

from cataforge.runtime.skill.builtins.doc_consistency._parse import (
    _extract_all_ids,
    _extract_sections,
)
from cataforge.utils.md_parse import strip_code_blocks


def _ids_referencing(content: str, kind: str, f_id: str) -> list[str]:
    """Sorted IDs of ``kind`` whose own section mentions ``f_id`` (``[]`` if no content)."""
    if not content:
        return []
    sections = _extract_sections(content, kind)
    return sorted(i for i in _extract_all_ids(content, kind) if f_id in sections.get(i, ""))


def _classify_coverage(has_arch: bool, has_devplan: bool, has_uispec: bool) -> str:
    if has_arch and has_devplan and has_uispec:
        return "full"
    if has_arch or has_devplan:
        return "partial"
    return "missing"


class _CrossDocChecksMixin:
    """Per-relationship cross-doc checks. Mixed into :class:`CrossDocChecker`;
    relies on the host class for ``self.docs`` / ``self._issue`` / state."""

    _content: dict[str, str]

    @abstractmethod
    def _has_content(self, doc_type: str) -> bool: ...

    @abstractmethod
    def _kg_uncovered_acs(self, downstream_doc_type: str) -> set[str] | None: ...

    @abstractmethod
    def _kg_devplan_ac_coverage(self) -> tuple[dict[str, set[str]], set[str], set[str]] | None: ...

    @abstractmethod
    def _issue(self, severity: str, category: str, message: str) -> None: ...

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

        # arch traces to Features, not ACs directly: an AC is covered when its
        # parent PRD Feature is referenced in ARCH, or (legacy) the AC id itself
        # appears. Falls back to direct AC presence for ACs outside any F section.
        ac_parent: dict[str, str] = {}
        for f_id, section in _extract_sections(prd_content, "F").items():
            for ac in re.findall(r"AC-\d+", section):
                ac_parent[ac] = f_id

        covered = {
            ac
            for ac in prd_acs
            if ac in arch_content
            or (ac_parent.get(ac) is not None and ac_parent[ac] in arch_content)
        }
        missing = prd_acs - covered
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
        """ARCH entity IDs should reach DEV-PLAN tasks, directly or via the
        owning module: a task that references M-xxx covers every entity that
        module's ARCH section manages."""
        if not self._has_content("arch") or not self._has_content("dev-plan"):
            return
        arch_content = self._content["arch"]
        devplan_content = strip_code_blocks(self._content["dev-plan"])

        arch_entities = _extract_all_ids(arch_content, "E")
        if not arch_entities:
            return

        m_sections = _extract_sections(arch_content, "M")
        missing = set()
        for e in arch_entities:
            if e in devplan_content:
                continue
            owning_modules = {m_id for m_id, text in m_sections.items() if e in text}
            if any(m_id in devplan_content for m_id in owning_modules):
                continue
            missing.add(e)
        if missing:
            display = ", ".join(sorted(missing)[:5])
            self._issue(
                "MEDIUM",
                "entity-propagation",
                f"ARCH 实体 {display} 未在 DEV-PLAN 任务中引用",
            )

    def check_prd_devplan_ac_traceability(self) -> None:
        """Every PRD AC should reach DEV-PLAN.

        A bare ``AC-NNN`` id is only comparable across documents when the PRD
        numbers ACs in one global sequence. When the same id recurs under
        multiple features (per-feature local numbering), the token diff is
        meaningless, so coverage reads at feature level: every feature that
        carries ACs must be referenced by the DEV-PLAN (per-AC depth is
        covered by :meth:`check_prd_devplan_ac_granularity`).
        """
        if not self._has_content("prd") or not self._has_content("dev-plan"):
            return

        kg_cov = self._kg_devplan_ac_coverage()
        if kg_cov is not None:
            self._report_devplan_ac_gap(*kg_cov)
            return

        prd_content = strip_code_blocks(self._content["prd"])
        devplan_content = strip_code_blocks(self._content["dev-plan"])

        ac_parents: dict[str, set[str]] = {ac: set() for ac in re.findall(r"AC-\d+", prd_content)}
        if not ac_parents:
            return
        for f_id, section in _extract_sections(prd_content, "F").items():
            for ac in re.findall(r"AC-\d+", section):
                ac_parents.setdefault(ac, set()).add(f_id)

        referenced_acs = set(re.findall(r"AC-\d+", devplan_content))
        features_with_acs = set().union(*ac_parents.values()) if ac_parents else set()
        referenced_features = {f for f in features_with_acs if f in devplan_content}
        self._report_devplan_ac_gap(ac_parents, referenced_acs, referenced_features)

    def _report_devplan_ac_gap(
        self,
        ac_parents: dict[str, set[str]],
        referenced_acs: set[str],
        referenced_features: set[str],
    ) -> None:
        if not ac_parents:
            return
        local_numbering = any(len(parents) > 1 for parents in ac_parents.values())
        if local_numbering:
            features_with_acs: set[str] = set().union(*ac_parents.values())
            uncovered = sorted(features_with_acs - referenced_features)
            if uncovered:
                display = ", ".join(uncovered[:8])
                suffix = f" (共 {len(uncovered)} 项)" if len(uncovered) > 8 else ""
                self._issue(
                    "HIGH",
                    "ac-traceability",
                    f"PRD 中 {len(uncovered)} 个 feature 的 AC 未传播到 DEV-PLAN: "
                    f"{display}{suffix}",
                )
            return
        missing = set(ac_parents) - referenced_acs
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
        """User-facing PRD features should have UI-SPEC page/component.

        A feature section may declare its delivery surface with a
        ``delivery: ui | api | dev-tooling`` field line — a non-``ui`` surface
        is exempt from UI coverage regardless of verb heuristics; ``ui``
        requires coverage even without them. Without the field, the verb
        heuristic decides.
        """
        if not self._has_content("prd") or not self._has_content("ui-spec"):
            return
        prd_content = self._content["prd"]
        uispec_content = strip_code_blocks(self._content["ui-spec"])

        ui_verbs = re.compile(
            r"显示|渲染|展示|输入|点击|导航|页面|表单|列表|弹窗|对话框"
            r"|display|render|show|input|click|navigate|page|form|list|modal|dialog",
            re.IGNORECASE,
        )
        delivery_field = re.compile(
            r"^\s*[-*]?\s*\**(?:delivery|交付面)\**\s*[:：]\s*([a-z-]+)",
            re.IGNORECASE | re.MULTILINE,
        )

        f_sections = _extract_sections(prd_content, "F")
        for f_id, section in f_sections.items():
            declared = delivery_field.search(section)
            if declared is not None:
                if declared.group(1).lower() != "ui":
                    continue
            elif not ui_verbs.search(section):
                continue
            if f_id not in uispec_content:
                self._issue(
                    "MEDIUM",
                    "ui-coverage",
                    f"PRD 中 user-facing 功能 {f_id} 未在 UI-SPEC 中找到对应覆盖",
                )

    def check_orphaned_components(self) -> None:
        """UI-SPEC components should be referenced somewhere beyond their own
        section — a page, another component's trigger declaration, or the
        prose/tables outside any UC section (e.g. the master component list)."""
        if not self._has_content("ui-spec"):
            return
        content = self._content["ui-spec"]
        c_ids = _extract_all_ids(content, "UC")
        if not c_ids:
            return

        uc_sections = _extract_sections(content, "UC")
        orphaned = set()
        for c in c_ids:
            own = uc_sections.get(c, "")
            if content.count(c) - own.count(c) <= 0:
                orphaned.add(c)
        if orphaned:
            display = ", ".join(sorted(orphaned)[:5])
            self._issue(
                "MEDIUM",
                "orphaned-component",
                f"UI-SPEC 组件 {display} 未被任何页面或组件引用",
            )

    def build_traceability_matrix(self) -> list[dict[str, str]]:
        """Build the F-NNN traceability matrix across all doc types."""
        if not self._has_content("prd"):
            return []
        arch_content = strip_code_blocks(self._content.get("arch", ""))
        devplan_content = strip_code_blocks(self._content.get("dev-plan", ""))
        uispec_content = strip_code_blocks(self._content.get("ui-spec", ""))
        f_sections = _extract_sections(self._content["prd"], "F")

        matrix: list[dict[str, str]] = []
        for f_id in sorted(f_sections):
            arch_modules = _ids_referencing(arch_content, "M", f_id)
            arch_apis = _ids_referencing(arch_content, "API", f_id)
            devplan_tasks = _ids_referencing(devplan_content, "T", f_id)
            uispec_pages = _ids_referencing(uispec_content, "P", f_id)

            has_uispec = bool(uispec_pages) or not self._has_content("ui-spec")
            coverage = _classify_coverage(
                bool(arch_modules or arch_apis), bool(devplan_tasks), has_uispec
            )
            matrix.append(
                {
                    "feature": f_id,
                    "ac_count": str(len(re.findall(r"AC-\d+", f_sections[f_id]))),
                    "arch_modules": ", ".join(arch_modules) or "—",
                    "arch_apis": ", ".join(arch_apis) or "—",
                    "devplan_tasks": ", ".join(devplan_tasks) or "—",
                    "uispec_pages": ", ".join(uispec_pages) or "—",
                    "coverage": coverage,
                }
            )
        return matrix
