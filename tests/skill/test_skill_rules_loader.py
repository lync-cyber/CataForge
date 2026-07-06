"""Tests for the skill-level rules plugin loader (issue #113)."""

from __future__ import annotations

from pathlib import Path

import pytest

from cataforge.runtime.skill.builtins.code_review.checks import wiring as wp
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
    js = rules[("wiring", "js-ts")]
    assert js.schema_version == CURRENT_SCHEMA_VERSION
    assert js.scope == "language"
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


def test_rule_type_registry_has_builtins() -> None:
    from cataforge.runtime.skill.rules.loader import RULE_TYPE_SCHEMAS

    assert {"wiring", "e2e", "doc_terms"} <= set(RULE_TYPE_SCHEMAS)


def test_validate_doc_terms_requires_label() -> None:
    bad = """
schema_version: 2
scope: language
rule_type: doc_terms
language: zh
extensions: []
forbidden_terms:
  - regex: 'simply'
"""
    with pytest.raises(RuleLoadError, match="'label' field required"):
        validate_yaml_text(bad, "test")


def test_validate_doc_terms_ok() -> None:
    good = """
schema_version: 2
scope: language
rule_type: doc_terms
language: zh
extensions: []
forbidden_terms:
  - regex: 'simply'
    label: marketing-adverb
"""
    spec = validate_yaml_text(good, "test")
    assert spec.rule_type == "doc_terms"
    assert spec.raw["forbidden_terms"][0]["label"] == "marketing-adverb"


def test_register_custom_rule_type_roundtrip() -> None:
    from cataforge.runtime.skill.rules.loader import (
        RULE_TYPE_SCHEMAS,
        register_rule_type,
    )

    register_rule_type("custom_x", list_pattern_keys=[("foo_patterns", False)])
    try:
        spec = validate_yaml_text(
            """
schema_version: 2
scope: language
rule_type: custom_x
language: any
extensions: []
foo_patterns:
  - regex: 'x'
""",
            "test",
        )
        assert spec.rule_type == "custom_x"
    finally:
        RULE_TYPE_SCHEMAS.pop("custom_x", None)


def test_validate_yaml_rejects_unknown_rule_type() -> None:
    bad = """
schema_version: 2
scope: language
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
schema_version: 2
scope: language
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
schema_version: 2
scope: language
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
schema_version: 2
scope: language
rule_type: wiring
language: js-ts
extensions: [".js"]
empty_handler_patterns:
  - regex: 'x'
    flags: ['NOT_A_FLAG']
"""
    with pytest.raises(RuleLoadError, match="unknown flag"):
        validate_yaml_text(bad, "test")


def _write_project_rule(project_root: Path, skill_id: str, filename: str, body: str) -> Path:
    rules_dir = project_root / ".cataforge" / "skills" / skill_id / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    path = rules_dir / filename
    path.write_text(body, encoding="utf-8")
    return path


def test_project_override_replaces_package_default(tmp_path: Path) -> None:
    """A project YAML for the same (rule_type, language) replaces the default."""
    body = """
schema_version: 2
scope: language
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
    assert ("wiring", "go") in rules


def _write_override_rule(
    project_root: Path, layer: str, skill_id: str, filename: str, body: str
) -> Path:
    rules_dir = project_root / ".cataforge" / "overrides" / layer / "skills" / skill_id / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    path = rules_dir / filename
    path.write_text(body, encoding="utf-8")
    return path


def test_override_layer_replaces_scaffold_rule(tmp_path: Path) -> None:
    """A project-override YAML beats the scaffold skills/<id>/rules YAML."""
    scaffold_body = """
schema_version: 2
scope: language
rule_type: wiring
language: js-ts
extensions: [".js"]
empty_handler_patterns:
  - regex: 'scaffoldOnly'
"""
    override_body = """
schema_version: 2
scope: language
rule_type: wiring
language: js-ts
extensions: [".js"]
empty_handler_patterns:
  - regex: 'overrideWins'
