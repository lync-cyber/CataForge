"""A faithfully-filled agile-lite template passes its doc-review typed check.

Guards the lite templates against regressing the fields the typed checks
require — without them, agile-lite docs FAIL Layer-1 on the happy path
(missing user stories, non-functional section, API request).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from cataforge.runtime.skill.builtins.doc_review.checker import DocChecker

LITE_DIR = (
    Path(__file__).resolve().parents[2] / ".cataforge" / "skills" / "context" / "templates" / "lite"
)


def _fill(template_text: str) -> str:
    """Replace ``{placeholder}`` tokens with a dummy value so the doc reads as
    faithfully filled in."""
    return re.sub(r"\{[^{}]*\}", "demo", template_text)


def _typed_errors(tmp_path: Path, doc_type: str, template_name: str, method: str) -> list[str]:
    filled = _fill((LITE_DIR / template_name).read_text(encoding="utf-8"))
    doc = tmp_path / template_name
    doc.write_text(filled, encoding="utf-8")
    checker = DocChecker(doc_type, str(doc), docs_dir=str(tmp_path))
    getattr(checker, method)()
    return checker.errors


@pytest.mark.parametrize(
    ("doc_type", "template", "method"),
    [
        ("prd", "prd-lite.md", "check_prd"),
        ("arch", "arch-lite.md", "check_arch"),
        ("dev-plan", "dev-plan-lite.md", "check_dev_plan"),
    ],
)
def test_filled_lite_template_passes_typed_check(
    tmp_path: Path, doc_type: str, template: str, method: str
) -> None:
    errors = _typed_errors(tmp_path, doc_type, template, method)
    assert errors == [], errors
