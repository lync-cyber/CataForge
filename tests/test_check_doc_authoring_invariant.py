"""Self-test for ``scripts/checks/check_doc_authoring_invariant.py``.

The guard locks doc-producing agent cards to the kg-first authoring flow: a card
that instantiates a doc template must route its Output Contract through
``cataforge context finalize`` rather than instructing a bare ``docs/<doc>.md``
write. Without these tests a heuristic tweak could silently stop catching the
Markdown-first regression.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "checks" / "check_doc_authoring_invariant.py"


def _run_against(tmp_root: Path) -> subprocess.CompletedProcess[str]:
    """Run the guard with SCAN_GLOBS pointed at *tmp_root*."""
    runner = (
        "import sys, pathlib;"
        f"sys.path.insert(0, {str(REPO_ROOT / 'scripts' / 'checks')!r});"
        "import importlib.util as iu;"
        f"spec = iu.spec_from_file_location('guard', {str(SCRIPT)!r});"
        "mod = iu.module_from_spec(spec); spec.loader.exec_module(mod);"
        f"mod.REPO_ROOT = pathlib.Path({str(tmp_root)!r});"
        f"mod.SCAN_GLOBS = [(pathlib.Path({str(tmp_root)!r}), '**/AGENT.md')];"
        "sys.exit(mod.main())"
    )
    return subprocess.run(
        [sys.executable, "-c", runner], capture_output=True, text=True, encoding="utf-8"
    )


def _write_card(tmp_path: Path, name: str, output_contract: str) -> None:
    card = f"""---
name: {name}
---

# Role: {name}

## Output Contract
{output_contract}

## Anti-Patterns
- 禁止: 猜测项目状态
"""
    d = tmp_path / name
    d.mkdir()
    (d / "AGENT.md").write_text(card, encoding="utf-8")


def test_passes_kg_first_card(tmp_path: Path) -> None:
    _write_card(
        tmp_path,
        "architect",
        "- 必须产出: arch 逻辑文档,经 `cataforge context` authoring 落稿并 "
        "`cataforge context finalize` 导出人审视图\n- 使用模板: 通过context调用 arch 模板",
    )
    result = _run_against(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout


def test_flags_markdown_first_card(tmp_path: Path) -> None:
    _write_card(
        tmp_path,
        "architect",
        "- 必须产出: arch-{project}.md (含 API, DATA, 模块章节)\n"
        "- 使用模板: 通过context调用 arch 模板",
    )
    result = _run_against(tmp_path)
    assert result.returncode == 1
    assert "architect" in result.stderr


def test_ignores_non_producing_card(tmp_path: Path) -> None:
    """A card with no doc-template signature (e.g. reviewer) is out of scope."""
    _write_card(
        tmp_path,
        "reviewer",
        "- 文档审查: docs/reviews/doc/REVIEW-{doc_id}-r{N}.md (问题列表 + 严重等级)",
    )
    result = _run_against(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout


def test_allow_marker_silences(tmp_path: Path) -> None:
    _write_card(
        tmp_path,
        "architect",
        "- 必须产出: arch-{project}.md <!-- allow-doc-authoring: legacy markdown-only project -->\n"
        "- 使用模板: 通过context调用 arch 模板",
    )
    result = _run_against(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