"""
    _write_project_rule(tmp_path, "code-review", "wiring-js-ts.yaml", scaffold_body)
    _write_override_rule(tmp_path, "project", "code-review", "wiring-js-ts.yaml", override_body)
    rules = discover_rules(
        "code-review",
        builtin_module="cataforge.runtime.skill.builtins.code_review",
        project_root=tmp_path,
    )
    js = rules[("wiring", "js-ts")]
    assert "overrideWins" in js.raw["empty_handler_patterns"][0]["regex"]


def test_user_override_layer_beats_project(tmp_path: Path) -> None:
    """user layer wins over project layer for the same (rule_type, language)."""
    for layer, marker in (("project", "projectMark"), ("user", "userMark")):
        _write_override_rule(
            tmp_path,
            layer,
            "code-review",
            "wiring-js-ts.yaml",
            f"""
schema_version: 2
scope: language
rule_type: wiring
language: js-ts
extensions: [".js"]
empty_handler_patterns:
  - regex: '{marker}'
""",
        )
    rules = discover_rules(
        "code-review",
        builtin_module="cataforge.runtime.skill.builtins.code_review",
        project_root=tmp_path,
    )
    js = rules[("wiring", "js-ts")]
    assert "userMark" in js.raw["empty_handler_patterns"][0]["regex"]


def test_project_can_add_new_language(tmp_path: Path) -> None:
    body = """
schema_version: 2
scope: language
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
    rules = wp.load_wiring_rules()
    assert "js-ts" in rules.by_language
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


def test_e2e_python_real_input_matches_cli_primitives() -> None:
    """subprocess/CliRunner/pexpect-driven CLI e2e counts as real user input."""
    rule = ep.load_e2e_rules().rule_for_extension(".py")
    assert rule is not None
    for sample in (
        "subprocess.run([sys.executable, 'cli.py', '32'], capture_output=True)",
        "result = runner.invoke(cli, ['convert', '32'])",
        "child = pexpect.spawn('converter --help')",
        "out, err = proc.communicate('32\\n')",
    ):
        assert any(p.search(sample) for p in rule.real_input_patterns), sample


def test_wiring_check_loads_project_override_at_runtime(tmp_path: Path) -> None:
    """A project override YAML is honored when the wiring check runs.

    Regression: the wrapper previously froze rules at import time, so a
    project's override never reached the runtime scan. The check now
    resolves rules from the pipeline's project_root (injected by the
    runner via CATAFORGE_PROJECT_ROOT) on every run.
    """
    from cataforge.runtime.skill.builtins.code_review.checks import wiring
    from cataforge.runtime.skill.builtins.code_review.engine.context import CheckContext

    body = """
schema_version: 2
scope: language
rule_type: wiring
language: kotlin
extensions: [".kt"]
empty_handler_patterns:
  - regex: 'setOnClickListener\\s*\\{\\s*\\}'
"""
    _write_project_rule(tmp_path, "code-review", "wiring-kotlin.yaml", body)
    src = tmp_path / "Main.kt"
    src.write_text("button.setOnClickListener {}\n", encoding="utf-8")

    ctx = CheckContext(target=tmp_path, project_root=tmp_path, mode="review")
    findings = wiring.run(ctx)
    assert [f.line for f in findings] == [1]
    assert all(f.severity == "warn" for f in findings)


def test_e2e_collect_loads_project_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """e2e collect() picks up a project override for an added language."""
    from cataforge.runtime.skill.builtins.testing import e2e_scan

    body = """
schema_version: 2
scope: language
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


# ---- schema v2 semantics ---------------------------------------------------


def test_v1_yaml_rejected_with_migration_hint() -> None:
    v1 = """
schema_version: 1
rule_type: wiring
language: js-ts
extensions: [".js"]
empty_handler_patterns: []
"""
    with pytest.raises(RuleLoadError, match="迁移到 2"):
        validate_yaml_text(v1, "test")


def test_scope_required() -> None:
    body = """
