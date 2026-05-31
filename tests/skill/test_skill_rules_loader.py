"""Tests for the skill-level rules plugin loader (issue #113)."""

from __future__ import annotations

from pathlib import Path

import pytest

from cataforge.runtime.skill.builtins.code_review import wiring_patterns as wp
from cataforge.runtime.skill.builtins.testing import e2e_patterns as ep
from cataforge.runtime.skill.rules.loader import (
    CURRENT_SCHEMA_VERSION,
    RuleLoadError,
    discover_rules,
    validate_yaml_text,
)


def test_package_defaults_load_for_code_review() -> None:
    rules = discover_rules(
        "code-review",
        builtin_module="cataforge.runtime.skill.builtins.code_review",
    )
    assert ("wiring", "js-ts") in rules
    assert ("wiring", "python") in rules
    js = rules[("wiring", "js-ts")]
    assert js.schema_version == CURRENT_SCHEMA_VERSION
    assert ".tsx" in js.extensions
    assert js.raw["empty_handler_patterns"]


def test_package_defaults_load_for_testing() -> None:
    rules = discover_rules(
        "testing",
        builtin_module="cataforge.runtime.skill.builtins.testing",
    )
    assert ("e2e", "js-ts") in rules
    assert ("e2e", "python") in rules
    py = rules[("e2e", "python")]
    assert ".py" in py.extensions
    # Each backdoor pattern must carry a label per the schema
    for entry in py.raw["backdoor_patterns"]:
        assert isinstance(entry["label"], str) and entry["label"]


def test_validate_yaml_rejects_unknown_rule_type() -> None:
    bad = """
schema_version: 1
rule_type: bogus
language: js-ts
extensions: [".js"]
"""
    with pytest.raises(RuleLoadError, match="unknown rule_type"):
        validate_yaml_text(bad, "test")


def test_validate_yaml_rejects_bad_schema_version() -> None:
    bad = """
schema_version: 99
rule_type: wiring
language: js-ts
extensions: [".js"]
"""
    with pytest.raises(RuleLoadError, match="unsupported schema_version"):
        validate_yaml_text(bad, "test")


def test_validate_yaml_rejects_invalid_regex() -> None:
    bad = """
schema_version: 1
rule_type: wiring
language: js-ts
extensions: [".js"]
empty_handler_patterns:
  - regex: '['
"""
    with pytest.raises(RuleLoadError, match="invalid regex"):
        validate_yaml_text(bad, "test")


def test_validate_yaml_e2e_requires_label() -> None:
    bad = """
schema_version: 1
rule_type: e2e
language: js-ts
extensions: [".js"]
backdoor_patterns:
  - regex: 'window\\.X'
"""
    with pytest.raises(RuleLoadError, match="'label' field required"):
        validate_yaml_text(bad, "test")


def test_validate_yaml_unknown_flag() -> None:
    bad = """
schema_version: 1
rule_type: wiring
language: js-ts
extensions: [".js"]
empty_handler_patterns:
  - regex: 'x'
    flags: ['NOT_A_FLAG']
"""
    with pytest.raises(RuleLoadError, match="unknown flag"):
        validate_yaml_text(bad, "test")


def _write_project_rule(
    project_root: Path, skill_id: str, filename: str, body: str
) -> Path:
    rules_dir = project_root / ".cataforge" / "skills" / skill_id / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    path = rules_dir / filename
    path.write_text(body, encoding="utf-8")
    return path


def test_project_override_replaces_package_default(tmp_path: Path) -> None:
    """A project YAML for the same (rule_type, language) replaces the default."""
    body = """
schema_version: 1
rule_type: wiring
language: js-ts
extensions: [".js", ".ts"]
empty_handler_patterns:
  - regex: 'projectOnly'
"""
    _write_project_rule(tmp_path, "code-review", "wiring-js-ts.yaml", body)
    rules = discover_rules(
        "code-review",
        builtin_module="cataforge.runtime.skill.builtins.code_review",
        project_root=tmp_path,
    )
    js = rules[("wiring", "js-ts")]
    assert "projectOnly" in js.raw["empty_handler_patterns"][0]["regex"]
    # Project override does NOT remove other-language defaults
    assert ("wiring", "python") in rules


def test_project_can_add_new_language(tmp_path: Path) -> None:
    body = """
schema_version: 1
rule_type: wiring
language: rust
extensions: [".rs"]
empty_handler_patterns:
  - regex: 'on_[a-z]+\\s*:\\s*Box::new\\(\\|\\|\\s*\\{\\}\\)'
"""
    _write_project_rule(tmp_path, "code-review", "wiring-rust.yaml", body)
    rules = discover_rules(
        "code-review",
        builtin_module="cataforge.runtime.skill.builtins.code_review",
        project_root=tmp_path,
    )
    assert ("wiring", "rust") in rules


def test_wiring_patterns_module_exposes_languages() -> None:
    # Default (no project_root) compiles both shipped languages.
    rules = wp.load_wiring_rules()
    assert "js-ts" in rules.by_language
    assert "python" in rules.by_language
    assert rules.rule_for_extension(".tsx") is not None
    assert rules.rule_for_extension(".unknown") is None


def test_e2e_patterns_module_exposes_languages() -> None:
    rules = ep.load_e2e_rules()
    assert "js-ts" in rules.by_language
    assert "python" in rules.by_language
    assert ".py" in rules.all_extensions()


def test_e2e_python_real_input_matches_send_keys() -> None:
    rule = ep.load_e2e_rules().rule_for_extension(".py")
    assert rule is not None
    sample = "elem.send_keys('hello')"
    assert any(p.search(sample) for p in rule.real_input_patterns)


def test_code_linter_loads_project_wiring_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A project override YAML is honored at CodeLinter construction.

    Regression: the wrapper previously froze rules at import time, so a
    project's override never reached the runtime scan. The scanner now
    resolves rules from CATAFORGE_PROJECT_ROOT (injected by the runner).
    """
    from cataforge.runtime.skill.builtins.code_review.code_lint import CodeLinter

    body = """
schema_version: 1
rule_type: wiring
language: go
extensions: [".go"]
empty_handler_patterns:
  - regex: 'func\\(\\)\\s*\\{\\s*\\}'
"""
    _write_project_rule(tmp_path, "code-review", "wiring-go.yaml", body)
    monkeypatch.setenv("CATAFORGE_PROJECT_ROOT", str(tmp_path))

    linter = CodeLinter(str(tmp_path))
    assert ".go" in linter.wiring_rules.scanned_extensions()
    assert linter.wiring_rules.rule_for_extension(".go") is not None


def test_e2e_collect_loads_project_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """e2e collect() picks up a project override for an added language."""
    from cataforge.runtime.skill.builtins.testing import e2e_scan

    body = """
schema_version: 1
rule_type: e2e
language: go
extensions: [".go"]
backdoor_patterns:
  - label: go-test-hook
    regex: 'testHook'
real_input_patterns:
  - regex: 'SendKeys'
"""
    _write_project_rule(tmp_path, "testing", "e2e-go.yaml", body)
    monkeypatch.setenv("CATAFORGE_PROJECT_ROOT", str(tmp_path))

    src = tmp_path / "suite_test.go"
    src.write_text("func TestX() { testHook() }\n", encoding="utf-8")
    report = e2e_scan.collect(tmp_path, e2e_scan.project_root_from_env())
    assert report.summary["file_count"] == 1
    assert report.summary["backdoor_total"] == 1
