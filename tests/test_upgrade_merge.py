"""upgrade.py 文档解析与合并逻辑测试"""

import json
import os
import sys


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".claude", "scripts"))
from upgrade import extract_filled_values, extract_section, merge_settings


# ── extract_section ──────────────────────────────────────────────────────


class TestExtractSection:
    def test_normal(self):
        content = "## A\nline1\nline2\n## B\nline3"
        result = extract_section(content, "A")
        assert "## A" in result
        assert "line1" in result
        assert "## B" not in result

    def test_last_section(self):
        content = "## A\nline1\n## B\nline2\nline3"
        result = extract_section(content, "B")
        assert "## B" in result
        assert "line2" in result

    def test_not_found(self):
        content = "## A\nline1"
        assert extract_section(content, "Nonexistent") == ""

    def test_chinese_heading(self):
        content = "## 项目状态\n- 当前阶段: dev\n## 全局约定\nother"
        result = extract_section(content, "项目状态")
        assert "当前阶段: dev" in result
        assert "全局约定" not in result


# ── extract_filled_values ────────────────────────────────────────────────


class TestExtractFilledValues:
    def test_normal(self):
        content = "- 项目名: MyProject\n- 技术栈: Python"
        result = extract_filled_values(content)
        assert result["项目名"] == "MyProject"
        assert result["技术栈"] == "Python"

    def test_skip_placeholder(self):
        content = "- 命名: {规范}\n- Commit: conventional"
        result = extract_filled_values(content)
        assert "命名" not in result
        assert result["Commit"] == "conventional"

    def test_skip_comment(self):
        content = "- 设计工具: <!-- optional -->"
        result = extract_filled_values(content)
        assert "设计工具" not in result

    def test_indented(self):
        content = "  - prd: approved\n  - arch: draft"
        result = extract_filled_values(content)
        assert result["prd"] == "approved"
        assert result["arch"] == "draft"


# ── merge_settings ───────────────────────────────────────────────────────


class TestMergeSettings:
    def _write_settings(self, path, data):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)

    def test_preserve_env(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        os.makedirs(".claude")

        # 当前 settings
        cur = {"env": {"MY_VAR": "keep"}, "permissions": {"allow": ["a"]}}
        self._write_settings(".claude/settings.json", cur)

        # 新版 settings
        src = tmp_path / "new"
        os.makedirs(src / ".claude")
        new = {"env": {"NEW_VAR": "add"}, "permissions": {"allow": ["b"]}}
        self._write_settings(str(src / ".claude" / "settings.json"), new)

        merge_settings(str(src))

        with open(".claude/settings.json", "r") as f:
            merged = json.load(f)

        assert merged["env"]["MY_VAR"] == "keep"
        assert merged["env"]["NEW_VAR"] == "add"

    def test_replace_hooks(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        os.makedirs(".claude")

        cur = {"hooks": {"old": True}}
        self._write_settings(".claude/settings.json", cur)

        src = tmp_path / "new"
        os.makedirs(src / ".claude")
        new = {"hooks": {"new": True}}
        self._write_settings(str(src / ".claude" / "settings.json"), new)

        merge_settings(str(src))

        with open(".claude/settings.json", "r") as f:
            merged = json.load(f)

        assert "old" not in merged.get("hooks", {})
        assert merged["hooks"]["new"] is True

    def test_merge_mcp_servers(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        os.makedirs(".claude")

        cur = {"mcpServers": {"user-mcp": {"url": "x"}}}
        self._write_settings(".claude/settings.json", cur)

        src = tmp_path / "new"
        os.makedirs(src / ".claude")
        new = {"mcpServers": {"framework-mcp": {"url": "y"}}}
        self._write_settings(str(src / ".claude" / "settings.json"), new)

        merge_settings(str(src))

        with open(".claude/settings.json", "r") as f:
            merged = json.load(f)

        assert "user-mcp" in merged["mcpServers"]
        assert "framework-mcp" in merged["mcpServers"]
