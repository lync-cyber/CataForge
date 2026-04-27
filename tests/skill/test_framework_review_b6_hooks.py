"""B6 — hook meta-asset audit.

Synthetic-project tests that exercise check_b6_hook_consistency in
isolation. The real project's hooks.yaml passes, so we manufacture each
failure mode under tmp_path and assert the right finding fires.

Covers:
- α: hooks.yaml references a script that has no .py file → FAIL
- β: a referenced script exists but has a SyntaxError → FAIL
- γ: matcher_capability typo (not in CAPABILITY_IDS / EXTENDED) → FAIL
- δ: profile.yaml hooks.degradation missing or orphan → WARN x2
- happy path: well-formed project → no B6 findings
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cataforge.skill.builtins.framework_review.framework_check import (
    Report,
    check_b6_hook_consistency,
)


def _make_project(
    tmp_path: Path,
    hooks_yaml: str,
    *,
    custom_scripts: dict[str, str] | None = None,
    profile_yaml: str | None = None,
) -> Path:
    """Spin up a minimal .cataforge/ tree under tmp_path."""
    cf = tmp_path / ".cataforge"
    (cf / "hooks").mkdir(parents=True)
    (cf / "hooks" / "hooks.yaml").write_text(hooks_yaml, encoding="utf-8")
    if custom_scripts:
        custom_dir = cf / "hooks" / "custom"
        custom_dir.mkdir(parents=True, exist_ok=True)
        for name, src in custom_scripts.items():
            (custom_dir / f"{name}.py").write_text(src, encoding="utf-8")
    if profile_yaml is not None:
        plat_dir = cf / "platforms" / "claude-code"
        plat_dir.mkdir(parents=True)
        (plat_dir / "profile.yaml").write_text(profile_yaml, encoding="utf-8")
    return tmp_path


# Minimal valid hooks.yaml referencing only one builtin (guard_dangerous)
# that exists in cataforge.hook.scripts. The B6 check resolves this via
# importlib.resources, so it works regardless of cwd.
_HAPPY_HOOKS_YAML = """\
schema_version: 2
hooks:
  PreToolUse:
    - matcher_capability: shell_exec
      script: guard_dangerous
      type: block
"""

_HAPPY_PROFILE_YAML = """\
hooks:
  degradation:
    guard_dangerous: native
"""


def _without_manifest_drift(report: Report) -> list:
    """Filter out B6_hook_manifest_drift findings.

    B6-ε (manifest drift) is exercised by test_framework_review_b6_manifest.py
    against synthetic manifests. Tests in this file use a minimal hooks.yaml
    fixture that intentionally wires only guard_dangerous — so the real
    HOOKS_MANIFEST (9 entries) will fire 8 unwired-WARN ε findings, which
    is correct behavior but unrelated to what α/β/γ/δ tests assert.
    """
    return [f for f in report.findings if f.check_id != "B6_hook_manifest_drift"]


def test_b6_happy_path_no_findings(tmp_path: Path) -> None:
    root = _make_project(
        tmp_path,
        _HAPPY_HOOKS_YAML,
        profile_yaml=_HAPPY_PROFILE_YAML,
    )
    report = Report()
    check_b6_hook_consistency(root, report)
    relevant = _without_manifest_drift(report)
    assert relevant == [], (
        f"happy path should produce no α/β/γ/δ findings, got: "
        f"{[f.render() for f in relevant]}"
    )


def test_b6_alpha_unreachable_script_fails(tmp_path: Path) -> None:
    """α: hooks.yaml references a script with no .py file → FAIL."""
    hooks_yaml = """\
schema_version: 2
hooks:
  PreToolUse:
    - matcher_capability: shell_exec
      script: this_script_does_not_exist
      type: block
"""
    root = _make_project(tmp_path, hooks_yaml)
    report = Report()
    check_b6_hook_consistency(root, report)

    findings = [f for f in report.findings if "reachability" in f.check_id]
    assert len(findings) == 1
    assert findings[0].severity == "FAIL"
    assert "this_script_does_not_exist" in findings[0].location


def test_b6_beta_syntax_error_in_custom_script_fails(tmp_path: Path) -> None:
    """β: referenced custom script has a SyntaxError → FAIL."""
    hooks_yaml = """\
schema_version: 2
hooks:
  PostToolUse:
    - matcher_capability: file_edit
      script: custom:my_broken_hook
      type: observe
