"""ui-spec components are authored under the UC- (UIComponent) prefix.

C- maps to Component, whose definition authority is arch only — a C- heading
in a ui-spec doc is treated as a reference and never minted as an entity. The
ui-spec component prefix is UC- (UIComponent, authority ui-spec). The shipped
templates and cross-doc references must use UC- so authored components actually
ingest into the graph.
"""

from __future__ import annotations

import re
from pathlib import Path

# A standalone C-NNN reference (the arch Component prefix) — C not preceded by
# an uppercase letter, so UC-NNN (UIComponent) is excluded.
_STANDALONE_C = re.compile(r"(?<![A-Z])C-\d")

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = REPO_ROOT / ".cataforge" / "skills" / "context" / "templates"


def _parsed_doc(doc_id: str, doc_type: str, body: str):
    from cataforge.domain.kg.ingest.scan import (
        ParsedDoc,
        _code_block_char_ranges,
        _heading_spans,
    )

    return ParsedDoc(
        doc_id=doc_id,
        doc_type=doc_type,
        file_path=Path(f"{doc_id}.md"),
        mtime=0.0,
        raw=body,
        body=body,
        body_offset=0,
        sections=_heading_spans(body, 0),
        code_block_offsets=_code_block_char_ranges(body),
    )


def _entities(doc_type: str, body: str):
    from cataforge.domain.kg.ingest.entity_extract import extract_entities

    return list(extract_entities(_parsed_doc(doc_type, doc_type, body)))


# --- extraction semantics: UC- works, C- is a no-op in ui-spec ----------------


def test_uc_prefix_extracts_as_uicomponent_in_ui_spec() -> None:
    body = "# UI\n\n## 2. 组件清单\n\n### UC-001: 顶栏（TopBar）\n\n- **变体**: default\n"
    ents = _entities("ui-spec", body)
    by_id = {e.entity_id: e for e in ents}
    assert "UC-001" in by_id
    assert by_id["UC-001"].class_name == "UIComponent"


def test_c_prefix_not_extracted_in_ui_spec() -> None:
    # C-=Component, authority arch — in a ui-spec doc it is a reference, so no
    # entity is minted. This is exactly the trap the UC- migration removes.
    body = "# UI\n\n## 2. 组件清单\n\n### C-001: 顶栏（TopBar）\n\n- **变体**: default\n"
    assert not any(e.entity_id == "C-001" for e in _entities("ui-spec", body))


# --- shipped templates must author components under UC- -----------------------


def _read(rel: str) -> str:
    return (TEMPLATES / rel).read_text(encoding="utf-8")


def test_standard_ui_spec_template_uses_uc_prefix() -> None:
    text = _read("standard/ui-spec.md")
    assert "### UC-" in text
    assert "### C-" not in text
    assert not _STANDALONE_C.search(text)  # NAV / 使用组件 references migrated too


def test_lite_ui_spec_template_uses_uc_prefix() -> None:
    text = _read("lite/ui-spec-lite.md")
    assert "### UC-" in text
    assert "### C-" not in text


def test_components_volume_template_uses_uc_prefix() -> None:
    text = _read("volumes/ui-spec-components.md")
    assert "### UC-" in text
    assert "### C-" not in text
    assert "-uc{start}-uc{end}" in text  # volume id range label migrated


def test_dev_plan_template_references_ui_spec_uc() -> None:
    text = _read("standard/dev-plan.md")
    assert "ui-spec#UC-" in text
    assert "ui-spec#C-" not in text


def test_shipped_standard_ui_spec_components_are_extractable() -> None:
    # The end-to-end guarantee: a ui-spec authored straight from the shipped
    # template yields at least one UIComponent entity.
    text = _read("standard/ui-spec.md")
    ents = _entities("ui-spec", text)
    assert any(e.class_name == "UIComponent" for e in ents)