schema_version: 2
rule_type: wiring
language: js-ts
extensions: [".js"]
empty_handler_patterns: []
"""
    with pytest.raises(RuleLoadError, match="'scope' required"):
        validate_yaml_text(body, "test")


def test_project_scope_forbids_language_and_extensions() -> None:
    from cataforge.runtime.skill.rules.loader import RULE_TYPE_SCHEMAS, register_rule_type

    register_rule_type(
        "model_x",
        list_pattern_keys=[],
        extra_validator=lambda raw, source: None,
    )
    try:
        bad = """
schema_version: 2
scope: project
rule_type: model_x
language: js-ts
"""
        with pytest.raises(RuleLoadError, match="scope 'project' forbids 'language'"):
            validate_yaml_text(bad, "test")

        good = """
schema_version: 2
scope: project
rule_type: model_x
layers:
  - name: core
"""
        spec = validate_yaml_text(good, "test")
        assert spec.scope == "project"
        assert spec.language == ""
        assert spec.extensions == frozenset()
        assert spec.raw["layers"][0]["name"] == "core"
    finally:
        RULE_TYPE_SCHEMAS.pop("model_x", None)


def test_unknown_key_rejected_without_extra_validator() -> None:
    body = """
schema_version: 2
scope: language
rule_type: wiring
language: js-ts
extensions: [".js"]
empty_handler_pattens:
  - regex: 'typo'
"""
    with pytest.raises(RuleLoadError, match="unknown key"):
        validate_yaml_text(body, "test")


def test_placeholder_pragma_key_no_longer_accepted() -> None:
    body = """
schema_version: 2
scope: language
rule_type: wiring
language: js-ts
extensions: [".js"]
empty_handler_patterns: []
placeholder_pragma:
  regex: 'x'
"""
    with pytest.raises(RuleLoadError, match="unknown key"):
        validate_yaml_text(body, "test")


# ---- arch rule_type structural validation -----------------------------------

_ARCH_PROJECT_HEAD = """
schema_version: 2
scope: project
rule_type: arch
"""


def test_arch_project_scope_roundtrip() -> None:
    body = (
        _ARCH_PROJECT_HEAD
        + """
enforce: warn
layers:
  - name: api
    paths: ["src/app/api/**"]
    modules: ["app.api"]
  - name: domain
    paths: ["src/app/domain/**"]
rules:
  api: [domain]
  domain: []
"""
    )
    spec = validate_yaml_text(body, "test")
    assert spec.scope == "project" and spec.language == ""
    assert spec.raw["enforce"] == "warn"


def test_arch_rules_reference_undeclared_layer() -> None:
    body = (
        _ARCH_PROJECT_HEAD
        + """
layers:
  - name: api
    paths: ["src/app/api/**"]
rules:
  api: [ghost]
"""
    )
    with pytest.raises(RuleLoadError, match="undeclared layer"):
        validate_yaml_text(body, "test")


def test_arch_rules_unknown_layer_key() -> None:
    body = (
        _ARCH_PROJECT_HEAD
        + """
layers:
  - name: api
    paths: ["src/app/api/**"]
rules:
  api: []
  ghost: []
"""
    )
    with pytest.raises(RuleLoadError, match="undeclared layer"):
        validate_yaml_text(body, "test")


def test_arch_rules_must_cover_every_layer() -> None:
    body = (
        _ARCH_PROJECT_HEAD
        + """
layers:
  - name: api
    paths: ["src/app/api/**"]
  - name: domain
    paths: ["src/app/domain/**"]
rules:
  api: [domain]
"""
    )
    with pytest.raises(RuleLoadError, match="missing direction entry"):
        validate_yaml_text(body, "test")


def test_arch_duplicate_layer_name() -> None:
    body = (
        _ARCH_PROJECT_HEAD
        + """
layers:
  - name: api
    paths: ["a/**"]
  - name: api
    paths: ["b/**"]
rules:
  api: []
"""
    )
    with pytest.raises(RuleLoadError, match="duplicate layer name"):
        validate_yaml_text(body, "test")


def test_arch_enforce_invalid_value() -> None:
    body = (
        _ARCH_PROJECT_HEAD
        + """
