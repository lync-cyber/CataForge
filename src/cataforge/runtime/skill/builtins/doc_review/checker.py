"""Document structure validation — ``DocChecker`` and CLI ``main``."""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from cataforge.core.paths import project_root_from_docs_dir
from cataforge.core.types import Severity
from cataforge.runtime.skill.builtins._shared import CheckReport, IssueCollector
from cataforge.utils.common import ensure_utf8
from cataforge.utils.frontmatter import split_yaml_frontmatter
from cataforge.utils.md_parse import strip_code_blocks

from ._render import render_text
from .constants import DOC_SPLIT_THRESHOLD_LINES, KNOWN_DOC_PREFIXES, VOLUME_TYPES
from .template_registry import (
    load_template_required_sections,
    parse_required_sections_from_list,
)
from .typed_checks import TypedDocChecksMixin


def _fm(content: str) -> dict[str, Any]:
    """Extract frontmatter dict; empty dict when absent or malformed."""
    meta, _ = split_yaml_frontmatter(content)
    return meta if meta is not None else {}


def read_file(path: str) -> str:
    return Path(path).read_text()


class DocChecker(TypedDocChecksMixin):
    def __init__(
        self,
        doc_type: str,
        doc_file: str,
        docs_dir: str = "docs/",
        volume_type: str | None = None,
        quiet: bool = False,
    ) -> None:
        self.doc_type = doc_type
        self.doc_file = doc_file
        self.docs_dir = docs_dir
        self.content = read_file(doc_file)
        self.lines = self.content.splitlines()
        self._issues = IssueCollector()
        self._quiet = quiet
        self.volume_type = volume_type or self._detect_volume_type()

    @property
    def errors(self) -> list[str]:
        return [i.message for i in self._issues.blocking]

    @property
    def warnings(self) -> list[str]:
        return [i.message for i in self._issues.advisory]

    def _detect_volume_type(self) -> str:
        fm = _fm(self.content)
        vt = fm.get("volume_type", "")
        if vt and vt in VOLUME_TYPES:
            return str(vt)
        vol = fm.get("volume", "")
        if vol and vol in VOLUME_TYPES:
            return str(vol)
        stem = Path(self.doc_file).stem
        filename_patterns = [
            (r"-api$", "api"),
            (r"-data$", "data"),
            (r"-modules$", "modules"),
            (r"-s\d+$", "sprint"),
            (r"-f\d+-f\d+$", "features"),
            (r"-p\d+-p\d+$", "pages"),
            (r"-c\d+-c\d+$", "components"),
            (r"-theme-\d+(?:-[\w-]+)?$", "theme"),
        ]
        for pattern, vol_type in filename_patterns:
            if re.search(pattern, stem):
                return vol_type
        return "main"

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
        todo_count = len(re.findall(r"TODO|TBD|FIXME", self.content))
        assumption_count = len(re.findall(r"\[ASSUMPTION\]", self.content))
        remaining = todo_count - assumption_count
        if remaining > 0:
            self.fail(f"{remaining}个未处理TODO/TBD/FIXME")

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
            self.warn(f"文档行数({line_count})超过{threshold}行阈值，建议通过doc-gen拆分为分卷")

    def check_xref(self) -> None:
        content_no_code = strip_code_blocks(self.content)
        refs = re.findall(r"([\w-]+)#([\w§.\-]+)", content_no_code)
        docs_path = Path(self.docs_dir)
        if not docs_path.exists():
            return

        # When the project has KG active for this doc_type, use the
        # graph to verify referent existence — strict URI resolution
        # eliminates the false positives the file-glob path produces
        # against URL fragments and across-volume references
        # (Task 6 §6.4 A12).
        kg_resolver = self._maybe_kg_xref_resolver()

        for doc_id, _section in refs:
            if "{" in doc_id or "}" in doc_id:
                continue
            prefix = doc_id.split("-")[0] if "-" in doc_id else doc_id
            if prefix not in KNOWN_DOC_PREFIXES and doc_id not in KNOWN_DOC_PREFIXES:
                continue

            if kg_resolver is not None:
                entity_match = re.search(r"\b([A-Z]+-\d{3,})\b", _section)
                if entity_match and not kg_resolver(entity_match.group(1)):
                    self.fail(f"交叉引用目标 {doc_id}#{_section} 在 KG 中未解析")
                continue

            matches = list(docs_path.glob(f"{doc_id}*"))
            if not matches:
                matches = list(docs_path.glob(f"**/{doc_id}*"))
            if not matches:
                parent = docs_path.parent
                if parent != docs_path:
                    matches = list(parent.glob(f"**/{doc_id}*"))
            if not matches:
                self.fail(f"交叉引用目标 {doc_id} 未找到对应文件")

    def check_required_sections(self) -> None:
        fm = _fm(self.content)
        mode = fm.get("mode", "standard") if fm else "standard"
        sections = load_template_required_sections(self.doc_type, self.volume_type, mode)
        if sections is None:
            self_declared = (fm or {}).get("required_sections")
            if isinstance(self_declared, list) and self_declared:
                sections = parse_required_sections_from_list([str(h) for h in self_declared if h])
                self.warn(
                    f"模板未注册 (doc_type={self.doc_type}, "
                    f"volume_type={self.volume_type})，回退使用文档自声明的 "
                    f"required_sections ({len(sections)} 项)"
                )
            else:
                if self.doc_type not in ("changelog",):
                    self.warn(
                        f"无法从模板加载 required_sections "
                        f"(doc_type={self.doc_type}, volume_type={self.volume_type})"
                    )
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
                missing_str = ", ".join(f"{prefix}-{str(m).zfill(3)}" for m in sorted(missing))
                self.warn(f"ID编号不连续, 缺少: {missing_str}")

    def check_split_header(self) -> None:
        if self.volume_type != "main":
            fm = _fm(self.content)
            if not fm.get("split_from"):
                self.fail(f"分卷文档 (volume={self.volume_type}) 缺少 split_from 字段")

    def check_bidirectional_coverage(self) -> None:
        """Verify downstream doc covers all items from its upstream doc.

        When the project has KG active for the upstream + downstream
        doc_types, replaces the file-scan + string-match check with a
        SPARQL ``cf:implements`` / ``cf:verifies+`` query (Task 6 §6.4
        A13). The graph-based check eliminates the false-positive class
        from Task 1 §1.4 case A — a mention in a comment block no
        longer counts as coverage.
        """
        coverage_rules: dict[str, dict[str, str]] = {
            "arch": {"upstream_type": "prd", "upstream_prefix": "F"},
            "dev-plan": {"upstream_type": "arch", "upstream_prefix": "M"},
            "ui-spec": {"upstream_type": "prd", "upstream_prefix": "F"},
        }
        rule = coverage_rules.get(self.doc_type)
        if not rule or self.volume_type != "main":
            return

        upstream_prefix = rule["upstream_prefix"]
        upstream_type = rule["upstream_type"]

        if self._kg_bidirectional_coverage(upstream_prefix):
            return  # KG-based check ran and reported its own failures

        docs_path = Path(self.docs_dir)
        if not docs_path.exists():
            docs_path = docs_path.parent
            if not docs_path.exists():
                return

        upstream_items: set[str] = set()
        for up_file in docs_path.glob(f"**/{upstream_type}*.md"):
            try:
                up_content = up_file.read_text()
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

    def _maybe_kg_xref_resolver(self) -> Callable[[str], bool] | None:
        """Return a ``callable(entity_id) -> bool`` if KG is active.

        The resolver short-circuits the file-glob xref check when the
        graph carries authoritative knowledge of the project's
        entities (Task 6 §6.4 A12).
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
            kg = KnowledgeGraph.connect(cfg).__enter__()
        except Exception:
            return None

        def _exists(entity_id: str) -> bool:
            try:
                return kg.query.exists(entity_id)
            except Exception:
                return True  # don't false-fail on transient KG errors

        return _exists

    def _kg_bidirectional_coverage(self, upstream_prefix: str) -> bool:
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
            with KnowledgeGraph.connect(cfg) as kg:
                rows = kg.trace.bidirectional_coverage()
        except Exception:
            return False

        uncovered = [
            r.feature_id
            for r in rows
            if r.feature_id.startswith(upstream_prefix + "-") and not (r.has_impl and r.has_test)
        ]
        if uncovered:
            display = ", ".join(sorted(uncovered)[:5])
            suffix = f" (共 {len(uncovered)} 项)" if len(uncovered) > 5 else ""
            self.fail(
                f"KG 覆盖检查: {upstream_prefix} 中 {len(uncovered)} 项缺少"
                f"实现或验证: {display}{suffix}"
            )
        return True

    def check_split_consistency(self) -> None:
        if self.volume_type != "main":
            return
        doc_dir = Path(self.doc_file).parent
        doc_stem = Path(self.doc_file).stem
        volume_files = [
            f
            for f in doc_dir.glob(f"{doc_stem}-*")
            if f.name != Path(self.doc_file).name and f.suffix == ".md"
        ]
        for vf in volume_files:
            if vf.stem not in self.content and vf.name not in self.content:
                self.warn(f"主卷未引用分卷文件: {vf.name}")

    def collect(self) -> CheckReport:
        """Run all checks and return a structured report (no console I/O).

        Findings accumulate in ``self._issues``; an unrecognized doc_type is
        flagged in ``summary`` so the renderer can note that only the generic
        checks ran.
        """
        self.check_meta()
        self.check_nav_block()
        self.check_no_todo()
        self.check_xref()
        self.check_line_count()
        self.check_required_sections()
        self.check_id_continuity()
        self.check_split_header()
        self.check_split_consistency()
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
            headline=(f"检查: {self.doc_file} (type={self.doc_type}, volume={self.volume_type})"),
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


def main() -> None:
    ensure_utf8()
    if len(sys.argv) < 3:
        print(
            "用法: python -m cataforge.runtime.skill.builtins.doc_review.doc_check "
            "<doc-type> <doc-file> [--docs-dir docs/] [--volume-type <type>]"
        )
        sys.exit(2)

    doc_type = sys.argv[1]
    doc_file = sys.argv[2]
    docs_dir = "docs/"
    volume_type = None
    fmt = "text"

    if "--docs-dir" in sys.argv:
        idx = sys.argv.index("--docs-dir")
        docs_dir = sys.argv[idx + 1]
    if "--volume-type" in sys.argv:
        idx = sys.argv.index("--volume-type")
        volume_type = sys.argv[idx + 1]
    if "--format" in sys.argv:
        idx = sys.argv.index("--format")
        fmt = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else "text"

    checker = DocChecker(doc_type, doc_file, docs_dir, volume_type)
    report = checker.collect()
    if fmt == "json":
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(render_text(report))
    sys.exit(1 if report.issues.blocking else 0)
