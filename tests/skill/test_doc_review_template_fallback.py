"""Tests for doc-review template fallback + theme registration."""

from __future__ import annotations

from pathlib import Path

from cataforge.runtime.skill.builtins.doc_review.checker import DocChecker
from cataforge.runtime.skill.builtins.doc_review.constants import VOLUME_TYPES
from cataforge.runtime.skill.builtins.doc_review.template_registry import (
    build_template_path_map,
)


def test_theme_volume_type_registered_in_constants() -> None:
    assert "theme" in VOLUME_TYPES


def test_theme_volume_template_registered() -> None:
    """ui-spec/theme must appear in the template registry so the checker
    no longer WARNs `无法从模板加载 required_sections`."""
    mapping = build_template_path_map()
    assert "ui-spec" in mapping
    assert "theme" in mapping["ui-spec"]["standard"]


def _write(p: Path, body: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


def test_check_required_sections_falls_back_to_frontmatter(tmp_path: Path) -> None:
    """When the template registry doesn't cover a (doc_type, volume_type),
    the checker must fall back to the doc's self-declared `required_sections`."""
    body = (
        "---\n"
        "id: ui-spec-x-vN-special-01\n"
        "doc_type: ui-spec\n"
        "author: ui-designer\n"
        "status: draft\n"
        "volume_type: nonexistent-volume\n"
        "deps: []\n"
        "consumers: []\n"
        "required_sections:\n"
        '  - "## 9. 自定义章节"\n'
        "---\n"
        "# x\n\n[NAV]\n[/NAV]\n\n## 9. 自定义章节\n内容\n"
    )
    doc = _write(tmp_path / "doc.md", body)

    checker = DocChecker(
        "ui-spec", str(doc),
        docs_dir=str(tmp_path), volume_type="nonexistent-volume",
        quiet=True,
    )
    checker.check_required_sections()
    # Template missing → fallback used → only the WARN about fallback,
    # no FAIL because the section is present.
    assert any("回退" in w for w in checker.warnings), checker.warnings
    assert checker.errors == []


def test_check_required_sections_fallback_flags_missing_section(
    tmp_path: Path,
) -> None:
    body = (
        "---\n"
        "id: ui-spec-x-vN-special-01\n"
        "doc_type: ui-spec\n"
        "author: ui-designer\n"
        "status: draft\n"
        "volume_type: nonexistent-volume\n"
        "deps: []\n"
        "consumers: []\n"
        "required_sections:\n"
        '  - "## 9. 必填章节"\n'
        "---\n"
        "# x\n\n[NAV]\n[/NAV]\n\n## 8. 别的章节\n内容\n"
    )
    doc = _write(tmp_path / "doc.md", body)

    checker = DocChecker(
        "ui-spec", str(doc),
        docs_dir=str(tmp_path), volume_type="nonexistent-volume",
        quiet=True,
    )
    checker.check_required_sections()
    assert any("缺少必填章节" in e for e in checker.errors), checker.errors


def test_theme_volume_detected_from_filename(tmp_path: Path) -> None:
    """`-theme-NN-slug` filenames must auto-detect volume_type=theme."""
    body = (
        "---\n"
        "id: ui-spec-x-vN-theme-04-japanese-mook\n"
        "doc_type: ui-spec\n"
        "author: ui-designer\n"
        "status: draft\n"
        "deps: []\n"
        "consumers: []\n"
        "split_from: ui-spec-x-vN\n"
        "---\n"
        "# theme\n"
    )
    doc = _write(
        tmp_path / "ui-spec-x-vN-theme-04-japanese-mook.md", body
    )
    checker = DocChecker(
        "ui-spec", str(doc), docs_dir=str(tmp_path), quiet=True,
    )
    assert checker.volume_type == "theme"


def test_deploy_spec_requires_local_stack_evidence_section(tmp_path: Path) -> None:
    """deploy-spec 模板把'本地最小栈验证证据'列为必填章节；
    Layer 1 对缺该段的 deploy-spec 文档判 fail。"""
    body = (
        "---\n"
        "id: deploy-spec-x\n"
        "doc_type: deploy-spec\n"
        "author: devops\n"
        "status: draft\n"
        "deps: []\n"
        "consumers: []\n"
        "---\n"
        "# Deployment Spec\n\n[NAV]\n[/NAV]\n\n"
        "## 1. 构建流程\n内容\n\n"
        "## 2. 环境配置\n内容\n\n"
        "## 3. CI/CD流水线\n内容\n\n"
        "## 4. 发布检查清单\n内容\n"
    )
    doc = _write(tmp_path / "deploy-spec-x.md", body)
    checker = DocChecker(
        "deploy-spec", str(doc), docs_dir=str(tmp_path), quiet=True,
    )
    # 默认 volume_type='main' 命中注册模板，required_sections 含证据段
    assert checker.volume_type == "main"
    checker.check_required_sections()
    assert any(
        "本地最小栈验证证据" in e for e in checker.errors
    ), checker.errors