enforce: shadow
layers:
  - name: api
    paths: ["a/**"]
rules:
  api: []
"""
    )
    with pytest.raises(RuleLoadError, match="'enforce' must be one of"):
        validate_yaml_text(body, "test")


def test_arch_project_scope_rejects_import_patterns() -> None:
    body = (
        _ARCH_PROJECT_HEAD
        + """
layers:
  - name: api
    paths: ["a/**"]
rules:
  api: []
import_patterns:
  - label: x
    regex: '(y)'
"""
    )
    with pytest.raises(RuleLoadError, match="unknown key"):
        validate_yaml_text(body, "test")


def test_arch_language_scope_requires_capture_group() -> None:
    body = """
schema_version: 2
scope: language
rule_type: arch
language: python
extensions: [".py"]
import_patterns:
  - label: "no group"
    regex: 'import \\w+'
"""
    with pytest.raises(RuleLoadError, match="capture group 1"):
        validate_yaml_text(body, "test")


def test_arch_language_scope_rejects_layers() -> None:
    body = """
schema_version: 2
scope: language
rule_type: arch
language: python
extensions: [".py"]
import_patterns:
  - label: ok
    regex: 'import (\\w+)'
layers:
  - name: api
    paths: ["a/**"]
"""
    with pytest.raises(RuleLoadError, match="unknown key"):
        validate_yaml_text(body, "test")


# ---- config_keys / api_surface structural validation --------------------------


def test_config_keys_project_scope_declares_via_filenames() -> None:
    body = """
schema_version: 2
scope: project
rule_type: config_keys
filenames: [".env", ".env.*"]
declare_patterns:
  - label: x
    regex: '^([A-Z]+)='
"""
    spec = validate_yaml_text(body, "test")
    assert spec.scope == "project" and spec.language == ""

    no_selector = """
schema_version: 2
scope: project
rule_type: config_keys
declare_patterns:
  - label: x
    regex: '^([A-Z]+)='
"""
    with pytest.raises(RuleLoadError, match="'filenames' to select files"):
        validate_yaml_text(no_selector, "test")


def test_config_keys_requires_some_pattern_list() -> None:
    body = """
schema_version: 2
scope: language
rule_type: config_keys
language: dotenv
extensions: []
filenames: [".env"]
"""
    with pytest.raises(RuleLoadError, match="at least one of"):
        validate_yaml_text(body, "test")


def test_config_keys_requires_file_selector() -> None:
    body = """
schema_version: 2
scope: language
rule_type: config_keys
language: dotenv
extensions: []
declare_patterns:
  - label: x
    regex: '^([A-Z]+)='
"""
    with pytest.raises(RuleLoadError, match="'extensions' or 'filenames'"):
        validate_yaml_text(body, "test")


def test_config_keys_requires_capture_group() -> None:
    body = """
schema_version: 2
scope: language
rule_type: config_keys
language: dotenv
extensions: []
filenames: [".env"]
declare_patterns:
  - label: x
    regex: '^[A-Z]+='
"""
    with pytest.raises(RuleLoadError, match="capture group 1"):
        validate_yaml_text(body, "test")


def test_api_surface_project_gating_must_be_bool() -> None:
    body = """
schema_version: 2
scope: project
rule_type: api_surface
gating: "yes"
"""
    with pytest.raises(RuleLoadError, match="'gating' must be a boolean"):
        validate_yaml_text(body, "test")


def test_api_surface_language_requires_export_patterns() -> None:
    body = """
schema_version: 2
scope: language
rule_type: api_surface
language: python
extensions: [".py"]
"""
    with pytest.raises(RuleLoadError, match="non-empty 'export_patterns'"):
        validate_yaml_text(body, "test")


def test_api_surface_project_roundtrip() -> None:
    body = """
