"""Cross-document consistency validation.

Checks semantic alignment across the document set (PRD, ARCH, UI-SPEC,
DEV-PLAN) — AC traceability, API contract alignment, coverage matrix.
Single-document structure checks live in ``doc_review.checker``; this
module focuses exclusively on inter-document relationships.
"""

from __future__ import annotations

import sys
from pathlib import Path

from cataforge.core.types import Severity
from cataforge.skill.builtins._shared import Issue, IssueCollector
from cataforge.skill.builtins.doc_consistency._checks import _CrossDocChecksMixin
from cataforge.skill.builtins.doc_consistency._parse import (
    _find_docs,
    _read_all_content,
)
from cataforge.utils.common import ensure_utf8


class CrossDocChecker(_CrossDocChecksMixin):
    """Cross-document semantic consistency checker (Layer 1)."""

    def __init__(self, docs_dir: str = "docs/", quiet: bool = False) -> None:
        self.docs_dir = Path(docs_dir)
        self._issues = IssueCollector()
        self._quiet = quiet
        self._docs = _find_docs(self.docs_dir)
        self._content: dict[str, str] = {}
        for doc_type, paths in self._docs.items():
            self._content[doc_type] = _read_all_content(paths)
        self._kg_active: set[str] | None = None  # lazily resolved per-doc_type set

    @property
    def errors(self) -> list[Issue]:
        return self._issues.blocking

    @property
    def warnings(self) -> list[Issue]:
        return self._issues.advisory

    def _issue(
        self,
        severity: str,
        category: str,
        message: str,
    ) -> None:
        self._issues.add(Severity(severity), category, message)
        if not self._quiet:
            print(f"{severity}: [{category}] {message}")

    def _has_content(self, doc_type: str) -> bool:
        return bool(self._content.get(doc_type, "").strip())

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
