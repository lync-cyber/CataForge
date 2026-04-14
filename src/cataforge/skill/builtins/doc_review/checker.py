"""Document structure validation — ``DocChecker`` and CLI ``main``."""

from __future__ import annotations

import re
import sys
from pathlib import Path

from cataforge.utils.common import ensure_utf8_stdio
from cataforge.utils.yaml_parser import parse_yaml_frontmatter

from .constants import DOC_SPLIT_THRESHOLD_LINES, KNOWN_DOC_PREFIXES, VOLUME_TYPES
from .template_registry import load_template_required_sections
from .typed_checks import TypedDocChecksMixin


def read_file(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


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
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self._quiet = quiet
        self.volume_type = volume_type or self._detect_volume_type()

    def _detect_volume_type(self) -> str:
        fm = parse_yaml_frontmatter(self.content)
        vt = fm.get("volume_type", "")
        if vt and vt in VOLUME_TYPES:
            return vt
        vol = fm.get("volume", "")
        if vol and vol in VOLUME_TYPES:
            return vol
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

    def fail(self, msg: str) -> None:
        self.errors.append(msg)
        if not self._quiet:
            print(f"FAIL: {msg}")

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)
        if not self._quiet:
            print(f"WARN: {msg}")

    # ---- Generic checks ----

    def check_meta(self) -> None:
        fm = parse_yaml_frontmatter(self.content)
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
        if (
            nav_top_sections
            and actual_top_sections
            and nav_top_sections != actual_top_sections
        ):
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

    @staticmethod
    def _strip_code_blocks(text: str) -> str:
        return re.sub(r"```.*?```", "", text, flags=re.DOTALL)

    def check_line_count(self) -> None:
        line_count = len(self.lines)
        if line_count > DOC_SPLIT_THRESHOLD_LINES:
            self.warn(
                f"文档行数({line_count})超过{DOC_SPLIT_THRESHOLD_LINES}行阈值，建议通过doc-gen拆分为分卷"
            )

    def check_xref(self) -> None:
        content_no_code = self._strip_code_blocks(self.content)
        refs = re.findall(r"([\w-]+)#([\w§.\-]+)", content_no_code)
        docs_path = Path(self.docs_dir)
        if not docs_path.exists():
            return
        for doc_id, _section in refs:
            if "{" in doc_id or "}" in doc_id:
                continue
            prefix = doc_id.split("-")[0] if "-" in doc_id else doc_id
            if prefix not in KNOWN_DOC_PREFIXES and doc_id not in KNOWN_DOC_PREFIXES:
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
        sections = load_template_required_sections(self.doc_type, self.volume_type)
        if sections is None:
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
                missing_str = ", ".join(
                    f"{prefix}-{str(m).zfill(3)}" for m in sorted(missing)
                )
                self.warn(f"ID编号不连续, 缺少: {missing_str}")

    def check_nav_index_registered(self) -> None:
        docs_path = Path(self.docs_dir)
        nav_index_path = docs_path / "NAV-INDEX.md"
        if not nav_index_path.exists():
            parent = docs_path.parent
            nav_index_path = parent / "NAV-INDEX.md"
            if not nav_index_path.exists():
                grandparent = parent.parent
                nav_index_path = grandparent / "NAV-INDEX.md"
        if not nav_index_path.exists():
            self.warn("NAV-INDEX.md不存在，无法验证注册状态")
            return
        nav_content = nav_index_path.read_text(encoding="utf-8")
        doc_filename = Path(self.doc_file).name
        fm = parse_yaml_frontmatter(self.content)
        doc_id = fm.get("id", "")
        if doc_filename not in nav_content and doc_id not in nav_content:
            self.warn(f"文档未注册到NAV-INDEX (文件={doc_filename}, ID={doc_id})")

    def check_split_header(self) -> None:
        if self.volume_type != "main":
            fm = parse_yaml_frontmatter(self.content)
            if not fm.get("split_from"):
                self.fail(f"分卷文档 (volume={self.volume_type}) 缺少 split_from 字段")

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

    def run(self) -> int:
        print(f"检查: {self.doc_file} (type={self.doc_type}, volume={self.volume_type})")

        self.check_meta()
        self.check_nav_block()
        self.check_no_todo()
        self.check_xref()
        self.check_line_count()
        self.check_required_sections()
        self.check_id_continuity()
        self.check_nav_index_registered()
        self.check_split_header()
        self.check_split_consistency()

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

        if self.warnings:
            print(f"WARNINGS: {len(self.warnings)}")
        if not self.errors:
            print("PASS: 所有检查通过")
            return 0
        print(f"TOTAL FAILURES: {len(self.errors)}")
        return 1


def main() -> None:
    ensure_utf8_stdio()
    if len(sys.argv) < 3:
        print(
            "用法: python -m cataforge.skill.builtins.doc_review.doc_check "
            "<doc-type> <doc-file> [--docs-dir docs/] [--volume-type <type>]"
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
