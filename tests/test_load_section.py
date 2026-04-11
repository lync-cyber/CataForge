"""load_section.py 单元测试 — 覆盖 parse/resolve/extract/batch/CLI 及异常边界"""

import io
import os
import sys

import pytest

import load_section
from load_section import (
    DocResolveError,
    LoadSectionError,
    RefParseError,
    SectionNotFoundError,
    extract,
    extract_batch,
    main,
    parse_ref,
    resolve_file,
)


# ---------- 测试辅助 ----------

def _write(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _make_prd(tmp_path, content: str) -> str:
    """在 tmp_path/docs/prd/ 下写入 prd-demo-v1.md，返回项目根目录。"""
    root = str(tmp_path)
    path = os.path.join(root, "docs", "prd", "prd-demo-v1.md")
    _write(path, content)
    return root


PRD_SAMPLE = """# PRD: Demo

## 1. 背景

背景正文。

### 1.1 子背景

子背景正文。

### 1.2 另一子节

另一子节正文。

## 2. 功能需求

功能列表：

### F-001: 登录

登录需求正文。
多行内容。

### F-002: 注销

注销需求正文。

## 3. 非功能需求

非功能正文。
"""


# ---------- TestParseRef ----------

class TestParseRef:
    def test_top_level_section(self):
        assert parse_ref("prd#§2") == ("prd", "2", None)

    def test_sub_section(self):
        assert parse_ref("prd#§1.1") == ("prd", "1.1", None)

    def test_deep_section(self):
        assert parse_ref("arch#§1.4") == ("arch", "1.4", None)

    def test_item_f_short(self):
        assert parse_ref("prd#§2.F-003") == ("prd", "2", "F-003")

    def test_item_api(self):
        assert parse_ref("arch#§3.API-001") == ("arch", "3", "API-001")

    def test_item_multiletter_prefix(self):
        # AC-xxx、T-xxx 等多字母/单字母均可
        assert parse_ref("dev-plan#§1.T-042") == ("dev-plan", "1", "T-042")
        assert parse_ref("prd#§2.AC-015") == ("prd", "2", "AC-015")

    def test_doc_id_with_hyphen(self):
        assert parse_ref("arch-api#§3.API-001") == ("arch-api", "3", "API-001")

    def test_strip_whitespace(self):
        assert parse_ref("  prd#§2  ") == ("prd", "2", None)

    def test_empty_raises(self):
        with pytest.raises(RefParseError):
            parse_ref("")

    def test_whitespace_only_raises(self):
        with pytest.raises(RefParseError):
            parse_ref("   ")

    def test_none_raises(self):
        with pytest.raises(RefParseError):
            parse_ref(None)  # type: ignore[arg-type]

    def test_missing_hash_raises(self):
        with pytest.raises(RefParseError):
            parse_ref("prd§2")

    def test_missing_section_marker_raises(self):
        with pytest.raises(RefParseError):
            parse_ref("prd#2")

    def test_uppercase_doc_id_raises(self):
        with pytest.raises(RefParseError):
            parse_ref("PRD#§2")

    def test_bad_section_path_raises(self):
        with pytest.raises(RefParseError):
            parse_ref("prd#§abc")

    def test_lowercase_item_raises(self):
        # 小写 item 无法匹配 item 模式，且非纯数字节路径
        with pytest.raises(RefParseError):
            parse_ref("prd#§2.f-001")


# ---------- TestResolveFile ----------

class TestResolveFile:
    def test_unknown_doc_id_raises(self, tmp_path):
        with pytest.raises(DocResolveError):
            resolve_file("unknown", str(tmp_path), "1", None)

    def test_missing_doc_dir_raises(self, tmp_path):
        with pytest.raises(DocResolveError):
            resolve_file("prd", str(tmp_path), "1", None)

    def test_empty_doc_dir_raises(self, tmp_path):
        os.makedirs(os.path.join(tmp_path, "docs", "prd"))
        with pytest.raises(DocResolveError):
            resolve_file("prd", str(tmp_path), "1", None)

    def test_single_file_returned(self, tmp_path):
        root = _make_prd(tmp_path, PRD_SAMPLE)
        path = resolve_file("prd", root, "1", None)
        assert path.endswith("prd-demo-v1.md")
        assert os.path.isfile(path)

    def test_multi_volume_picks_matching(self, tmp_path):
        root = str(tmp_path)
        # 主卷仅有 §1，分卷 arch-demo-v1-api.md 含 API-001
        _write(
            os.path.join(root, "docs", "arch", "arch-demo-v1.md"),
            "# ARCH\n\n## 1. 概览\n\nXYZ\n",
        )
        _write(
            os.path.join(root, "docs", "arch", "arch-demo-v1-api.md"),
            "# ARCH API\n\n## 3. 接口契约\n\n### API-001: 登录接口\n\n内容\n",
        )
        path = resolve_file("arch", root, "3", "API-001")
        assert path.endswith("arch-demo-v1-api.md")

    def test_multi_volume_fallback_first(self, tmp_path):
        root = str(tmp_path)
        _write(
            os.path.join(root, "docs", "arch", "arch-demo-v1.md"),
            "# ARCH\n\n## 1. 概览\n",
        )
        _write(
            os.path.join(root, "docs", "arch", "arch-demo-v1-api.md"),
            "# ARCH API\n\n## 3. 接口契约\n",
        )
        # 目标不存在于任一卷 → 返回首个候选（稳定排序后）
        path = resolve_file("arch", root, "99", None)
        assert path.endswith(".md")


# ---------- TestExtract ----------

class TestExtract:
    def test_extract_top_level(self, tmp_path):
        root = _make_prd(tmp_path, PRD_SAMPLE)
        content = extract("prd#§2", root)
        assert content.startswith("## 2. 功能需求")
        assert "F-001" in content
        assert "F-002" in content
        # 终止于下一顶级
        assert "## 3. 非功能需求" not in content
        # 包含子节
        assert "### F-001: 登录" in content

    def test_extract_sub_section(self, tmp_path):
        root = _make_prd(tmp_path, PRD_SAMPLE)
        content = extract("prd#§1.1", root)
        assert content.startswith("### 1.1 子背景")
        assert "子背景正文" in content
        # 终止于同级 1.2
        assert "### 1.2" not in content
        # 不应含其他顶级
        assert "## 2. 功能需求" not in content

    def test_extract_item(self, tmp_path):
        root = _make_prd(tmp_path, PRD_SAMPLE)
        content = extract("prd#§2.F-001", root)
        assert content.startswith("### F-001: 登录")
        assert "登录需求正文" in content
        assert "多行内容" in content
        # 终止于 F-002
        assert "F-002" not in content

    def test_extract_item_no_colon(self, tmp_path):
        content = "# Doc\n\n## 3. 接口\n\n### API-001\n\n接口正文。\n\n### API-002\n\n另一接口。\n"
        _write(
            os.path.join(tmp_path, "docs", "arch", "arch-x-v1.md"),
            content,
        )
        result = extract("arch#§3.API-001", str(tmp_path))
        assert result.startswith("### API-001")
        assert "接口正文" in result
        assert "API-002" not in result

    def test_extract_section_stops_at_higher_level(self, tmp_path):
        content = (
            "# Doc\n\n## 1. 一\n\n### 1.1 子\n\n子正文。\n\n## 2. 二\n\n二正文。\n"
        )
        _write(os.path.join(tmp_path, "docs", "prd", "prd-x-v1.md"), content)
        result = extract("prd#§1.1", str(tmp_path))
        assert "子正文" in result
        assert "## 2. 二" not in result

    def test_extract_missing_section_raises(self, tmp_path):
        root = _make_prd(tmp_path, PRD_SAMPLE)
        with pytest.raises(SectionNotFoundError) as exc:
            extract("prd#§99", root)
        assert "prd#§99" in str(exc.value)

    def test_extract_missing_item_raises(self, tmp_path):
        root = _make_prd(tmp_path, PRD_SAMPLE)
        with pytest.raises(SectionNotFoundError):
            extract("prd#§2.F-999", root)

    def test_extract_propagates_resolve_error(self, tmp_path):
        with pytest.raises(DocResolveError):
            extract("prd#§1", str(tmp_path))

    def test_extract_propagates_parse_error(self, tmp_path):
        with pytest.raises(RefParseError):
            extract("not-a-ref", str(tmp_path))

    def test_extract_strips_trailing_blank_lines(self, tmp_path):
        content = "# Doc\n\n## 1. A\n\n正文\n\n\n\n## 2. B\n\nB\n"
        _write(os.path.join(tmp_path, "docs", "prd", "prd-x-v1.md"), content)
        result = extract("prd#§1", str(tmp_path))
        assert result.endswith("正文")

    def test_extract_sub_section_numeric_prefix_only(self, tmp_path):
        # 标题为 "### 1.1" 不带文字也应命中
        content = "# Doc\n\n## 1. A\n\n### 1.1\n\nX\n\n### 1.2\n\nY\n"
        _write(os.path.join(tmp_path, "docs", "prd", "prd-x-v1.md"), content)
        result = extract("prd#§1.1", str(tmp_path))
        assert "X" in result
        assert "Y" not in result


# ---------- TestExtractBatch ----------

class TestExtractBatch:
    def test_all_success(self, tmp_path):
        root = _make_prd(tmp_path, PRD_SAMPLE)
        successes, errors = extract_batch(["prd#§1", "prd#§2"], root)
        assert len(successes) == 2
        assert len(errors) == 0
        assert successes[0][0] == "prd#§1"
        assert successes[1][0] == "prd#§2"

    def test_mixed_success_and_error(self, tmp_path):
        root = _make_prd(tmp_path, PRD_SAMPLE)
        successes, errors = extract_batch(
            ["prd#§1", "prd#§99", "bad-ref"], root
        )
        assert len(successes) == 1
        assert successes[0][0] == "prd#§1"
        assert len(errors) == 2
        error_refs = {e[0] for e in errors}
        assert "prd#§99" in error_refs
        assert "bad-ref" in error_refs

    def test_empty_list(self, tmp_path):
        successes, errors = extract_batch([], str(tmp_path))
        assert successes == []
        assert errors == []


# ---------- TestMain (CLI) ----------

class TestMain:
    def test_cli_single_success(self, tmp_path, capsys):
        root = _make_prd(tmp_path, PRD_SAMPLE)
        code = main(["--project-root", root, "prd#§1.1"])
        captured = capsys.readouterr()
        assert code == 0
        assert "=== prd#§1.1 ===" in captured.out
        assert "子背景正文" in captured.out
        assert captured.err == ""

    def test_cli_multiple_refs(self, tmp_path, capsys):
        root = _make_prd(tmp_path, PRD_SAMPLE)
        code = main(["--project-root", root, "prd#§1", "prd#§2.F-001"])
        captured = capsys.readouterr()
        assert code == 0
        assert "=== prd#§1 ===" in captured.out
        assert "=== prd#§2.F-001 ===" in captured.out
        assert "登录需求正文" in captured.out

    def test_cli_error_exit_code(self, tmp_path, capsys):
        root = _make_prd(tmp_path, PRD_SAMPLE)
        code = main(["--project-root", root, "prd#§99"])
        captured = capsys.readouterr()
        assert code == 2
        assert "[ERROR]" in captured.err
        assert "prd#§99" in captured.err

    def test_cli_mixed_returns_error_code(self, tmp_path, capsys):
        root = _make_prd(tmp_path, PRD_SAMPLE)
        code = main(["--project-root", root, "prd#§1", "prd#§99"])
        captured = capsys.readouterr()
        assert code == 2
        # 成功项仍然输出
        assert "=== prd#§1 ===" in captured.out
        # 错误项写入 stderr
        assert "prd#§99" in captured.err

    def test_cli_bad_ref_format(self, tmp_path, capsys):
        root = _make_prd(tmp_path, PRD_SAMPLE)
        code = main(["--project-root", root, "not-a-ref"])
        captured = capsys.readouterr()
        assert code == 2
        assert "[ERROR]" in captured.err


# ---------- TestExceptionHierarchy ----------

class TestExceptionHierarchy:
    def test_all_are_load_section_error(self):
        assert issubclass(RefParseError, LoadSectionError)
        assert issubclass(DocResolveError, LoadSectionError)
        assert issubclass(SectionNotFoundError, LoadSectionError)

    def test_batch_catches_all_subclasses(self, tmp_path):
        # 验证 extract_batch 的 except LoadSectionError 能捕获全部三种
        root = _make_prd(tmp_path, PRD_SAMPLE)
        _, errors = extract_batch(
            ["bad-ref", "unknown-doc#§1", "prd#§1", "prd#§99"], root
        )
        assert len(errors) == 3
