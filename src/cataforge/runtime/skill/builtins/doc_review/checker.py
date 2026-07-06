"""Document structure validation — ``DocChecker`` and CLI ``main``."""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cataforge.core.paths import project_root_from_docs_dir
from cataforge.core.types import Severity
from cataforge.runtime.skill.builtins._shared import CheckReport, IssueCollector
from cataforge.utils.common import ensure_utf8
from cataforge.utils.frontmatter import split_yaml_frontmatter
from cataforge.utils.md_parse import strip_code_blocks
from cataforge.utils.placeholders import count_unresolved_placeholders

from ._render import render_text
from .constants import (
    DOC_SPLIT_THRESHOLD_LINES,
    KNOWN_DOC_PREFIXES,
)
from .template_registry import (
    load_template_required_sections,
    parse_required_sections_from_list,
)
from .typed_checks import TypedDocChecksMixin


@dataclass(frozen=True)
class _CoverageRule:
    """One upstream→downstream coverage relation for ``check_bidirectional_coverage``.

    ``require_test`` gates whether a verifying TestCase is demanded in addition
    to an implementing artifact. Authoring-phase gates (arch / ui-spec / dev-plan)
    leave it False — TestCases are a later-phase artifact, so demanding one here
    is structurally unsatisfiable. A future testing-phase gate can set it True.
    """

    upstream_type: str
    upstream_prefix: str
    require_test: bool = False


def _coverage_row_uncovered(*, has_impl: bool, has_test: bool, require_test: bool) -> bool:
    """A Feature row is uncovered when it lacks an implementing artifact, or
    (only when the gate demands it) lacks a verifying TestCase."""
    return not (has_impl and (has_test or not require_test))


def _fm(content: str) -> dict[str, Any]:
    """Extract frontmatter dict; empty dict when absent or malformed."""
    meta, _ = split_yaml_frontmatter(content)
    return meta if meta is not None else {}


_BARE_SECTION_RE = re.compile(r"§(\d+(?:\.\d+)*)")
_MD_HEADING_RE = re.compile(r"^#{1,6}\s+(.+)$", re.MULTILINE)


def _bare_section_number(section: str) -> str | None:
    """``§3`` / ``§3.2`` → the bare number; ``None`` for anything else.

    Entity xrefs (``§2.F-003``), placeholders (``§N``) and free-form fragments
    are not bare section refs and keep their existing handling.
    """
    m = _BARE_SECTION_RE.fullmatch(section)
    return m.group(1) if m else None


def _heading_matches_section(title: str, number: str) -> bool:
    """True when heading ``title`` is section ``number``.

    Accepts both numbering styles: ``2. 功能需求`` / ``2 概览`` and the
    §-prefixed ``§2 Modules``. The number must end at a boundary so ``§3``
    never matches ``30. …``.
    """
    esc = re.escape(number)
    return re.match(rf"(?:§\s*)?{esc}(?:[.\s):、）]|$)", title.strip()) is not None


def _md_file_has_section(path: Path, number: str) -> bool:
    """True when the markdown file carries a heading for section ``number``."""
    try:
        text = path.read_text()
    except OSError:
        return True  # unreadable target is a filesystem problem, not a broken ref
    return any(_heading_matches_section(m.group(1), number) for m in _MD_HEADING_RE.finditer(text))


@dataclass(frozen=True)
class _KgXrefResolvers:
    """KG-backed xref existence checks: entity by id, section by bare §-number."""

    entity: Callable[[str], bool]
    section: Callable[[str, str], bool]


def read_file(path: str) -> str:
    return Path(path).read_text(errors="replace")


