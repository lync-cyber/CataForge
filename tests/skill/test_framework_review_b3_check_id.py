"""B3 — anchor-based check_id reconciliation.

Synthetic-project tests for the new <!-- check_id: xxx --> anchor
strategy in check_b3_manifest_drift. The anchor path is preferred
when present; delegation marker is the fallback; token heuristic is
the legacy path.

Covers:
- happy path: SKILL.md anchors every manifest entry → no findings
- orphan anchor: SKILL.md anchor for an ID not in manifest → FAIL
- missing anchor: manifest entry has no anchor → FAIL
- mixed mode: anchor + delegation marker → only orphan anchors fail
  (missing anchors silently allowed because delegation opts out of
  exhaustive coverage)
- delegation alone (no anchors): unchanged — passes if manifest exists
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType

from cataforge.skill.builtins.framework_review.framework_check import (
    Report,
    check_b3_manifest_drift,
)


def _make_skill_md(
    tmp_path: Path,
    skill_id: str,
    body: str,
) -> Path:
    """Write a minimal SKILL.md with the given Layer 1 section body."""
    skill_dir = tmp_path / ".cataforge" / "skills" / skill_id
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {skill_id}\ndescription: test fixture\n---\n"
        f"# {skill_id}\n\n"
        f"## 能力边界\n- test\n\n"
        f"## Layer 1 检查项 (test_check.py)\n\n{body}\n\n"
        f"## 效率策略\n- test\n",
        encoding="utf-8",
    )
    return tmp_path


def _stub_manifest_module(monkeypatch, module_name: str, manifest: tuple) -> None:
    """Inject a fake builtin module exporting the given CHECKS_MANIFEST."""
    fake_module = ModuleType(module_name)
    fake_module.CHECKS_MANIFEST = manifest  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, module_name, fake_module)


# Reuse the existing builtin map keys so check_b3_manifest_drift picks
# our fixture up. Using "code-review" → "cataforge.skill.builtins.code_review"
# means we must also stub-import that module to avoid the real one
# loading.
_TEST_SKILL_ID = "code-review"
_TEST_MODULE = "cataforge.skill.builtins.code_review"


def test_b3_anchor_happy_path_no_findings(tmp_path: Path, monkeypatch) -> None:
    """Every manifest ID has a matching anchor → no findings."""
    body = (
        "- 通用文档结构\n"
        "  <!-- check_id: ID_A -->\n"
        "- 文件大小阈值\n"
        "  <!-- check_id: ID_B -->\n"
    )
    _make_skill_md(tmp_path, _TEST_SKILL_ID, body)
    _stub_manifest_module(
        monkeypatch,
        _TEST_MODULE,
        (
            {"id": "ID_A", "title": "alpha title", "severity": "fail"},
            {"id": "ID_B", "title": "beta title", "severity": "warn"},
        ),
    )

    report = Report()
    check_b3_manifest_drift(tmp_path, report)
    assert report.findings == [], (
        f"happy anchor path should produce no findings, got: "
        f"{[f.render() for f in report.findings]}"
    )


def test_b3_orphan_anchor_fails(tmp_path: Path, monkeypatch) -> None:
    """Anchor references an ID that no manifest entry declares → FAIL."""
    body = (
        "- 已有的检查\n"
        "  <!-- check_id: ID_A -->\n"
        "- 不存在的检查\n"
        "  <!-- check_id: ID_RENAMED_AWAY -->\n"
    )
    _make_skill_md(tmp_path, _TEST_SKILL_ID, body)
    _stub_manifest_module(
        monkeypatch,
        _TEST_MODULE,
        ({"id": "ID_A", "title": "alpha", "severity": "fail"},),
    )

    report = Report()
    check_b3_manifest_drift(tmp_path, report)

    orphan_findings = [
        f
        for f in report.findings
        if "ID_RENAMED_AWAY" in f.message
    ]
    assert len(orphan_findings) == 1, (
        f"expected 1 orphan-anchor FAIL, got: "
        f"{[f.render() for f in report.findings]}"
    )
    assert orphan_findings[0].severity == "FAIL"
    assert "no matching manifest entry" in orphan_findings[0].message


def test_b3_missing_anchor_fails(tmp_path: Path, monkeypatch) -> None:
    """Manifest entry has no anchor in prose → FAIL."""
    body = (
        "- 已锚定的检查\n"
        "  <!-- check_id: ID_A -->\n"
    )
    _make_skill_md(tmp_path, _TEST_SKILL_ID, body)
    _stub_manifest_module(
        monkeypatch,
        _TEST_MODULE,
        (
            {"id": "ID_A", "title": "alpha", "severity": "fail"},
            {"id": "ID_B", "title": "beta", "severity": "fail"},
            {"id": "ID_C", "title": "gamma", "severity": "warn"},
        ),
    )

    report = Report()
    check_b3_manifest_drift(tmp_path, report)

    missing_findings = [
        f
        for f in report.findings
        if "no <!-- check_id:" in f.message
    ]
    assert len(missing_findings) == 2  # ID_B and ID_C
    missing_ids = {
        f.message.split("'")[1] for f in missing_findings
    }
    assert missing_ids == {"ID_B", "ID_C"}


def test_b3_mixed_anchor_and_delegation_only_orphan_fails(
    tmp_path: Path, monkeypatch
) -> None:
    """Anchor + delegation marker → only orphan anchors fail.

    Missing anchors are silently allowed because the delegation marker
    explicitly opts out of exhaustive prose coverage. Useful when the
    SKILL.md wants to surface the most-important checks in prose but
    leave less-important ones to the manifest alone.
    """
    body = (
        "> 权威清单见 `cataforge.skill.builtins.X.CHECKS_MANIFEST`。\n\n"
        "- 关键检查\n"
        "  <!-- check_id: ID_A -->\n"
        "- 误锚点\n"
        "  <!-- check_id: ID_GHOST -->\n"
    )
    _make_skill_md(tmp_path, _TEST_SKILL_ID, body)
    _stub_manifest_module(
        monkeypatch,
        _TEST_MODULE,
        (
            {"id": "ID_A", "title": "alpha", "severity": "fail"},
            {"id": "ID_B", "title": "beta", "severity": "warn"},  # not anchored
        ),
    )

    report = Report()
    check_b3_manifest_drift(tmp_path, report)

    # Orphan anchor → FAIL.
    orphan_findings = [
        f for f in report.findings if "ID_GHOST" in f.message
    ]
    assert len(orphan_findings) == 1
    assert orphan_findings[0].severity == "FAIL"

    # Missing anchor for ID_B → silently allowed because of delegation.
    missing_findings = [
        f for f in report.findings if "ID_B" in f.message and "no <!--" in f.message
    ]
    assert missing_findings == []


def test_b3_delegation_alone_unchanged(tmp_path: Path, monkeypatch) -> None:
    """Delegation marker without anchors → manifest existence is the only
    contract (legacy delegation behavior preserved)."""
    body = (
        "> 权威清单见 `cataforge.skill.builtins.X.CHECKS_MANIFEST`（"
        "framework-review 自动对账，本段与 manifest 不一致即 FAIL）。\n\n"
        "- 检查 A 简述\n"
        "- 检查 B 简述\n"
    )
    _make_skill_md(tmp_path, _TEST_SKILL_ID, body)
    _stub_manifest_module(
        monkeypatch,
        _TEST_MODULE,
        (
            {"id": "ID_A", "title": "title that doesn't appear in prose", "severity": "fail"},
            {"id": "ID_B", "title": "another rephrased title", "severity": "warn"},
        ),
    )

    report = Report()
    check_b3_manifest_drift(tmp_path, report)
    # Delegation: prose-manifest mismatch is not checked.
    assert report.findings == []


def test_b3_legacy_token_path_still_works(tmp_path: Path, monkeypatch) -> None:
    """No anchors + no delegation → fall back to token heuristic.

    Manifest title's significant tokens must appear in the section. We
    verify a happy case (token survives) and a fail case (token absent).
    """
    body = "- 文档结构检查与字段校验\n- 引用图完整性\n"
    _make_skill_md(tmp_path, _TEST_SKILL_ID, body)
    _stub_manifest_module(
        monkeypatch,
        _TEST_MODULE,
        (
            # Happy: "字段校验" is in body → token "字段校验" matches.
            {"id": "ID_A", "title": "字段校验", "severity": "fail"},
            # Fail: no signal of "完全不相关的检查" tokens in body.
            {"id": "ID_B", "title": "完全不相关的检查", "severity": "warn"},
        ),
    )

    report = Report()
    check_b3_manifest_drift(tmp_path, report)

    # The happy entry passes. The fail entry triggers a finding.
    fail_findings = [
        f for f in report.findings if "完全不相关的检查" in f.message
    ]
    assert len(fail_findings) == 1
    assert fail_findings[0].severity == "FAIL"
