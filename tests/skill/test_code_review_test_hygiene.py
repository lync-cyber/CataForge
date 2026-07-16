"""test_hygiene probe: unlabeled slow-test / per-test expensive-setup candidates."""

from __future__ import annotations

from pathlib import Path

from cataforge.runtime.skill.builtins.code_review.checks import test_hygiene
from cataforge.runtime.skill.builtins.code_review.engine.context import CheckContext
from cataforge.runtime.skill.builtins.code_review.engine.pipeline import execute


def _ctx(root: Path) -> CheckContext:
    return CheckContext(target=root, project_root=None, mode="scan")


def _write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_unlabeled_slow_test_flagged(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "tests/test_cli.py",
        "import subprocess\n\ndef test_cli():\n    subprocess.run(['tool'])\n",
    )
    findings = test_hygiene.run(_ctx(tmp_path))
    assert len(findings) == 1
    f = findings[0]
    assert f.check_id == test_hygiene.CHECK_ID
    assert f.severity == "info"
    assert f.category == "test-quality"
    assert "无标签慢测候选" in f.detail
    assert "子进程" in f.detail


def test_marked_slow_test_not_flagged(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "tests/test_cli.py",
        "import pytest, subprocess\n\n@pytest.mark.slow\ndef test_cli():\n"
        "    subprocess.run(['tool'])\n",
    )
    assert test_hygiene.run(_ctx(tmp_path)) == []


def test_expensive_per_test_setup_flagged(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "tests/test_db.py",
        "import pytest, subprocess\n\n"
        "@pytest.mark.slow\n"
        "class TestDb:\n"
        "    def setup_method(self):\n"
        "        subprocess.run(['build', 'artifact'])\n"
        "    def test_query(self):\n"
        "        assert True\n",
    )
    findings = test_hygiene.run(_ctx(tmp_path))
    assert [f.detail for f in findings if "昂贵 setup" in f.detail]


def test_module_scope_fixture_not_flagged_as_setup(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "tests/test_shared.py",
        "import pytest, subprocess\n\n"
        "@pytest.mark.slow\n"
        '@pytest.fixture(scope="module")\n'
        "def built():\n"
        "    subprocess.run(['build'])\n",
    )
    assert test_hygiene.run(_ctx(tmp_path)) == []


def test_non_test_file_ignored(tmp_path: Path) -> None:
    _write(tmp_path, "src/runner.py", "import subprocess\nsubprocess.run(['tool'])\n")
    assert test_hygiene.run(_ctx(tmp_path)) == []


def test_pragma_allowance_with_reason_skips(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "tests/test_cli.py",
        '# cataforge: allow(test_hygiene, reason="真实 CLI 安装验证")\n'
        "import subprocess\n\ndef test_cli():\n    subprocess.run(['tool'])\n",
    )
    assert test_hygiene.run(_ctx(tmp_path)) == []


def test_pragma_allowance_without_reason_warns(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "tests/test_cli.py",
        "# cataforge: allow(test_hygiene)\n"
        "import subprocess\n\ndef test_cli():\n    subprocess.run(['tool'])\n",
    )
    findings = test_hygiene.run(_ctx(tmp_path))
    assert [f for f in findings if f.severity == "warn" and "缺 reason" in f.detail]


def test_ancestor_tests_dir_outside_target_not_matched(tmp_path: Path) -> None:
    root = tmp_path / "tests" / "myproject"
    _write(root, "src/runner.py", "import subprocess\nsubprocess.run(['tool'])\n")
    assert test_hygiene.run(_ctx(root)) == []


def test_clean_setup_adjacent_slow_test_not_flagged_as_setup(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "tests/test_adjacent.py",
        "import subprocess\n\n"
        "class TestAdjacent:\n"
        "    def setup_method(self):\n"
        "        self.x = 1\n"
        "    def test_run(self):\n"
        "        subprocess.run(['tool'])\n",
    )
    findings = test_hygiene.run(_ctx(tmp_path))
    assert not [f for f in findings if "昂贵 setup" in f.detail]


def test_single_line_setup_body_flagged(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "tests/test_inline.py",
        "import pytest, subprocess\n\n"
        "@pytest.mark.slow\n"
        "class TestInline:\n"
        "    def setup_method(self): subprocess.run(['build'])\n"
        "    def test_query(self):\n"
        "        assert True\n",
    )
    findings = test_hygiene.run(_ctx(tmp_path))
    assert [f for f in findings if "昂贵 setup" in f.detail]


def test_fixture_scope_after_other_kwargs_not_flagged_as_setup(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "tests/test_env.py",
        "import pytest, subprocess\n\n"
        "@pytest.mark.slow\n"
        '@pytest.fixture(autouse=True, scope="session")\n'
        "def env():\n"
        "    subprocess.run(['build'])\n",
    )
    assert test_hygiene.run(_ctx(tmp_path)) == []


def test_mock_and_comment_references_not_flagged_slow(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "tests/test_fake.py",
        "# parses dockerfile-style syntax\n"
        "def test_fake_api(api):\n"
        "    api.requests.get('/x')\n"
        "    assert api.ok\n",
    )
    assert test_hygiene.run(_ctx(tmp_path)) == []


def test_asyncio_sleep_flagged_slow(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "tests/test_async.py",
        "import asyncio\n\nasync def test_wait():\n    await asyncio.sleep(0.5)\n",
    )
    findings = test_hygiene.run(_ctx(tmp_path))
    assert [f for f in findings if "显式休眠" in f.detail]


def test_scan_focus_selects_probe(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "tests/test_cli.py",
        "import subprocess\n\ndef test_cli():\n    subprocess.run(['tool'])\n",
    )
    focused = execute("scan", tmp_path, focus=["test-quality"], tool_cache={})
    assert test_hygiene.CHECK_ID in focused.checks_run
    assert any(f.check_id == test_hygiene.CHECK_ID for f in focused.findings)
    excluded = execute("scan", tmp_path, focus=["dead-code"], tool_cache={})
    assert test_hygiene.CHECK_ID not in excluded.checks_run
