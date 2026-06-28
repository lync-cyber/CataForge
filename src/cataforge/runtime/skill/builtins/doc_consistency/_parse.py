"""Doc-consistency parsing helpers + cross-doc id regexes."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from cataforge.utils.frontmatter import split_yaml_frontmatter as _split_fm
from cataforge.utils.md_parse import strip_code_blocks


def _load_doc(path: Path) -> tuple[dict[str, Any], str]:
    """Return (frontmatter_dict, body_text) for a markdown doc."""
    content = path.read_text(errors="replace")
    fm, body = _split_fm(content)
    return fm or {}, body if body else content


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
    return set(re.findall(rf"{prefix}-\d+", strip_code_blocks(content)))


def _read_all_content(paths: list[Path]) -> str:
    """Concatenate content of all files."""
    parts = []
    for p in paths:
        try:
            parts.append(p.read_text(errors="replace"))
        except OSError:
            continue
    return "\n".join(parts)