class DocChecker(TypedDocChecksMixin):
    def __init__(
        self,
        doc_type: str,
        doc_file: str,
        docs_dir: str = "docs/",
        quiet: bool = False,
    ) -> None:
        self.doc_type = doc_type
        self.doc_file = doc_file
        self.docs_dir = docs_dir
        self.content = read_file(doc_file)
        self.lines = self.content.splitlines()
        self._issues = IssueCollector()
        self._quiet = quiet

    @property
    def errors(self) -> list[str]:
        return [i.message for i in self._issues.blocking]

    @property
    def warnings(self) -> list[str]:
        return [i.message for i in self._issues.advisory]

    def fail(self, msg: str, category: str = "doc-structure") -> None:
        self._issues.add(Severity.HIGH, category, msg)

    def warn(self, msg: str, category: str = "doc-structure") -> None:
        self._issues.add(Severity.LOW, category, msg)

    # ---- Generic checks ----

    def check_meta(self) -> None:
        fm = _fm(self.content)
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
        if "consumers" not in fm and self.doc_type not in ("research", "changelog"):
            self.fail("缺少consumers字段")

    def check_nav_block(self) -> None:
        if self.doc_type in ("changelog", "research"):
            return
        nav_match = re.search(r"\[NAV\](.*?)\[/NAV\]", self.content, re.DOTALL)
        if not nav_match:
            self.fail("缺少[NAV]...[/NAV]块")
            return
        nav_text = nav_match.group(1)
        nav_sections = re.findall(r"§(\d+)", nav_text)
        nav_top_sections = sorted(set(nav_sections))
        actual_sections = re.findall(r"^## (\d+)\.", self.content, re.MULTILINE)
        actual_top_sections = sorted(set(actual_sections))
        if nav_top_sections and actual_top_sections and nav_top_sections != actual_top_sections:
            self.warn(
                f"[NAV]块章节({','.join('§' + s for s in nav_top_sections)}) "
                f"与实际章节({','.join('§' + s for s in actual_top_sections)})不一致"
            )

    def check_no_todo(self) -> None:
        unannotated = count_unresolved_placeholders(self.content)
        if unannotated > 0:
            self.fail(f"{unannotated}个未处理TODO/TBD/FIXME")

    def _split_threshold(self) -> int:
        """Resolve ``DOC_SPLIT_THRESHOLD_LINES`` from framework.json.

        Falls back to the module default when no project root is resolvable
        or the constant is absent/invalid — so the check still runs against
        an arbitrary docs directory.
        """
        root = self._project_root()
        if root is None:
            return DOC_SPLIT_THRESHOLD_LINES
        try:
            from cataforge.core.config import ConfigManager

            val = ConfigManager(root).get_constant("DOC_SPLIT_THRESHOLD_LINES")
        except Exception:
            return DOC_SPLIT_THRESHOLD_LINES
        if isinstance(val, int) and not isinstance(val, bool) and val > 0:
            return val
        return DOC_SPLIT_THRESHOLD_LINES

    def check_line_count(self) -> None:
        line_count = len(self.lines)
        threshold = self._split_threshold()
        if line_count > threshold:
            self.warn(f"文档行数({line_count})超过{threshold}行阈值，建议拆分为多个逻辑文档或精简")

    def check_xref(self) -> None:
        content_no_code = strip_code_blocks(self.content)
        refs = re.findall(r"([\w-]+)#([\w§.\-]+)", content_no_code)
        docs_path = self._docs_root()
        if not docs_path.exists():
            return

        # When the project has KG active for this doc_type, use the
        # graph to verify referent existence — strict URI resolution
        # eliminates the false positives the file-glob path produces
        # against URL fragments.
        resolvers = self._maybe_kg_xref_resolvers()

        for doc_id, _section in refs:
            if "{" in doc_id or "}" in doc_id:
                continue
            prefix = doc_id.split("-")[0] if "-" in doc_id else doc_id
            if prefix not in KNOWN_DOC_PREFIXES and doc_id not in KNOWN_DOC_PREFIXES:
                continue

            section_num = _bare_section_number(_section)

            if resolvers is not None:
                entity_match = re.search(r"\b([A-Z]+-\d{3,})\b", _section)
                if entity_match:
                    if not resolvers.entity(entity_match.group(1)):
                        self.fail(f"交叉引用目标 {doc_id}#{_section} 在 KG 中未解析")
                elif section_num is not None and not resolvers.section(doc_id, section_num):
                    self.fail(f"交叉引用目标 {doc_id}#{_section} 在 KG 中无对应章节")
                continue

            matches = list(docs_path.glob(f"{doc_id}*"))
            if not matches:
                matches = list(docs_path.glob(f"**/{doc_id}*"))
            if not matches:
                self.fail(f"交叉引用目标 {doc_id} 未找到对应文件")
                continue
            if section_num is not None and not any(
                _md_file_has_section(p, section_num) for p in matches if p.is_file()
            ):
                self.fail(f"交叉引用目标 {doc_id}#{_section} 未找到对应章节")

    def check_required_sections(self) -> None:
        fm = _fm(self.content)
        mode = fm.get("mode", "standard") if fm else "standard"
        sections = load_template_required_sections(self.doc_type, mode)
        if sections is None:
            self_declared = (fm or {}).get("required_sections")
            if isinstance(self_declared, list) and self_declared:
                sections = parse_required_sections_from_list([str(h) for h in self_declared if h])
                self.warn(
                    f"模板未注册 (doc_type={self.doc_type})，回退使用文档自声明的 "
                    f"required_sections ({len(sections)} 项)"
                )
            else:
                if self.doc_type not in ("changelog",):
                    self.warn(f"无法从模板加载 required_sections (doc_type={self.doc_type})")
                return
        _, body = split_yaml_frontmatter(self.content)
        body = body if body is not None else self.content
        for heading, name in sections:
            pattern = re.escape(heading)
            match = re.search(pattern + r"(.*?)(?=^## |\Z)", body, re.DOTALL | re.MULTILINE)
            if not match:
                self.fail(f"缺少必填章节: {name}")
            elif len(match.group(1).strip()) == 0:
                self.fail(f"必填章节为空: {name}")

    def check_id_continuity(self) -> None:
        id_patterns: dict[str, list[tuple[str, str]]] = {
            "prd": [("F", r"F-(\d+)"), ("AC", r"AC-(\d+)")],
            "arch": [("M", r"M-(\d+)"), ("API", r"API-(\d+)"), ("E", r"E-(\d+)")],
            "dev-plan": [("T", r"T-(\d+)")],
            "ui-spec": [("UC", r"UC-(\d+)"), ("P", r"P-(\d+)")],
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
                missing_str = ", ".join(f"{prefix}-{str(m).zfill(3)}" for m in sorted(missing))
                self.warn(f"ID编号不连续, 缺少: {missing_str}")

    # Doc types that are themselves review artifacts (or never enter the
    # doc-review verdict flow) — their status is not gated on a REVIEW report.
    _STATUS_PROVENANCE_EXEMPT = frozenset(
        {
            "review",
            "code-review",
            "sprint-review",
            "framework-review",
            "design-review",
            "correction-log",
            "skill-improve",
            "changelog",
            "research",
        }
    )

    def check_status_provenance(self) -> None:
        """``status: approved`` requires a review-report trail.

        A freshly created document cannot be born approved — that bypasses
        the doc-review gate.
        """
        fm = _fm(self.content)
        if fm.get("status") != "approved":
            return
        if self.doc_type in self._STATUS_PROVENANCE_EXEMPT:
            return
        doc_id = str(fm.get("id") or "")
        if not doc_id:
            return  # missing id is already a check_meta failure
        reviews_dir = self._docs_root() / "reviews" / "doc"
        if not list(reviews_dir.glob(f"REVIEW-{doc_id}-r*.md")):
            self.fail(
                f"status=approved 但缺少审查报告 docs/reviews/doc/REVIEW-{doc_id}-r*.md "
                f"— 新建文档必须以 status: draft 起始，经 doc-review 通过后才置 approved"
            )

    def check_bidirectional_coverage(self) -> None:
        """Verify downstream doc covers all items from its upstream doc.

        When the project has KG active for the upstream + downstream
        doc_types, replaces the file-scan + string-match check with a
        SPARQL ``cf:implements`` / ``cf:verifies+`` query (Task 6 §6.4
        A13). The graph-based check eliminates the false-positive class
        from Task 1 §1.4 case A — a mention in a comment block no
        longer counts as coverage.
        """
        coverage_rules: dict[str, _CoverageRule] = {
            "arch": _CoverageRule("prd", "F"),
            "dev-plan": _CoverageRule("arch", "M"),
            "ui-spec": _CoverageRule("prd", "F"),
        }
        rule = coverage_rules.get(self.doc_type)
        if not rule:
            return

        upstream_prefix = rule.upstream_prefix
        upstream_type = rule.upstream_type

        if self._kg_bidirectional_coverage(upstream_prefix, rule.require_test):
            return  # KG-based check ran and reported its own failures

        docs_path = self._docs_root()
        if not docs_path.exists():
            return

        upstream_items: set[str] = set()
        for up_file in docs_path.glob(f"**/{upstream_type}*.md"):
            try:
                up_content = up_file.read_text(errors="replace")
            except OSError:
                continue
            for m in re.finditer(rf"^### ({upstream_prefix}-\d+)", up_content, re.MULTILINE):
                upstream_items.add(m.group(1))

        if not upstream_items:
            return

        content_no_code = strip_code_blocks(self.content)
        covered = {item for item in upstream_items if re.search(re.escape(item), content_no_code)}
        uncovered = upstream_items - covered

        if uncovered:
            sorted_uncovered = sorted(uncovered)
            display = ", ".join(sorted_uncovered[:5])
            suffix = f" (共 {len(sorted_uncovered)} 项)" if len(sorted_uncovered) > 5 else ""
            self.fail(f"上游 {upstream_type} 中 {len(uncovered)} 项未被覆盖: {display}{suffix}")

    # ------------------------------------------------------------------
    # KG dispatch helpers (Task 6 §6.4 A12 / A13)
    # ------------------------------------------------------------------

    def _project_root(self) -> Path | None:
        """Resolve the project root from ``docs_dir`` (None when not a project)."""
        return project_root_from_docs_dir(self.docs_dir)

    def _docs_root(self) -> Path:
        """The project-global docs tree root — holds ``reviews/`` and the docs.

        Project-global lookups (review reports, upstream-doc scans, xref target
        resolution) must resolve here, never against the ``docs_dir`` subdir a
        caller may pass (e.g. ``docs/arch/``). Falls back to ``docs_dir`` when
        the path is not inside a CataForge project (bare-file checks, tests).
        """
        root = self._project_root()
        return root / "docs" if root is not None else Path(self.docs_dir)

    def _maybe_kg_xref_resolvers(self) -> _KgXrefResolvers | None:
        """Return KG-backed xref resolvers if KG is active.

        They short-circuit the file-glob xref check when the graph carries
        authoritative knowledge of the project's entities and sections
        (Task 6 §6.4 A12).
        """
        project_root = self._project_root()
        if project_root is None:
            return None
        try:
            from cataforge.domain.kg import KnowledgeGraph
            from cataforge.domain.kg._dispatch import is_active_for, kg_config_for
        except ImportError:
            return None
        if not is_active_for(self.doc_type, project_root):
            return None
        try:
            cfg = kg_config_for(project_root)
            kg = KnowledgeGraph.connect(cfg, read_only=True).__enter__()
        except Exception:
            return None

        def _entity_exists(entity_id: str) -> bool:
            try:
                return kg.query.exists(entity_id)
            except Exception:
                return True  # don't false-fail on transient KG errors

        def _section_exists(doc_id: str, number: str) -> bool:
            try:
                anchors = kg.query.section_anchors(doc_id)
            except Exception:
                return True  # don't false-fail on transient KG errors
            if not anchors:
                # The graph models no sections for this doc (not ingested /
                # not Document-backed) — outside this check's jurisdiction.
                return True
            return any(_heading_matches_section(a, number) for a in anchors)

        return _KgXrefResolvers(entity=_entity_exists, section=_section_exists)

    def _kg_bidirectional_coverage(self, upstream_prefix: str, require_test: bool = False) -> bool:
        """Run the SPARQL coverage check when KG is active.

        Returns True iff the KG path ran (callers should skip the
        legacy file-scan). Failures discovered by the graph are
        recorded via `self.fail()`; a green result returns True with
        no `fail()` calls.
        """
        project_root = self._project_root()
        if project_root is None:
            return False
        try:
            from cataforge.domain.kg import KnowledgeGraph
            from cataforge.domain.kg._dispatch import is_active_for, kg_config_for
        except ImportError:
            return False
        if not is_active_for(self.doc_type, project_root):
            return False
        try:
            cfg = kg_config_for(project_root)
            with KnowledgeGraph.connect(cfg, read_only=True) as kg:
                # Module coverage (dev-plan→arch) gates on `cf:realizes`; every
                # other upstream prefix is Feature impl/test coverage.
                if upstream_prefix == "M":
                    rows = kg.trace.module_coverage()
                else:
                    rows = kg.trace.bidirectional_coverage()
        except Exception:
            return False

        uncovered = [
            r.entity_id
            for r in rows
            if r.entity_id.startswith(upstream_prefix + "-")
            and _coverage_row_uncovered(
                has_impl=r.has_impl, has_test=r.has_test, require_test=require_test
            )
        ]
        if uncovered:
            display = ", ".join(sorted(uncovered)[:5])
            suffix = f" (共 {len(uncovered)} 项)" if len(uncovered) > 5 else ""
            self.fail(
                f"KG 覆盖检查: {upstream_prefix} 中 {len(uncovered)} 项缺少"
                f"实现或验证: {display}{suffix}"
            )
        return True

    def check_export_freshness(self) -> None:
        """Graph mode: the file under review must be a fresh, consistent export.

        A ``graph_ahead`` / ``conflict`` document means the graph holds content
        the exported view lacks — reviewing the stale file burns a full review
        cycle on superseded text. Desynced tile sections likewise mean
        revisions that never reached the export. Markdown mode, an unreachable
        graph, or a file with no Document node all skip silently.
        """
        project_root = self._project_root()
        if project_root is None:
            return
        try:
            from cataforge.domain.kg import KnowledgeGraph
            from cataforge.domain.kg._dispatch import (
                context_mode,
                is_active_for,
                kg_config_for,
            )
        except ImportError:
            return
        try:
            if context_mode(project_root) != "graph" or not is_active_for(
                self.doc_type, project_root
            ):
                return
        except Exception:
            return
        try:
            import hashlib

            from cataforge.domain.kg._sparql_utils import cf_namespace
            from cataforge.domain.kg.authority import DRIFT_CONFLICT, DRIFT_GRAPH_AHEAD
            from cataforge.domain.kg.export.document_pipeline import (
                _list_documents,
                render_document,
            )
            from cataforge.domain.kg.reconcile import (
                _classify_document_drift,
                _document_baseline,
            )
            from cataforge.domain.kg.section_sync import desynced_tile_sections

            cfg = kg_config_for(project_root)
            target = Path(self.doc_file).resolve()
            with KnowledgeGraph.connect(cfg, read_only=True) as kg:
                ns = cf_namespace(cfg)
                doc = next(
                    (
                        d
                        for d in _list_documents(kg.store, ns)
                        if (project_root / d["source_path"]).resolve() == target
                    ),
                    None,
                )
                if doc is None:
                    return
                baseline = _document_baseline(kg.store, cfg, doc["doc_iri"])
                render_hash = hashlib.sha256(
                    render_document(kg.store, ns, doc).encode("utf-8")
                ).hexdigest()
                file_hash = hashlib.sha256(target.read_bytes()).hexdigest()
                state = _classify_document_drift(file_hash, baseline, render_hash)
                desynced = desynced_tile_sections(kg.store, cfg, doc["doc_iri"])
        except Exception:
            return  # transient KG errors must not block a text review
        if state in (DRIFT_GRAPH_AHEAD, DRIFT_CONFLICT):
            self.fail(
                f"导出视图陈旧 (drift={state}): 图侧内容尚未导出，"
                "先运行 `cataforge context finalize` 重导出后再审查",
                category="consistency",
            )
        if desynced:
            display = ", ".join(desynced[:3])
            self.fail(
                f"图内 {len(desynced)} 个章节与其 level-2 tile 不一致 ({display}): "
                "修订未到达导出视图，经 `context write-narrative` 重写该节"
                "或 `cataforge context ingest` 重建一致性",
                category="consistency",
            )

    def collect(self) -> CheckReport:
        """Run all checks and return a structured report (no console I/O).

        Findings accumulate in ``self._issues``; an unrecognized doc_type is
        flagged in ``summary`` so the renderer can note that only the generic
        checks ran.
        """
        self.check_export_freshness()
        self.check_meta()
        self.check_status_provenance()
        self.check_nav_block()
        self.check_no_todo()
        self.check_xref()
        self.check_line_count()
        self.check_required_sections()
        self.check_id_continuity()
        self.check_bidirectional_coverage()

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
        unknown = self.doc_type not in checks
        if not unknown:
            checks[self.doc_type]()

        return CheckReport(
            self._issues,
            summary={"unknown_doc_type": self.doc_type if unknown else None},
            headline=(f"检查: {self.doc_file} (type={self.doc_type})"),
        )

    def run(self) -> int:
        """Run checks, print the text report (unless quiet), return 0/1.

        Advisory findings do not gate, so the exit code is 1 only when
        blocking findings exist.
        """
        report = self.collect()
        if not self._quiet:
            print(render_text(report))
        return 1 if report.issues.blocking else 0


VALID_DOC_TYPES = (
    "prd",
    "arch",
    "dev-plan",
    "ui-spec",
    "test-report",
    "deploy-spec",
    "research",
    "changelog",
)


def _usage() -> str:
    return (
        "用法: cataforge skill run doc-review -- <doc-type> <doc-file> "
        "[--docs-dir docs/]\n"
        f"  doc-type ∈ {{{', '.join(VALID_DOC_TYPES)}}}"
    )


def _looks_like_path(value: str) -> bool:
    return value.endswith(".md") or "/" in value or "\\" in value


def main() -> None:
    ensure_utf8()
    if len(sys.argv) < 3 or sys.argv[1].startswith("--"):
        print(f"错误: 缺少 doc-type / doc-file 参数。\n{_usage()}")
        sys.exit(2)

    doc_type = sys.argv[1]
    doc_file = sys.argv[2]
    if _looks_like_path(doc_type):
        print(f"错误: 第一个参数 {doc_type!r} 像文件路径，doc-type 缺失或顺序颠倒。\n{_usage()}")
        sys.exit(2)
    if not Path(doc_file).is_file():
        print(f"错误: 找不到文档文件 {doc_file!r} (cwd={Path.cwd()})。\n{_usage()}")
        sys.exit(2)
    docs_dir = "docs/"
    fmt = "text"

    if "--docs-dir" in sys.argv:
        idx = sys.argv.index("--docs-dir")
        docs_dir = sys.argv[idx + 1]
    if "--format" in sys.argv:
        idx = sys.argv.index("--format")
        fmt = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else "text"

    checker = DocChecker(doc_type, doc_file, docs_dir)
    report = checker.collect()
    if fmt == "json":
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(render_text(report))
    sys.exit(1 if report.issues.blocking else 0)
