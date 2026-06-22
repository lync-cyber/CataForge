"""Subprocess-contract regression net for the structured-report builtins.

SkillRunner invokes these builtins as ``python -m`` subprocesses and routes
the returncode into the EVENT-LOG (0=completed, 1=needs_revision). These
tests pin that contract at the subprocess boundary — independent of the
in-process render/collect unit tests — and confirm the new ``--format json``
path emits valid JSON whose findings agree with the text-mode gate decision.
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

_PRD = textwrap.dedent(
    """\
    ---
    id: prd-t
    author: pm
    status: approved
    deps: []
    consumers: [arch]
    ---
    [NAV]§2[/NAV]
    ## 2. 功能需求
    ### F-001: Login
    - 优先级: P0
    AC-001: works
    """
)


def _run(module: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        [sys.executable, "-m", module, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def test_doc_consistency_skip_exits_zero(tmp_path: Path) -> None:
    (tmp_path / "prd").mkdir()
    (tmp_path / "prd" / "prd.md").write_text(_PRD, encoding="utf-8")
    res = _run("cataforge.runtime.skill.builtins.doc_consistency.checker", str(tmp_path))
    assert res.returncode == 0  # < 2 doc types → skip
    assert res.stdout.startswith("跳过:")


def test_doc_review_failures_exit_one_text_and_json_agree(tmp_path: Path) -> None:
    docs = tmp_path / "prd"
    docs.mkdir()
    doc = docs / "prd.md"
    doc.write_text(_PRD, encoding="utf-8")
    module = "cataforge.runtime.skill.builtins.doc_review.doc_check"

    text = _run(module, "prd", str(doc), "--docs-dir", str(tmp_path))
    js = _run(module, "prd", str(doc), "--docs-dir", str(tmp_path), "--format", "json")

    # Both invocations gate identically; doc-review exits 1 on blocking findings.
    assert text.returncode == js.returncode
    assert text.returncode in (0, 1)
    payload = json.loads(js.stdout)
    has_blocking = any(i["severity"] in ("CRITICAL", "HIGH") for i in payload["issues"])
    assert (text.returncode == 1) == has_blocking


_DOC_CHECK = "cataforge.runtime.skill.builtins.doc_review.doc_check"


def test_doc_check_missing_doctype_exits_two_with_help() -> None:
    """Passing only a file (forgot doc-type) yields an actionable error that
    lists the valid doc-types and uses the public `cataforge skill run` form."""
    res = _run(_DOC_CHECK, "docs/arch/x.md")
    assert res.returncode == 2
    out = res.stdout + res.stderr
    assert "python -m" not in out  # never tell users to call the module path
    assert "arch" in out and "prd" in out
    assert "cataforge skill run doc-review" in out


def test_doc_check_doctype_looking_like_path_detected(tmp_path: Path) -> None:
    doc = tmp_path / "arch.md"
    doc.write_text("# x\n", encoding="utf-8")
    res = _run(_DOC_CHECK, "docs/arch/x.md", str(doc))
    assert res.returncode == 2
    assert "doc-type" in (res.stdout + res.stderr)


def test_doc_check_missing_file_exits_two_no_traceback(tmp_path: Path) -> None:
    res = _run(_DOC_CHECK, "arch", str(tmp_path / "nope.md"))
    assert res.returncode == 2
    out = res.stdout + res.stderr
    assert "Traceback" not in out
    assert "nope.md" in out


def test_e2e_scan_warnings_only_exits_zero(tmp_path: Path) -> None:
    e2e = tmp_path / "e2e"
    e2e.mkdir()
    (e2e / "login.spec.ts").write_text(
        'test("x", async () => { window.__S__ = 1; await page.fill("#u","a"); });\n',
        encoding="utf-8",
    )
    module = "cataforge.runtime.skill.builtins.testing.e2e_scan"

    text = _run(module, str(e2e))
    js = _run(module, str(e2e), "--format", "json")

    assert text.returncode == 0  # advisory-only never gates
    assert js.returncode == 0
    assert text.stdout.rstrip().endswith("RESULT: PASS (warnings only)")
    payload = json.loads(js.stdout)
    assert payload["summary"]["file_count"] == 1


def test_e2e_scan_missing_target_exits_two(tmp_path: Path) -> None:
    res = _run("cataforge.runtime.skill.builtins.testing.e2e_scan", str(tmp_path / "nope"))
    assert res.returncode == 2
    assert "目标路径不存在" in res.stdout


@pytest.mark.parametrize(
    "module",
    [
        "cataforge.runtime.skill.builtins.doc_consistency.checker",
        "cataforge.runtime.skill.builtins.testing.e2e_scan",
    ],
)
def test_json_output_is_valid(tmp_path: Path, module: str) -> None:
    target = tmp_path / "tree"
    target.mkdir()
    res = _run(module, str(target), "--format", "json")
    payload = json.loads(res.stdout)
    assert set(payload) >= {"exit_code", "issues", "summary"}