"""
    root = _make_project(
        tmp_path,
        hooks_yaml,
        custom_scripts={"my_broken_hook": "def main(:\n    pass\n"},  # SyntaxError
    )
    report = Report()
    check_b6_hook_consistency(root, report)

    findings = [f for f in report.findings if "syntax" in f.check_id]
    assert len(findings) == 1
    assert findings[0].severity == "FAIL"
    assert "my_broken_hook" in findings[0].location


def test_b6_gamma_unknown_matcher_capability_fails(tmp_path: Path) -> None:
    """γ: matcher_capability not in CAPABILITY_IDS / EXTENDED → FAIL."""
    hooks_yaml = """\
schema_version: 2
hooks:
  PreToolUse:
    - matcher_capability: typo_capability_xyz
      script: guard_dangerous
      type: block
"""
    root = _make_project(tmp_path, hooks_yaml)
    report = Report()
    check_b6_hook_consistency(root, report)

    findings = [f for f in report.findings if "matcher_capability" in f.check_id]
    assert len(findings) == 1
    assert findings[0].severity == "FAIL"
    assert "typo_capability_xyz" in findings[0].location


def test_b6_delta_missing_degradation_warns(tmp_path: Path) -> None:
    """δ: profile.yaml has no degradation flag for a referenced script → WARN."""
    profile_no_degradation = """\
hooks:
  degradation: {}
"""
    root = _make_project(
        tmp_path,
        _HAPPY_HOOKS_YAML,
        profile_yaml=profile_no_degradation,
    )
    report = Report()
    check_b6_hook_consistency(root, report)

    findings = [
        f
        for f in report.findings
        if "degradation_coverage" in f.check_id and f.severity == "WARN"
    ]
    assert len(findings) == 1
    assert "guard_dangerous" in findings[0].message
    assert "no degradation flag" in findings[0].message


def test_b6_delta_orphan_degradation_warns(tmp_path: Path) -> None:
    """δ: profile.yaml has a degradation entry for a script no longer in
    hooks.yaml → WARN (dead config)."""
    profile_with_orphan = """\
hooks:
  degradation:
    guard_dangerous: native
    removed_script_xyz: degraded
"""
    root = _make_project(
        tmp_path,
        _HAPPY_HOOKS_YAML,
        profile_yaml=profile_with_orphan,
    )
    report = Report()
    check_b6_hook_consistency(root, report)

    findings = [
        f
        for f in report.findings
        if "degradation_coverage" in f.check_id and f.severity == "WARN"
    ]
    assert len(findings) == 1
    assert "removed_script_xyz" in findings[0].message
    assert "dead config" in findings[0].message


def test_b6_no_hooks_yaml_silently_skips(tmp_path: Path) -> None:
    """Projects without .cataforge/hooks/hooks.yaml shouldn't fail B6 —
    framework-review supports projects that opt out of hooks entirely."""
    (tmp_path / ".cataforge").mkdir()
    report = Report()
    check_b6_hook_consistency(tmp_path, report)
    assert report.findings == []


def test_b6_malformed_yaml_fails(tmp_path: Path) -> None:
    """Malformed hooks.yaml itself → single FAIL with parse error."""
    root = _make_project(tmp_path, "not: valid: yaml: [\n")
    report = Report()
    check_b6_hook_consistency(root, report)
    assert len(report.findings) == 1
    assert report.findings[0].severity == "FAIL"
    assert "parse" in report.findings[0].message.lower()


@pytest.mark.parametrize(
    "script,prefix_stripped",
    [("guard_dangerous", "guard_dangerous"), ("custom:my_hook", "my_hook")],
)
def test_b6_custom_prefix_normalized_for_degradation(
    tmp_path: Path, script: str, prefix_stripped: str
) -> None:
    """Degradation parity must compare normalized names (custom: stripped),
    so a degradation entry "my_hook: degraded" satisfies a hooks.yaml
    "script: custom:my_hook" reference."""
    hooks_yaml = f"""\
schema_version: 2
hooks:
  PreToolUse:
    - matcher_capability: shell_exec
      script: {script}
      type: block
"""
    profile_yaml = f"""\
hooks:
  degradation:
    {prefix_stripped}: native
"""
    custom_scripts = (
        {"my_hook": "def main():\n    pass\n"} if script.startswith("custom:") else None
    )
    root = _make_project(
        tmp_path,
        hooks_yaml,
        custom_scripts=custom_scripts,
        profile_yaml=profile_yaml,
    )
    report = Report()
    check_b6_hook_consistency(root, report)

    coverage_findings = [
        f for f in report.findings if "degradation_coverage" in f.check_id
    ]
    assert coverage_findings == [], (
        f"custom: prefix should be stripped before degradation parity check, "
        f"got: {[f.render() for f in coverage_findings]}"
    )
