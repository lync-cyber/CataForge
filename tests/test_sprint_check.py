"""sprint_check.py 解析逻辑测试 — 覆盖6处修复的缺陷"""

import os
import sys


sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(__file__),
        "..",
        ".claude",
        "skills",
        "sprint-review",
        "scripts",
    ),
)
from sprint_check import check_unplanned_files, extract_sprint_tasks


# ── 任务ID字母后缀 (Bug #1, #6) ──────────────────────────────────────────


class TestTaskIdSuffix:
    """T-007a 等带字母后缀的任务ID应被正确解析"""

    def test_task_card_with_suffix(self, tmp_path):
        md = tmp_path / "dev-plan.md"
        md.write_text(
            "### Sprint 1\n"
            "### T-007a: 子任务\n"
            "- **status**: done\n"
            "### T-008: 下一任务\n"
            "- **status**: done\n"
        )
        tasks = extract_sprint_tasks([str(md)], 1)
        ids = [t["id"] for t in tasks]
        assert "T-007a" in ids
        assert "T-008" in ids
        assert len(ids) == 2  # 不会截断为重复的 T-007

    def test_table_row_with_suffix(self, tmp_path):
        md = tmp_path / "dev-plan.md"
        md.write_text(
            "### Sprint 1\n"
            "| 任务ID | 任务名 | 模块 | 依赖 | TDD测试点 | 状态 |\n"
            "|--------|--------|------|------|-----------|------|\n"
            "| T-007a | 子任务 | M-001 | — | AC-010 | done |\n"
            "| T-008 | 下一任务 | M-001 | — | AC-011 | todo |\n"
        )
        tasks = extract_sprint_tasks([str(md)], 1)
        ids = [t["id"] for t in tasks]
        assert "T-007a" in ids
        assert "T-008" in ids


# ── deliverables正则 (Bug #2) ─────────────────────────────────────────────


class TestDeliverablesRegex:
    """支持 **deliverables** (交付物): 格式"""

    def test_deliverables_with_parenthesized_label(self, tmp_path):
        md = tmp_path / "dev-plan.md"
        md.write_text(
            "### Sprint 1\n"
            "### T-001: 任务\n"
            "- **status**: done\n"
            "- **deliverables** (交付物):\n"
            "  - `src/foo/bar.py`\n"
            "  - `tests/test_bar.py`\n"
        )
        tasks = extract_sprint_tasks([str(md)], 1)
        assert len(tasks) == 1
        assert "src/foo/bar.py" in tasks[0]["deliverables"]
        assert "tests/test_bar.py" in tasks[0]["deliverables"]

    def test_deliverables_without_parenthesized_label(self, tmp_path):
        md = tmp_path / "dev-plan.md"
        md.write_text(
            "### Sprint 1\n### T-001: 任务\n- **deliverables**:\n  - `src/foo.py`\n"
        )
        tasks = extract_sprint_tasks([str(md)], 1)
        assert "src/foo.py" in tasks[0]["deliverables"]


# ── 状态回填 (Bug #3) ─────────────────────────────────────────────────────


class TestStatusBackfill:
    """Sprint volume文件无status时从主文件表格回填"""

    def test_backfill_from_main_table(self, tmp_path):
        # 主文件包含表格状态
        main = tmp_path / "dev-plan-main.md"
        main.write_text(
            "### Sprint 1\n"
            "| 任务ID | 任务名 | 模块 | 依赖 | TDD测试点 | 状态 |\n"
            "|--------|--------|------|------|-----------|------|\n"
            "| T-001 | 任务1 | M-001 | — | AC-001 | done |\n"
        )
        # sprint volume文件只有任务卡无状态
        vol = tmp_path / "dev-plan-s1.md"
        vol.write_text("### T-001: 任务1\n- **deliverables**:\n  - `src/mod.py`\n")
        tasks = extract_sprint_tasks([str(main), str(vol)], 1)
        t001 = [t for t in tasks if t["id"] == "T-001"]
        assert len(t001) == 1
        assert t001[0]["status"] == "done"


# ── 交付物路径清理 (Bug #4) ───────────────────────────────────────────────


class TestDeliverablePathCleaning:
    """checkbox前缀、描述后缀、非路径文本应被过滤"""

    def test_checkbox_and_description_stripped(self, tmp_path):
        md = tmp_path / "dev-plan.md"
        md.write_text(
            "### Sprint 1\n"
            "### T-001: 任务\n"
            "- **deliverables**:\n"
            "  - [x] `src/foo.py` — 功能模块\n"
            "  - [ ] `tests/test_foo.py` -- 单元测试\n"
        )
        tasks = extract_sprint_tasks([str(md)], 1)
        assert "src/foo.py" in tasks[0]["deliverables"]
        assert "tests/test_foo.py" in tasks[0]["deliverables"]

    def test_chinese_text_filtered(self, tmp_path):
        md = tmp_path / "dev-plan.md"
        md.write_text(
            "### Sprint 1\n"
            "### T-001: 任务\n"
            "- **deliverables**:\n"
            "  - `src/valid.py`\n"
            "  - 全部子包 __init__.py 文件\n"
        )
        tasks = extract_sprint_tasks([str(md)], 1)
        assert "src/valid.py" in tasks[0]["deliverables"]
        assert len(tasks[0]["deliverables"]) == 1  # 中文文本被过滤

    def test_template_variable_filtered(self, tmp_path):
        md = tmp_path / "dev-plan.md"
        md.write_text(
            "### Sprint 1\n"
            "### T-001: 任务\n"
            "- **deliverables**:\n"
            "  - `src/real.py`\n"
            "  - `{initial_migration}`\n"
        )
        tasks = extract_sprint_tasks([str(md)], 1)
        assert "src/real.py" in tasks[0]["deliverables"]
        assert len(tasks[0]["deliverables"]) == 1  # 模板变量被过滤


# ── __pycache__ 过滤 (Bug #5) ─────────────────────────────────────────────


class TestPycacheFiltering:
    """__pycache__目录及.pyc文件不应被报告为计划外文件"""

    def test_pycache_dir_excluded(self, tmp_path):
        src = tmp_path / "src"
        cache_dir = src / "__pycache__"
        cache_dir.mkdir(parents=True)
        (cache_dir / "mod.cpython-311.pyc").write_bytes(b"")
        tasks = [{"id": "T-001", "deliverables": []}]
        issues = check_unplanned_files(tasks, str(src))
        assert not any("__pycache__" in i for i in issues)
        assert not any(".pyc" in i for i in issues)

    def test_pyc_in_src_excluded(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "something.pyc").write_bytes(b"")
        tasks = [{"id": "T-001", "deliverables": []}]
        issues = check_unplanned_files(tasks, str(src))
        assert not any(".pyc" in i for i in issues)