schema_version: 2
scope: project
rule_type: api_surface
gating: true
"""
    spec = validate_yaml_text(body, "test")
    assert spec.raw["gating"] is True


# ---- complexity rule_type structural validation ------------------------------

_COMPLEXITY_HEAD = """
schema_version: 2
scope: project
rule_type: complexity
"""

_FULL_THRESHOLDS = """
thresholds:
  cyclomatic: { warn: 10, fail: 15 }
  cognitive: { warn: 15, fail: 25 }
  function_lines: { warn: 60, fail: 120 }
  nesting: { warn: 4, fail: 6 }
"""


def test_complexity_project_scope_roundtrip() -> None:
    spec = validate_yaml_text(_COMPLEXITY_HEAD + _FULL_THRESHOLDS, "test")
    assert spec.scope == "project"
    assert spec.raw["thresholds"]["nesting"] == {"warn": 4, "fail": 6}


def test_complexity_missing_metric_rejected() -> None:
    body = (
        _COMPLEXITY_HEAD
        + """
thresholds:
  cyclomatic: { warn: 10, fail: 15 }
"""
    )
    with pytest.raises(RuleLoadError, match="missing metric"):
        validate_yaml_text(body, "test")


def test_complexity_warn_above_fail_rejected() -> None:
    body = _COMPLEXITY_HEAD + _FULL_THRESHOLDS.replace(
        "cyclomatic: { warn: 10, fail: 15 }", "cyclomatic: { warn: 16, fail: 15 }"
    )
    with pytest.raises(RuleLoadError, match="'warn' must be <= 'fail'"):
        validate_yaml_text(body, "test")


def test_complexity_unknown_metric_rejected() -> None:
    body = _COMPLEXITY_HEAD + _FULL_THRESHOLDS + "  halstead: { warn: 1, fail: 2 }\n"
    with pytest.raises(RuleLoadError, match="unknown metric"):
        validate_yaml_text(body, "test")


def test_complexity_language_scope_requires_capture_group() -> None:
    body = """
schema_version: 2
scope: language
rule_type: complexity
language: python
extensions: [".py"]
function_patterns:
  - label: "no group"
    regex: 'def \\w+'
branch_patterns:
  - label: ok
    regex: 'if'
"""
    with pytest.raises(RuleLoadError, match="capture group 1"):
        validate_yaml_text(body, "test")


def test_complexity_language_scope_rejects_thresholds() -> None:
    body = """
schema_version: 2
scope: language
rule_type: complexity
language: python
extensions: [".py"]
function_patterns:
  - label: def
    regex: 'def (\\w+)'
branch_patterns:
  - label: ok
    regex: 'if'
thresholds:
  cyclomatic: { warn: 10, fail: 15 }
"""
    with pytest.raises(RuleLoadError, match="unknown key"):
        validate_yaml_text(body, "test")


def test_comment_only_yaml_is_skipped_as_template(tmp_path: Path) -> None:
    """A fully commented-out YAML (the shipped arch.yaml template) is not loaded."""
    _write_project_rule(tmp_path, "code-review", "arch.yaml", "# scope: project\n# rules: {}\n")
    rules = discover_rules(
        "code-review",
        builtin_module="cataforge.runtime.skill.builtins.code_review",
        project_root=tmp_path,
    )
    assert ("arch", "") not in rules
    # builtin per-language arch import patterns still load
    assert ("arch", "python") in rules


def test_extra_validator_failures_surface_as_load_errors() -> None:
    from cataforge.runtime.skill.rules.loader import RULE_TYPE_SCHEMAS, register_rule_type

    def _validator(raw: dict, source: str) -> None:
        if "layers" not in raw:
            raise RuleLoadError(f"{source}: 'layers' required")

    register_rule_type("model_y", list_pattern_keys=[], extra_validator=_validator)
    try:
        with pytest.raises(RuleLoadError, match="'layers' required"):
            validate_yaml_text(
                """
schema_version: 2
scope: project
rule_type: model_y
""",
                "test",
            )
    finally:
        RULE_TYPE_SCHEMAS.pop("model_y", None)
