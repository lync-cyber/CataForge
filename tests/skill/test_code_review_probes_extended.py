"""xref kernel + config-dead-key / api-surface / pragma-inventory probes."""

from __future__ import annotations

import re
from pathlib import Path

from cataforge.runtime.skill.builtins.code_review.checks import (
    api_surface,
    config_keys,
    pragma_inventory,
)
from cataforge.runtime.skill.builtins.code_review.engine.baseline import (
    baseline_path,
    load_baseline,
)
from cataforge.runtime.skill.builtins.code_review.engine.context import CheckContext
from cataforge.runtime.skill.builtins.code_review.engine.xref import (
    Occurrence,
    collect_keys,
    collect_occurrences,
    dead_keys,
)
from cataforge.utils.run_subprocess import run as run_proc


def _ctx(root: Path, mode: str = "scan") -> CheckContext:
    return CheckContext(target=root, project_root=root, mode=mode)


# ---- xref kernel -------------------------------------------------------------


def test_collect_keys_with_normalizer() -> None:
    pattern = re.compile(r"class=\"([^\"]+)\"")
    text = 'a class="btn primary" b class="btn"'
    assert collect_keys(text, (pattern,), normalize=str.split) == {"btn", "primary"}


def test_collect_occurrences_lines_and_dedup() -> None:
    pattern = re.compile(r"(--[\w-]+)\s*:")
    text = "--a: 1;\n--b: 2; --b: 3;\n"
    occs = collect_occurrences("f.css", text, (pattern,))
    assert [(o.key, o.line) for o in occs] == [("--a", 1), ("--b", 2)]


def test_dead_keys_set_difference() -> None:
    declared = [Occurrence("A", "f", 1), Occurrence("B", "f", 2)]
    assert [o.key for o in dead_keys(declared, {"B"})] == ["A"]


# ---- config_dead_key ----------------------------------------------------------


