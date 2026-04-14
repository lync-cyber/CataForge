"""从 .cataforge/rules/ + overrides 生成 .cursor/rules/ MDC 文件。"""
from __future__ import annotations
import re
from pathlib import Path


def generate_cursor_rules(
    cataforge_rules_dir: Path,
    overrides_rules_dir: Path | None,
    output_dir: Path,
) -> list[str]:
    """生成 .cursor/rules/ 目录。

    策略:
    1. .cataforge/rules/*.md → .cursor/rules/*.mdc (添加 MDC frontmatter)
    2. overrides/rules/*.md → .cursor/rules/*.mdc (平台专属规则)
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    generated: list[str] = []

    for md_file in sorted(cataforge_rules_dir.glob("*.md")):
        mdc_name = md_file.stem.lower() + ".mdc"
        mdc_path = output_dir / mdc_name
        _convert_to_mdc(md_file, mdc_path, always_apply=True)
        generated.append(str(mdc_path))

    if overrides_rules_dir and overrides_rules_dir.is_dir():
        for md_file in sorted(overrides_rules_dir.glob("*.md")):
            mdc_name = md_file.stem.lower() + ".mdc"
            mdc_path = output_dir / mdc_name
            _convert_to_mdc(md_file, mdc_path, always_apply=True)
            generated.append(str(mdc_path))

    return generated


def _convert_to_mdc(source: Path, target: Path, always_apply: bool = False) -> None:
    """Markdown → MDC 格式转换。"""
    content = source.read_text(encoding="utf-8")
    title = _extract_title(content)
    frontmatter = (
        f'---\ndescription: "{title}"\n'
        f"alwaysApply: {str(always_apply).lower()}\n---\n\n"
    )
    target.write_text(frontmatter + content, encoding="utf-8")


def _extract_title(content: str) -> str:
    m = re.match(r"^#\s+(.+)", content)
    return m.group(1).strip() if m else "CataForge Rule"
