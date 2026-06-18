"""doc-review enforces the UC- component prefix for ui-spec docs.

A ui-spec doc that still authors components under C- (the arch Component
prefix) is flagged so authors migrate to UC-; id-continuity for ui-spec
components is tracked under UC-, not C-.
"""

from __future__ import annotations

from pathlib import Path

from cataforge.runtime.skill.builtins.doc_review.checker import DocChecker

_FM = (
    "---\nid: ui-spec-demo\ndoc_type: ui-spec\nauthor: ui-designer\n"
    "status: draft\ndeps: []\nconsumers: [tech-lead]\nvolume_type: components\n---\n"
)


def _write(tmp_path: Path, body: str) -> str:
    f = tmp_path / "ui-spec-demo-uc001-uc003.md"
    f.write_text(_FM + body, encoding="utf-8")
    return str(f)


def test_c_prefix_component_flagged_as_convention(tmp_path: Path) -> None:
    body = "# UI\n\n## 2. 组件清单\n\n### C-001: 顶栏\n- **变体**: default\n- **Props**: {}\n"
    c = DocChecker("ui-spec", _write(tmp_path, body), docs_dir=str(tmp_path))
    c.check_ui_spec()
    assert any("UC-" in e for e in c.errors), c.errors


def test_uc_prefix_component_not_flagged(tmp_path: Path) -> None:
    body = "# UI\n\n## 2. 组件清单\n\n### UC-001: 顶栏\n- **变体**: default\n- **Props**: {}\n"
    c = DocChecker("ui-spec", _write(tmp_path, body), docs_dir=str(tmp_path))
    c.check_ui_spec()
    assert not any("UC-" in e and "C-" in e for e in c.errors), c.errors


def test_id_continuity_tracks_uc_prefix(tmp_path: Path) -> None:
    body = "# UI\n\n## 2. 组件清单\n\n### UC-001: A\n\n### UC-003: B\n"
    c = DocChecker("ui-spec", _write(tmp_path, body), docs_dir=str(tmp_path))
    c.check_id_continuity()
    assert any("UC-002" in w for w in c.warnings), c.warnings


def test_components_volume_filename_detected_with_uc_range(tmp_path: Path) -> None:
    # No volume_type in frontmatter — detection must fall back to the filename
    # range label, which now uses the UC- component prefix.
    fm = (
        "---\nid: ui-spec-demo-uc001-uc014\ndoc_type: ui-spec\n"
        "author: ui-designer\nstatus: draft\ndeps: []\nconsumers: [tech-lead]\n---\n"
    )
    f = tmp_path / "ui-spec-demo-uc001-uc014.md"
    f.write_text(fm + "# UI\n\n## 2. 组件清单\n\n### UC-001: A\n", encoding="utf-8")
    c = DocChecker("ui-spec", str(f), docs_dir=str(tmp_path), volume_type=None)
    assert c.volume_type == "components"