def test_config_dead_key_reported_consumed_key_not(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("USED=1\nDEAD=2\n", encoding="utf-8")
    (tmp_path / "app.py").write_text('import os\nos.environ["USED"]\n', encoding="utf-8")
    findings = config_keys.run(_ctx(tmp_path))
    assert [(f.severity, f.line) for f in findings] == [("info", 2)]
    assert "DEAD" in findings[0].detail


def test_config_dotenv_variants_matched_by_filename_glob(tmp_path: Path) -> None:
    (tmp_path / ".env.production").write_text("ORPHAN=1\n", encoding="utf-8")
    findings = config_keys.run(_ctx(tmp_path))
    assert len(findings) == 1 and "ORPHAN" in findings[0].detail


def test_config_pragma_exempts_declaration_file(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text(
        '# cataforge: allow(config_dead_key, reason="compose 消费")\nINFRA_ONLY=1\n',
        encoding="utf-8",
    )
    assert config_keys.run(_ctx(tmp_path)) == []

    (tmp_path / ".env").write_text(
        "# cataforge: allow(config_dead_key)\nINFRA_ONLY=1\n", encoding="utf-8"
    )
    findings = config_keys.run(_ctx(tmp_path))
    assert [f.severity for f in findings] == ["warn"]
    assert "缺 reason" in findings[0].detail


# ---- api_surface ---------------------------------------------------------------


def test_api_surface_establish_then_diff_then_refresh(tmp_path: Path) -> None:
    (tmp_path / "lib.py").write_text("def keep():\n    return 1\n", encoding="utf-8")
    first = api_surface.run(_ctx(tmp_path))
    assert [f.severity for f in first] == ["info"]
    assert "快照已建立" in first[0].detail
    assert "lib.py::keep" in load_baseline(tmp_path, api_surface.SNAPSHOT_NAME)

    (tmp_path / "lib.py").write_text("def renamed():\n    return 1\n", encoding="utf-8")
    second = api_surface.run(_ctx(tmp_path))
    details = sorted(f.detail for f in second)
    assert any("API 导出移除：lib.py::keep" in d for d in details)
    assert any("API 新增导出：lib.py::renamed" in d for d in details)
    assert set(load_baseline(tmp_path, api_surface.SNAPSHOT_NAME)) == {"lib.py::renamed"}


def test_api_surface_review_noop_without_gating(tmp_path: Path) -> None:
    (tmp_path / "lib.py").write_text("def keep():\n    return 1\n", encoding="utf-8")
    api_surface.run(_ctx(tmp_path))  # establish
    (tmp_path / "lib.py").write_text("x = 1\n", encoding="utf-8")
    assert api_surface.run(_ctx(tmp_path, mode="review")) == []


def _enable_gating(root: Path) -> None:
    rules = root / ".cataforge" / "skills" / "code-review" / "rules"
    rules.mkdir(parents=True, exist_ok=True)
    (rules / "api-surface.yaml").write_text(
        "schema_version: 2\nscope: project\nrule_type: api_surface\ngating: true\n",
        encoding="utf-8",
    )


def test_api_surface_gating_review_fails_on_removed_export(tmp_path: Path) -> None:
    _enable_gating(tmp_path)
    (tmp_path / "lib.py").write_text("def keep():\n    return 1\n", encoding="utf-8")
    api_surface.run(_ctx(tmp_path))  # establish snapshot
    (tmp_path / "lib.py").write_text("x = 1\n", encoding="utf-8")
    findings = api_surface.run(_ctx(tmp_path, mode="review"))
    assert [f.severity for f in findings] == ["fail"]
    assert "lib.py::keep" in findings[0].detail
    # review never refreshes the snapshot
    assert "lib.py::keep" in load_baseline(tmp_path, api_surface.SNAPSHOT_NAME)


def test_api_surface_gating_review_without_snapshot_is_silent(tmp_path: Path) -> None:
    _enable_gating(tmp_path)
    (tmp_path / "lib.py").write_text("def keep():\n    return 1\n", encoding="utf-8")
    assert not baseline_path(tmp_path, api_surface.SNAPSHOT_NAME).is_file()
    assert api_surface.run(_ctx(tmp_path, mode="review")) == []


# ---- pragma_inventory -----------------------------------------------------------


def test_pragma_inventory_lists_allowances_and_flags_legacy(tmp_path: Path) -> None:
    (tmp_path / "cur.ts").write_text(
        '// cataforge: allow(ui_fidelity, reason="theme")\n', encoding="utf-8"
    )
    (tmp_path / "bare.ts").write_text(
        "// cataforge: allow(wiring_empty_handler)\n", encoding="utf-8"
    )
    (tmp_path / "old.ts").write_text("// cataforge: wiring-placeholder\n", encoding="utf-8")
    (tmp_path / "doc.md").write_text("// cataforge: legacy-example\n", encoding="utf-8")
    findings = pragma_inventory.run(_ctx(tmp_path))
    by_file = {Path(f.file).name: f.detail for f in findings}
    assert 'reason="theme"' in by_file["cur.ts"]
    assert "缺 reason" in by_file["bare.ts"]
    assert "unknown-pragma" in by_file["old.ts"]
    assert "doc.md" not in by_file  # prose files skipped
    assert all(f.severity == "info" for f in findings)


def test_pragma_inventory_blame_aging_in_git_repo(tmp_path: Path) -> None:
    for args in (("init", "-q"), ("config", "user.email", "t@t"), ("config", "user.name", "t")):
        assert run_proc(["git", *args], cwd=tmp_path).returncode == 0
    (tmp_path / "a.py").write_text(
        'import x  # cataforge: allow(arch_guard, reason="grandfathered")\n', encoding="utf-8"
    )
    assert run_proc(["git", "add", "-A"], cwd=tmp_path).returncode == 0
    assert run_proc(["git", "commit", "-qm", "init"], cwd=tmp_path).returncode == 0
    findings = pragma_inventory.run(_ctx(tmp_path))
    assert len(findings) == 1
    assert "引入 0 天前" in findings[0].detail
