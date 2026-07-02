"""Architecture layering guard: model activation, edge judgment, pragmas."""

from __future__ import annotations

from pathlib import Path

from cataforge.runtime.skill.builtins.code_review import CHECKS_MANIFEST
from cataforge.runtime.skill.builtins.code_review.checks import arch_guard
from cataforge.runtime.skill.builtins.code_review.engine.context import CheckContext
from cataforge.runtime.skill.builtins.code_review.engine.pipeline import execute

ARCH_MODEL = """
schema_version: 2
scope: project
rule_type: arch
layers:
  - name: api
    paths: ["src/app/api/**"]
    modules: ["app.api"]
  - name: domain
    paths: ["src/app/domain/**"]
    modules: ["app.domain"]
  - name: infra
    paths: ["src/app/infra/**"]
    modules: ["app.infra"]
rules:
  api: [domain]
  domain: []
  infra: [domain]
"""


def _project(tmp_path: Path, model: str | None = ARCH_MODEL) -> Path:
    rules_dir = tmp_path / ".cataforge" / "skills" / "code-review" / "rules"
    rules_dir.mkdir(parents=True)
    if model is not None:
        (rules_dir / "arch.yaml").write_text(model, encoding="utf-8")
    (tmp_path / "src/app/domain").mkdir(parents=True)
    (tmp_path / "src/app/api").mkdir(parents=True)
    (tmp_path / "src/app/infra").mkdir(parents=True)
    return tmp_path


def _ctx(root: Path, mode: str = "review") -> CheckContext:
    return CheckContext(target=root, project_root=root, mode=mode)


def test_absolute_import_violation_is_fail(tmp_path: Path) -> None:
    root = _project(tmp_path)
    (root / "src/app/domain/svc.py").write_text("import app.infra.db\n", encoding="utf-8")
    findings = arch_guard.run(_ctx(root))
    assert len(findings) == 1
    f = findings[0]
    assert (f.severity, f.category, f.line) == ("fail", "arch", 1)
    assert "domain" in f.detail and "infra" in f.detail


def test_allowed_direction_same_layer_and_third_party_pass(tmp_path: Path) -> None:
    root = _project(tmp_path)
    (root / "src/app/api/routes.py").write_text(
        "import app.domain.svc\n",  # api -> domain declared allowed
        encoding="utf-8",
    )
    (root / "src/app/domain/svc.py").write_text(
        "from app.domain import other\nimport requests\n",  # same layer + third-party
        encoding="utf-8",
    )
    assert arch_guard.run(_ctx(root)) == []


def test_unlayered_source_file_is_not_checked(tmp_path: Path) -> None:
    root = _project(tmp_path)
    (root / "scripts").mkdir()
    (root / "scripts/tool.py").write_text("import app.infra.db\n", encoding="utf-8")
    assert arch_guard.run(_ctx(root)) == []


def test_enforce_warn_downgrades_severity(tmp_path: Path) -> None:
    root = _project(
        tmp_path, ARCH_MODEL.replace("rule_type: arch", "rule_type: arch\nenforce: warn")
    )
    (root / "src/app/domain/svc.py").write_text("import app.infra.db\n", encoding="utf-8")
    findings = arch_guard.run(_ctx(root))
    assert [f.severity for f in findings] == ["warn"]


def test_relative_specifiers_resolve_to_layer(tmp_path: Path) -> None:
    root = _project(tmp_path)
    (root / "src/app/domain/x.ts").write_text(
        "import { db } from '../infra/db';\n", encoding="utf-8"
    )
    (root / "src/app/domain/y.py").write_text("from ..infra import db\n", encoding="utf-8")
    findings = arch_guard.run(_ctx(root))
    assert len(findings) == 2
    assert all(f.severity == "fail" and "infra" in f.detail for f in findings)


def test_line_pragma_with_reason_exempts_only_that_line(tmp_path: Path) -> None:
    root = _project(tmp_path)
    (root / "src/app/domain/svc.py").write_text(
        'import app.infra.db  # cataforge: allow(arch_guard, reason="迁移卡 B-31")\n'
        "import app.infra.conn\n",
        encoding="utf-8",
    )
    findings = arch_guard.run(_ctx(root))
    assert [(f.severity, f.line) for f in findings] == [("fail", 2)]


def test_line_pragma_without_reason_warns(tmp_path: Path) -> None:
    root = _project(tmp_path)
    (root / "src/app/domain/svc.py").write_text(
        "import app.infra.db  # cataforge: allow(arch_guard)\n", encoding="utf-8"
    )
    findings = arch_guard.run(_ctx(root))
    assert [(f.severity, f.line) for f in findings] == [("warn", 1)]
    assert "缺 reason" in findings[0].detail


def test_no_model_review_silent_scan_info(tmp_path: Path) -> None:
    root = _project(tmp_path, model=None)
    (root / "src/app/domain/svc.py").write_text("import app.infra.db\n", encoding="utf-8")
    assert arch_guard.run(_ctx(root)) == []
    scan = arch_guard.run(_ctx(root, mode="scan"))
    assert [f.severity for f in scan] == ["info"]
    assert "未声明" in scan[0].detail


def test_comment_only_project_arch_yaml_equals_no_model(tmp_path: Path) -> None:
    root = _project(tmp_path, model="# schema_version: 2\n# scope: project\n")
    (root / "src/app/domain/svc.py").write_text("import app.infra.db\n", encoding="utf-8")
    assert arch_guard.run(_ctx(root)) == []


def test_focus_arch_runs_only_arch_guard(tmp_path: Path) -> None:
    root = _project(tmp_path)
    (root / "src/app/domain/svc.py").write_text("import app.infra.db\n", encoding="utf-8")
    result = execute("review", root, focus=["arch"], project_root=root, tool_cache={})
    assert result.checks_run == ["code_review.arch_guard"]
    assert result.exit_code == 1


def test_manifest_entry() -> None:
    entry = next(e for e in CHECKS_MANIFEST if e["id"] == "code_review.arch_guard")
    assert entry["severity"] == "fail-on-error"
    assert entry["modes"] == "review+scan"


def test_builtin_ships_six_language_import_patterns() -> None:
    model, langs = arch_guard.load_arch_rules(None)
    assert model is None  # builtin arch.yaml is a comment-only template
    assert set(langs) == {"python", "js-ts", "go", "java", "csharp", "rust"}
    assert all(li.patterns for li in langs.values())


def test_module_prefix_matching_is_separator_aligned(tmp_path: Path) -> None:
    """'app.infrastructure' must NOT match the 'app.infra' modules prefix."""
    root = _project(tmp_path)
    (root / "src/app/domain/svc.py").write_text("import app.infrastructure\n", encoding="utf-8")
    assert arch_guard.run(_ctx(root)) == []
