"""Complexity gate: proxy metrics, diff-incremental gating, ratchet baseline."""

from __future__ import annotations

from pathlib import Path

from cataforge.runtime.skill.builtins.code_review.checks import complexity
from cataforge.runtime.skill.builtins.code_review.engine.baseline import (
    load_baseline,
    save_baseline,
)
from cataforge.runtime.skill.builtins.code_review.engine.context import CheckContext
from cataforge.utils.run_subprocess import run as run_proc

_NO_TOOLS = {"radon (cc)": False, "gocyclo": False, "lizard": False}


def _hot_py(branches: int = 17) -> str:
    """A function with cyclomatic = branches + 1."""
    body = "".join(f"    if x > {i}:\n        x -= {i}\n" for i in range(branches))
    return "def hot(x):\n" + body + "    return x\n"


def _ctx(root: Path, mode: str = "review") -> CheckContext:
    return CheckContext(target=root, project_root=root, mode=mode, tool_cache=dict(_NO_TOOLS))


def _git(root: Path, *args: str) -> None:
    result = run_proc(["git", *args], cwd=root)
    assert result.returncode == 0, result.stderr


def _git_repo(root: Path) -> None:
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@t")
    _git(root, "config", "user.name", "t")


def test_proxy_metrics(tmp_path: Path) -> None:
    (tmp_path / "hot.py").write_text(_hot_py(17), encoding="utf-8")
    _, langs = complexity.load_complexity_rules(tmp_path)
    fns = complexity._measure_all(_ctx(tmp_path), langs)
    assert [f.name for f in fns] == ["hot"]
    assert fns[0].metrics["cyclomatic"] == 18
    assert fns[0].metrics["function_lines"] == 36
    assert fns[0].metrics["nesting"] == 1
    assert fns[0].source == "proxy"


def test_review_without_git_gates_everything(tmp_path: Path) -> None:
    (tmp_path / "hot.py").write_text(_hot_py(17), encoding="utf-8")
    findings = complexity.run(_ctx(tmp_path))
    fails = [f for f in findings if f.severity == "fail"]
    assert len(fails) == 1
    assert "cyclomatic=18" in fails[0].detail
    assert "度量来源 proxy" in fails[0].detail


def test_review_untouched_function_passes(tmp_path: Path) -> None:
    _git_repo(tmp_path)
    (tmp_path / "hot.py").write_text(_hot_py(17), encoding="utf-8")
    (tmp_path / "other.py").write_text("def simple(x):\n    return x\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "init")
    (tmp_path / "other.py").write_text("def simple(x):\n    return x + 1\n", encoding="utf-8")
    assert complexity.run(_ctx(tmp_path)) == []


def test_review_touched_function_fails(tmp_path: Path) -> None:
    _git_repo(tmp_path)
    (tmp_path / "hot.py").write_text(_hot_py(17), encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "init")
    touched = (
        (tmp_path / "hot.py").read_text().replace("    return x\n", "    x += 1\n    return x\n")
    )
    (tmp_path / "hot.py").write_text(touched, encoding="utf-8")
    findings = complexity.run(_ctx(tmp_path))
    assert any(f.severity == "fail" and "cyclomatic=18" in f.detail for f in findings)


def test_untracked_file_counts_as_touched(tmp_path: Path) -> None:
    _git_repo(tmp_path)
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "init")
    (tmp_path / "hot.py").write_text(_hot_py(17), encoding="utf-8")  # untracked
    findings = complexity.run(_ctx(tmp_path))
    assert any(f.severity == "fail" for f in findings)


def test_baseline_ratchet_raises_the_limit(tmp_path: Path) -> None:
    (tmp_path / "hot.py").write_text(_hot_py(17), encoding="utf-8")
    save_baseline(
        tmp_path,
        complexity.BASELINE_NAME,
        {
            "hot.py::hot": {
                "cyclomatic": 18,
                "cognitive": 17,
                "function_lines": 36,
                "nesting": 1,
            }
        },
    )
    findings = complexity.run(_ctx(tmp_path))
    assert [f.severity for f in findings if "cyclomatic" in f.detail] == ["warn"]

    # worsening past the recorded baseline gates again
    (tmp_path / "hot.py").write_text(_hot_py(18), encoding="utf-8")
    findings = complexity.run(_ctx(tmp_path))
    fails = [f for f in findings if f.severity == "fail"]
    assert fails and "cyclomatic=19 超过门禁 18" in fails[0].detail


