"""B3 builtin-map integrity and B4 dynamic constant sourcing.

Guards two self-audit blindspots: a builtin listed in B3's reconciliation
map with no on-disk SKILL.md (its manifest then silently un-reconciled), and
B4 matching a hardcoded copy of a framework.json constant value instead of
the live value.
"""

from __future__ import annotations

import json
from pathlib import Path

from cataforge.core.paths import ProjectPaths
from cataforge.runtime.skill.builtins.framework_review._framework_data import (
    build_constant_literals,
)
from cataforge.runtime.skill.builtins.framework_review.checks.b3 import (
    _BUILTIN_MAP,
    check_b3_manifest_drift,
)
from cataforge.runtime.skill.builtins.framework_review.checks.b4 import (
    check_b4_hardcoded_constants,
)
from cataforge.runtime.skill.builtins.framework_review.framework_check import Report

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_every_builtin_map_skill_has_a_reconcilable_skill_md() -> None:
    """A skill is in B3's map only if it ships a SKILL.md to reconcile.

    doc-review's SKILL.md was folded into the context skill; leaving it mapped
    made B3 skip its manifest with no signal. testing, which does ship a
    SKILL.md, was missing despite publicly promising the reconciliation.
    """
    for skill_id in _BUILTIN_MAP:
        skill_md = ProjectPaths(REPO_ROOT).skill_dir(skill_id) / "SKILL.md"
        assert skill_md.is_file(), (
            f"{skill_id} is in B3 _BUILTIN_MAP but has no {skill_md} to reconcile"
        )
    assert "testing" in _BUILTIN_MAP
    assert "doc-review" not in _BUILTIN_MAP


def test_b3_reconciles_repo_skills_without_fail() -> None:
    """The shipped review skills reconcile against their builtins."""
    report = Report()
    check_b3_manifest_drift(REPO_ROOT, report)
    fails = [
        f for f in report.findings if f.check_id == "B3_manifest_drift" and f.severity == "FAIL"
    ]
    assert not fails, [f.message for f in fails]


def _make_project(tmp_path: Path, max_questions: int) -> Path:
    cf = tmp_path / ".cataforge"
    (cf / "skills" / "demo").mkdir(parents=True)
    (cf / "framework.json").write_text(
        json.dumps(
            {
                "version": "0.1.0",
                "runtime_api_version": "1.0",
                "constants": {"MAX_QUESTIONS_PER_BATCH": max_questions},
            }
        ),
        encoding="utf-8",
    )
    (cf / "skills" / "demo" / "SKILL.md").write_text(
        "---\nname: demo\n---\n# demo\n\n每批问题 ≤4 问。\n",
        encoding="utf-8",
    )
    return tmp_path


def test_b4_literal_tracks_live_framework_value(tmp_path: Path) -> None:
    """build_constant_literals reflects the framework.json value, not a copy."""
    root = _make_project(tmp_path, max_questions=4)
    literals = dict((n, h) for n, _p, h in build_constant_literals(root))
    assert literals["MAX_QUESTIONS_PER_BATCH"] == "≤4 问"


def test_b4_flags_text_matching_the_live_value(tmp_path: Path) -> None:
    """A doc with ``≤4 问`` is flagged when the constant is 4, not when it is 3.

    The previous static literal only ever matched ``≤3``, so a project that
    bumped the constant to 4 silently lost B4 coverage.
    """
    root = _make_project(tmp_path, max_questions=4)
    report = Report()
    check_b4_hardcoded_constants(root, report)
    hits = [f for f in report.findings if f.check_id == "B4_hardcoded_constants"]
    assert any("MAX_QUESTIONS_PER_BATCH" in f.message for f in hits), [f.message for f in hits]

    root3 = _make_project(tmp_path / "v3", max_questions=3)
    report3 = Report()
    check_b4_hardcoded_constants(root3, report3)
    hits3 = [
        f
        for f in report3.findings
        if f.check_id == "B4_hardcoded_constants" and "MAX_QUESTIONS_PER_BATCH" in f.message
    ]
    assert not hits3, "≤4 问 must not match when the constant is 3"
