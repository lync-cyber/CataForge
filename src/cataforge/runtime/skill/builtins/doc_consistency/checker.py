"""Cross-document consistency validation.

Checks semantic alignment across the document set (PRD, ARCH, UI-SPEC,
DEV-PLAN) — AC traceability, API contract alignment, coverage matrix.
Single-document structure checks live in ``doc_review.checker``; this
module focuses exclusively on inter-document relationships.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, cast

from cataforge.core.paths import project_root_from_docs_dir
from cataforge.core.types import Severity
from cataforge.runtime.skill.builtins._shared import CheckReport, Issue, IssueCollector
from cataforge.runtime.skill.builtins.doc_consistency._checks import _CrossDocChecksMixin
from cataforge.runtime.skill.builtins.doc_consistency._parse import (
    _find_docs,
    _read_all_content,
)
from cataforge.runtime.skill.builtins.doc_consistency._render import render_text
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

    def _has_content(self, doc_type: str) -> bool:
        return bool(self._content.get(doc_type, "").strip())

    def _project_root(self) -> Path | None:
        """Resolve project root from ``docs_dir`` (None when not a project)."""
        return project_root_from_docs_dir(self.docs_dir)

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
            from cataforge.domain.kg._dispatch import active_doc_types  # noqa: PLC0415

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
            from cataforge.domain.kg import KnowledgeGraph  # noqa: PLC0415
            from cataforge.domain.kg._dispatch import kg_config_for  # noqa: PLC0415
        except ImportError:
            return None

        cfg = kg_config_for(project_root)
        try:
            from cataforge.domain.kg._sparql_utils import cf_namespace  # noqa: PLC0415

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
                    str(row["eid"].value)
                    for row in cast("Any", kg.store.query(prd_q))
                    if row["eid"] is not None
                }
                referenced = {
                    str(row["ac_id"].value)
                    for row in cast("Any", kg.store.query(downstream_q))
                    if row["ac_id"] is not None
                }
        except Exception:
            return None
        if not prd_acs:
            return None  # no ACs ingested; let regex handle
        return prd_acs - referenced

    def collect(self) -> CheckReport:
        """Run all cross-document checks and return a structured report.

        Pure of console I/O: findings accumulate in ``self._issues`` and the
        traceability matrix lands in ``summary``. Rendering (text or JSON)
        is the caller's job via :mod:`._render` / :meth:`CheckReport.to_dict`.
        """
        available = [dt for dt in ("prd", "arch", "ui-spec", "dev-plan") if self._has_content(dt)]
        if len(available) < 2:
            return CheckReport(
                self._issues,
                summary={"available": available, "skipped": True},
                headline=(f"跳过: 仅发现 {len(available)} 个文档类型，跨文档校验需要至少 2 个"),
            )

        self.check_prd_arch_ac_coverage()
        self.check_prd_arch_nfr_mapping()
        self.check_prd_arch_priority_alignment()
        self.check_arch_devplan_api_contract()
        self.check_arch_devplan_entity_propagation()
        self.check_prd_devplan_ac_traceability()
        self.check_prd_devplan_ac_granularity()
        self.check_prd_uispec_user_facing_coverage()
        self.check_orphaned_components()

        return CheckReport(
            self._issues,
            summary={"available": available, "matrix": self.build_traceability_matrix()},
            headline=f"跨文档一致性校验: 发现 {', '.join(available)}",
        )

    def run(self) -> int:
        """Run checks, print the text report (unless quiet), return 0/1/2."""
        report = self.collect()
        if not self._quiet:
            print(render_text(report))
        return report.exit_code


def main() -> None:
    ensure_utf8()
    docs_dir = "docs/"
    fmt = "text"
    args = sys.argv[1:]
    if "--format" in args:
        idx = args.index("--format")
        fmt = args[idx + 1] if idx + 1 < len(args) else "text"
        args = args[:idx] + args[idx + 2 :]
    if args:
        docs_dir = args[0]

    checker = CrossDocChecker(docs_dir)
    report = checker.collect()
    if fmt == "json":
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(render_text(report))
    sys.exit(report.exit_code)


if __name__ == "__main__":
    main()
