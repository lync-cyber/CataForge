"""Cross-document consistency validation.

Checks semantic alignment across the document set (PRD, ARCH, UI-SPEC,
DEV-PLAN) — AC traceability, API contract alignment, coverage matrix.
Single-document structure checks live in ``doc_review.checker``; this
module focuses exclusively on inter-document relationships.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

from cataforge.utils.common import ensure_utf8
from cataforge.utils.frontmatter import split_yaml_frontmatter as _split_fm
from cataforge.utils.yaml_parser import parse_yaml_frontmatter

_ITEM_ID_RE = re.compile(r"^### ([A-Z]+-\d+)", re.MULTILINE)
_AC_ID_RE = re.compile(r"AC-(\d+)")
_F_ID_RE = re.compile(r"F-(\d+)")
_M_ID_RE = re.compile(r"M-(\d+)")
_API_ID_RE = re.compile(r"API-(\d+)")
_T_ID_RE = re.compile(r"T-(\d+)")
_C_ID_RE = re.compile(r"C-(\d+)")
_P_ID_RE = re.compile(r"P-(\d+)")
_E_ID_RE = re.compile(r"E-(\d+)")


def _strip_code_blocks(text: str) -> str:
    return re.sub(r"```.*?```", "", text, flags=re.DOTALL)


def _load_doc(path: Path) -> tuple[dict[str, Any], str]:
    """Return (frontmatter_dict, body_text) for a markdown doc."""
    content = path.read_text(encoding="utf-8")
    fm = parse_yaml_frontmatter(content) or {}
    _, body = _split_fm(content)
    return fm, body if body else content


def _find_docs(docs_dir: Path) -> dict[str, list[Path]]:
    """Discover documents grouped by doc_type."""
    result: dict[str, list[Path]] = {
        "prd": [],
        "arch": [],
        "ui-spec": [],
        "dev-plan": [],
    }
    for doc_type, paths in result.items():
        type_dir = docs_dir / doc_type
        if type_dir.is_dir():
            for f in sorted(type_dir.glob("*.md")):
                paths.append(f)
        for f in sorted(docs_dir.glob(f"{doc_type}*.md")):
            if f not in paths:
                paths.append(f)
    return result


def _extract_sections(content: str, prefix: str) -> dict[str, str]:
    """Extract item sections keyed by ID (e.g. 'F-001' -> section text)."""
    pattern = rf"^### ({prefix}-\d+).*?(?=^### [A-Z]+-\d+|^## |\Z)"
    result: dict[str, str] = {}
    for m in re.finditer(pattern, content, re.MULTILINE | re.DOTALL):
        result[m.group(1)] = m.group(0)
    return result


def _extract_all_ids(content: str, prefix: str) -> set[str]:
    """Extract all item IDs with a given prefix from text."""
    return set(re.findall(rf"{prefix}-\d+", _strip_code_blocks(content)))


def _read_all_content(paths: list[Path]) -> str:
    """Concatenate content of all files."""
    parts = []
    for p in paths:
        try:
            parts.append(p.read_text(encoding="utf-8"))
        except OSError:
            continue
    return "\n".join(parts)


class CrossDocChecker:
    """Validates cross-document consistency."""

    def __init__(self, docs_dir: str = "docs/", quiet: bool = False) -> None:
        self.docs_dir = Path(docs_dir)
        self.errors: list[dict[str, str]] = []
        self.warnings: list[dict[str, str]] = []
        self._quiet = quiet
        self._docs = _find_docs(self.docs_dir)
        self._content: dict[str, str] = {}
        for doc_type, paths in self._docs.items():
            self._content[doc_type] = _read_all_content(paths)
        self._kg_active: set[str] | None = None  # lazily resolved per-doc_type set

    def _issue(
        self,
        severity: str,
        category: str,
        message: str,
    ) -> None:
        entry = {"severity": severity, "category": category, "message": message}
        if severity in ("CRITICAL", "HIGH"):
            self.errors.append(entry)
        else:
            self.warnings.append(entry)
        if not self._quiet:
            print(f"{severity}: [{category}] {message}")

    def _has_content(self, doc_type: str) -> bool:
        return bool(self._content.get(doc_type, "").strip())

    # ---- KG dispatch helpers ----

    def _project_root(self) -> Path | None:
        """Heuristically resolve project root from ``docs_dir``.

        Mirrors the resolver in `doc_review.checker` — `docs_dir` is
        usually `<project_root>/docs/`; the parent is the project root.
        Returns None when the path doesn't look like a CataForge project.
        """
        docs_path = self.docs_dir.resolve()
        candidate = docs_path.parent
        if (candidate / ".cataforge").exists():
            return candidate
        if (docs_path / ".cataforge").exists():
            return docs_path
        return None

    def _active_doc_types(self) -> set[str]:
        """Resolve the active doc_type set once and cache.

        Returns the empty set when KG dispatch is unavailable (no project
        root, no `_dispatch` import, no store on disk) so callers can use
        ``if "prd" in self._active_doc_types()`` uniformly.
        """
        if self._kg_active is not None:
            return self._kg_active
        project_root = self._project_root()
        if project_root is None:
            self._kg_active = set()
            return self._kg_active
        store_path = project_root / ".cataforge" / "kg" / "store"
        if not store_path.exists():
            self._kg_active = set()
            return self._kg_active
        try:
            from cataforge.kg._dispatch import active_doc_types  # noqa: PLC0415

            self._kg_active = set(active_doc_types(project_root))
        except ImportError:
            self._kg_active = set()
        return self._kg_active

    def _kg_uncovered_acs(self, downstream_doc_type: str) -> set[str] | None:
        """Return PRD ACs not referenced from ``downstream_doc_type`` via KG.

        Uses the ingested ``cf:source_doc`` slot to enumerate ACs sourced
        in PRD docs, then queries for any AC entity whose IRI appears in
        a triple originating from an entity sourced in the downstream
        doc_type. Returns ``None`` to signal "fall through to regex" when
        either doc_type is not in the active set or the KG query fails.
        """
        active = self._active_doc_types()
        if "prd" not in active or downstream_doc_type not in active:
            return None
        project_root = self._project_root()
        if project_root is None:
            return None
        try:
            from cataforge.kg import KnowledgeGraph  # noqa: PLC0415
            from cataforge.kg._dispatch import kg_config_for  # noqa: PLC0415
        except ImportError:
            return None

        cfg = kg_config_for(project_root)
        try:
            from cataforge.kg._sparql_utils import cf_namespace  # noqa: PLC0415

            with KnowledgeGraph.connect(cfg) as kg:
                ns = cf_namespace(cfg)
                prd_q = (
                    f"PREFIX cf: <{ns}> "
                    "SELECT DISTINCT ?eid WHERE { "
                    "  ?s cf:entity_id ?eid ; "
                    "     cf:source_doc ?src . "
                    '  FILTER(STRSTARTS(STR(?eid), "AC-")) '
                    '  FILTER(CONTAINS(STR(?src), "prd")) '
                    "}"
                )
                downstream_q = (
                    f"PREFIX cf: <{ns}> "
                    "SELECT DISTINCT ?ac_id WHERE { "
                    "  ?src cf:source_doc ?src_doc . "
                    f'  FILTER(CONTAINS(STR(?src_doc), "{downstream_doc_type}")) '
                    "  ?src ?p ?ac . "
                    "  ?ac cf:entity_id ?ac_id . "
                    '  FILTER(STRSTARTS(STR(?ac_id), "AC-")) '
                    "}"
                )
                prd_acs = {
                    str(row["eid"].value)  # type: ignore[union-attr]
                    for row in kg.store.query(prd_q)
                    if row["eid"] is not None  # type: ignore[index]
                }
                referenced = {
                    str(row["ac_id"].value)  # type: ignore[union-attr]
                    for row in kg.store.query(downstream_q)
                    if row["ac_id"] is not None  # type: ignore[index]
                }
        except Exception:
            return None
        if not prd_acs:
            return None  # no ACs ingested; let regex handle
        return prd_acs - referenced

    # ---- PRD → ARCH consistency ----

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

        prd_content = _strip_code_blocks(self._content["prd"])
        arch_content = _strip_code_blocks(self._content["arch"])

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
        arch_content = _strip_code_blocks(self._content["arch"])

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

    # ---- ARCH → DEV-PLAN consistency ----

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

        devplan_no_code = _strip_code_blocks(devplan_content)
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
        devplan_content = _strip_code_blocks(self._content["dev-plan"])

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

    # ---- PRD → DEV-PLAN AC traceability ----

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

        prd_content = _strip_code_blocks(self._content["prd"])
        devplan_content = _strip_code_blocks(self._content["dev-plan"])

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

    # ---- PRD → UI-SPEC consistency ----

    def check_prd_uispec_user_facing_coverage(self) -> None:
        """User-facing PRD features should have UI-SPEC page/component."""
        if not self._has_content("prd") or not self._has_content("ui-spec"):
            return
        prd_content = self._content["prd"]
        uispec_content = _strip_code_blocks(self._content["ui-spec"])

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

    # ---- Cross-set checks ----

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

    # ---- Traceability matrix ----

    def build_traceability_matrix(self) -> list[dict[str, str]]:
        """Build the F-NNN traceability matrix across all doc types."""
        if not self._has_content("prd"):
            return []
        prd_content = self._content["prd"]
        arch_content = _strip_code_blocks(self._content.get("arch", ""))
        devplan_content = _strip_code_blocks(self._content.get("dev-plan", ""))
        uispec_content = _strip_code_blocks(self._content.get("ui-spec", ""))

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

    # ---- Orchestration ----

    def run(self) -> int:
        """Run all cross-document checks. Return 0/1/2 per exit semantics."""
        available = [dt for dt in ("prd", "arch", "ui-spec", "dev-plan") if self._has_content(dt)]
        if len(available) < 2:
            print(f"跳过: 仅发现 {len(available)} 个文档类型，跨文档校验需要至少 2 个")
            return 0

        print(f"跨文档一致性校验: 发现 {', '.join(available)}")
        print()

        self.check_prd_arch_ac_coverage()
        self.check_prd_arch_nfr_mapping()
        self.check_prd_arch_priority_alignment()
        self.check_arch_devplan_api_contract()
        self.check_arch_devplan_entity_propagation()
        self.check_prd_devplan_ac_traceability()
        self.check_prd_devplan_ac_granularity()
        self.check_prd_uispec_user_facing_coverage()
        self.check_orphaned_components()

        matrix = self.build_traceability_matrix()
        if matrix:
            print()
            print("=== 需求追踪矩阵 ===")
            print(
                "| Feature | ACs | ARCH Module | ARCH API "
                "| DEV-PLAN Task | UI-SPEC Page | Coverage |"
            )
            print("|" + "|".join(["---"] * 7) + "|")
            for row in matrix:
                print(
                    f"| {row['feature']} | {row['ac_count']} "
                    f"| {row['arch_modules']} | {row['arch_apis']} "
                    f"| {row['devplan_tasks']} | {row['uispec_pages']} "
                    f"| {row['coverage']} |"
                )

            missing_count = sum(1 for r in matrix if r["coverage"] == "missing")
            partial_count = sum(1 for r in matrix if r["coverage"] == "partial")
            if missing_count > 0:
                print(
                    f"\n覆盖缺口: {missing_count} missing, {partial_count} partial "
                    f"/ {len(matrix)} total"
                )

        print()
        if self.errors:
            print(f"CRITICAL/HIGH: {len(self.errors)} 项")
            return 1
        if self.warnings:
            print(f"MEDIUM/LOW: {len(self.warnings)} 项 (无阻塞问题)")
            return 2
        print("PASS: 跨文档一致性校验全部通过")
        return 0


def main() -> None:
    ensure_utf8()
    docs_dir = "docs/"
    if len(sys.argv) > 1:
        docs_dir = sys.argv[1]
    checker = CrossDocChecker(docs_dir)
    sys.exit(checker.run())


if __name__ == "__main__":
    main()
