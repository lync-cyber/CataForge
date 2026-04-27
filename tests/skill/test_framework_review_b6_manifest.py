"""B6-ε — HOOKS_MANIFEST drift detection.

Tests that hooks.yaml entries cross-validate against
``cataforge.hook.manifest.HOOKS_MANIFEST``:

* Orphan reference (script in hooks.yaml not in manifest) → FAIL
* Unwired manifest entry (manifest entry not referenced) → WARN
* ``custom:`` prefix scripts opt out (always pass)
* Manifest catalog must include every real builtin .py target
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType

from cataforge.skill.builtins.framework_review.framework_check import (
    Report,
    check_b6_hook_consistency,
)


def _write_minimal_project(
    tmp_path: Path,
    hooks_yaml_body: str,
) -> Path:
    """Write a minimal .cataforge/ tree with a hooks.yaml ready to audit."""
    hooks_dir = tmp_path / ".cataforge" / "hooks"
    hooks_dir.mkdir(parents=True)
    (hooks_dir / "hooks.yaml").write_text(hooks_yaml_body, encoding="utf-8")
    # custom dir must exist for resolver to work without errors
    (hooks_dir / "custom").mkdir()
    return tmp_path


def _stub_manifest_module(monkeypatch, names: list[str]) -> None:
    """Inject a fake cataforge.hook.manifest with controlled entries."""
    fake = ModuleType("cataforge.hook.manifest")
    entries = tuple(
        {
            "name": n,
            "events": ("PostToolUse",),
            "default_capability": "file_edit",
            "default_type": "observe",
            "description": f"test {n}",
            "safety_critical": False,
        }
        for n in names
    )
    fake.HOOKS_MANIFEST = entries  # type: ignore[attr-defined]
    fake.manifest_names = lambda: frozenset(names)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "cataforge.hook.manifest", fake)


def test_b6_epsilon_happy_all_referenced(tmp_path: Path, monkeypatch) -> None:
    """All hooks.yaml scripts in manifest, all manifest entries wired → no ε findings."""
    _write_minimal_project(
        tmp_path,
        """
schema_version: 2
hooks:
  PostToolUse:
    - matcher_capability: file_edit
      script: alpha
      type: observe
    - matcher_capability: file_edit
      script: beta
      type: observe
""",
    )
    _stub_manifest_module(monkeypatch, ["alpha", "beta"])

    report = Report()
    check_b6_hook_consistency(tmp_path, report)
    eps = [f for f in report.findings if f.check_id == "B6_hook_manifest_drift"]
    assert eps == [], f"unexpected ε findings: {[f.render() for f in eps]}"


def test_b6_epsilon_orphan_reference_fails(tmp_path: Path, monkeypatch) -> None:
    """hooks.yaml references script not in manifest → FAIL."""
    _write_minimal_project(
        tmp_path,
        """
schema_version: 2
hooks:
  PostToolUse:
    - matcher_capability: file_edit
      script: notify_util
      type: observe
""",
    )
    _stub_manifest_module(monkeypatch, ["alpha"])

    report = Report()
    check_b6_hook_consistency(tmp_path, report)
    fails = [
        f for f in report.findings
        if f.check_id == "B6_hook_manifest_drift"
        and f.severity == "FAIL"
        and "notify_util" in f.message
    ]
    assert len(fails) == 1
    assert "HOOKS_MANIFEST" in fails[0].message


def test_b6_epsilon_unwired_manifest_warns(tmp_path: Path, monkeypatch) -> None:
    """Manifest entry never referenced by hooks.yaml → WARN (dead inventory)."""
    _write_minimal_project(
        tmp_path,
        """
schema_version: 2
hooks:
  PostToolUse:
    - matcher_capability: file_edit
      script: alpha
      type: observe
""",
    )
    _stub_manifest_module(monkeypatch, ["alpha", "unused_helper"])

    report = Report()
    check_b6_hook_consistency(tmp_path, report)
    warns = [
        f for f in report.findings
        if f.check_id == "B6_hook_manifest_drift"
        and f.severity == "WARN"
        and "unused_helper" in f.message
    ]
    assert len(warns) == 1
    assert "dead inventory" in warns[0].message


def test_b6_epsilon_custom_prefix_skipped(tmp_path: Path, monkeypatch) -> None:
    """custom: scripts not subject to manifest validation."""
    _write_minimal_project(
        tmp_path,
        """
schema_version: 2
hooks:
  PostToolUse:
    - matcher_capability: file_edit
      script: 'custom:my-project-specific-hook'
      type: observe
""",
    )
    # Also create the custom .py so α doesn't fail (irrelevant for this test).
    custom_py = tmp_path / ".cataforge" / "hooks" / "custom" / "my-project-specific-hook.py"
    custom_py.write_text("# ok\n", encoding="utf-8")
    _stub_manifest_module(monkeypatch, [])  # empty manifest

    report = Report()
    check_b6_hook_consistency(tmp_path, report)
    fails = [
        f for f in report.findings
        if f.check_id == "B6_hook_manifest_drift" and f.severity == "FAIL"
    ]
    assert fails == []


def test_b6_epsilon_manifest_unimportable_skips(tmp_path: Path, monkeypatch) -> None:
    """Older wheel without manifest module → ε is no-op (no findings)."""
    _write_minimal_project(
        tmp_path,
        """
schema_version: 2
hooks:
  PostToolUse:
    - matcher_capability: file_edit
      script: anything_at_all
      type: observe
""",
    )
    # Force ImportError by injecting a sentinel that raises.
    monkeypatch.setitem(sys.modules, "cataforge.hook.manifest", None)

    report = Report()
    check_b6_hook_consistency(tmp_path, report)
    eps = [f for f in report.findings if f.check_id == "B6_hook_manifest_drift"]
    assert eps == []


def test_real_manifest_covers_all_real_builtin_scripts() -> None:
    """The shipped HOOKS_MANIFEST must catalog every real builtin .py target.

    notify_util.py is intentionally excluded as it's a helper.  Anything
    else in cataforge/hook/scripts/ that's not in the manifest is a
    registration bug (the file ships but isn't an advertised hook).
    """
    import cataforge.hook.scripts as scripts_pkg
    from cataforge.hook.manifest import manifest_names

    scripts_dir = Path(scripts_pkg.__file__).parent
    real_modules = {
        p.stem for p in scripts_dir.glob("*.py")
        if p.stem not in ("__init__", "notify_util")
    }
    declared = manifest_names()
    missing_from_manifest = real_modules - declared
    assert not missing_from_manifest, (
        f"these .py modules ship in cataforge.hook.scripts but are NOT "
        f"in HOOKS_MANIFEST: {sorted(missing_from_manifest)}"
    )
    extra_in_manifest = declared - real_modules
    assert not extra_in_manifest, (
        f"these names are in HOOKS_MANIFEST but have no .py file: "
        f"{sorted(extra_in_manifest)}"
    )