def test_scan_refreshes_baseline_and_reports_info_only(tmp_path: Path) -> None:
    (tmp_path / "hot.py").write_text(_hot_py(17), encoding="utf-8")
    findings = complexity.run(_ctx(tmp_path, mode="scan"))
    assert all(f.severity == "info" for f in findings)
    assert any("基线已刷新" in f.detail for f in findings)
    recorded = load_baseline(tmp_path, complexity.BASELINE_NAME)
    assert recorded["hot.py::hot"]["cyclomatic"] == 18


def test_pragma_on_definition_line(tmp_path: Path) -> None:
    exempt = _hot_py(17).replace(
        "def hot(x):",
        'def hot(x):  # cataforge: allow(complexity_gate, reason="遗留热点，重构卡 B-7")',
    )
    (tmp_path / "hot.py").write_text(exempt, encoding="utf-8")
    assert complexity.run(_ctx(tmp_path)) == []

    no_reason = _hot_py(17).replace(
        "def hot(x):", "def hot(x):  # cataforge: allow(complexity_gate)"
    )
    (tmp_path / "hot.py").write_text(no_reason, encoding="utf-8")
    findings = complexity.run(_ctx(tmp_path))
    assert [f.severity for f in findings] == ["warn"]
    assert "缺 reason" in findings[0].detail


def test_project_override_tightens_thresholds(tmp_path: Path) -> None:
    rules_dir = tmp_path / ".cataforge" / "skills" / "code-review" / "rules"
    rules_dir.mkdir(parents=True)
    (rules_dir / "complexity.yaml").write_text(
        """
schema_version: 2
scope: project
rule_type: complexity
thresholds:
  cyclomatic: { warn: 1, fail: 2 }
  cognitive: { warn: 15, fail: 25 }
  function_lines: { warn: 60, fail: 120 }
  nesting: { warn: 4, fail: 6 }
""",
        encoding="utf-8",
    )
    (tmp_path / "mild.py").write_text(
        "def mild(x):\n    if x:\n        return 1\n"
        "    if not x:\n        return 2\n    return 0\n",
        encoding="utf-8",
    )
    findings = complexity.run(_ctx(tmp_path))
    assert any(f.severity == "fail" and "cyclomatic=3 超过门禁 2" in f.detail for f in findings)


def test_same_name_functions_get_distinct_fingerprints(tmp_path: Path) -> None:
    (tmp_path / "dup.py").write_text(
        "class A:\n    def go(self):\n        return 1\n\n"
        "class B:\n    def go(self):\n        return 2\n",
        encoding="utf-8",
    )
    _, langs = complexity.load_complexity_rules(tmp_path)
    fns = complexity._measure_all(_ctx(tmp_path), langs)
    assert [f.fingerprint for f in fns] == ["dup.py::go", "dup.py::go#2"]


def test_parse_radon_json(tmp_path: Path) -> None:
    payload = '{"src/a.py": [{"type": "function", "name": "f", "lineno": 3, "complexity": 12}]}'
    parsed = complexity.parse_radon_json(payload)
    assert list(parsed.values()) == [12]
    assert next(iter(parsed))[1] == 3


def test_parse_gocyclo() -> None:
    parsed = complexity.parse_gocyclo("15 mypkg HandleRequest src/server.go:42:1\n")
    assert list(parsed.values()) == [15]
    assert next(iter(parsed))[1] == 42


def test_parse_lizard_csv() -> None:
    row = '10,17,80,2,20,"hot@3-22@src/a.py","src/a.py","hot","hot( x )",3,22\n'
    parsed = complexity.parse_lizard_csv(row)
    assert list(parsed.values()) == [17]
    assert next(iter(parsed))[1] == 3


def test_radon_rank_mapping() -> None:
    assert complexity.radon_rank(5) == "B"
    assert complexity.radon_rank(10) == "C"
    assert complexity.radon_rank(20) == "D"
    assert complexity.radon_rank(40) == "F"
    assert complexity.radon_rank(2) == "A"


def test_thresholds_for_builtin_defaults() -> None:
    thresholds = complexity.thresholds_for(None)
    assert thresholds is not None
    assert thresholds["cyclomatic"] == {"warn": 10, "fail": 15}
    assert set(thresholds) == set(complexity.METRICS)
