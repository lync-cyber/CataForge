"""upgrade.py 文档解析与合并逻辑测试"""

import json
import os
import sys


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".claude", "scripts"))
from _upgrade_local import extract_filled_values, extract_section, merge_settings


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

    def test_merge_hooks_preserves_user_custom(self, tmp_path, monkeypatch):
        """用户自定义钩子（不在新版框架中的）应被保留；新版框架钩子应被添加；完全相同的钩子不重复"""
        monkeypatch.chdir(tmp_path)
        os.makedirs(".claude")

        user_hook = {
            "matcher": "Bash",
            "hooks": [{"type": "command", "command": "echo user"}],
        }
        shared_hook = {
            "matcher": ".*",
            "hooks": [{"type": "command", "command": "echo shared"}],
        }
        framework_hook_new = {
            "matcher": "Edit",
            "hooks": [{"type": "command", "command": "echo new-framework"}],
        }

        # 当前：有一个用户自定义钩子 + 一个与新版框架完全相同的钩子
        cur = {"hooks": {"PreToolUse": [user_hook, shared_hook]}}
        self._write_settings(".claude/settings.json", cur)

        src = tmp_path / "new"
        os.makedirs(src / ".claude")
        # 新版：有 shared_hook（与旧版完全一致）+ 一个全新的框架钩子
        new = {"hooks": {"PreToolUse": [shared_hook, framework_hook_new]}}
        self._write_settings(str(src / ".claude" / "settings.json"), new)

        merge_settings(str(src))

        with open(".claude/settings.json", "r") as f:
            merged = json.load(f)

        hooks = merged["hooks"]["PreToolUse"]
        commands = [h["hooks"][0]["command"] for h in hooks]
        # 新版框架钩子（全新）应被添加
        assert "echo new-framework" in commands
        # 用户自定义钩子应被保留
        assert "echo user" in commands
        # 两版本共有的钩子不应重复（dedup）
        assert commands.count("echo shared") == 1

    def test_merge_hooks_preserves_user_only_events(self, tmp_path, monkeypatch):
        """用户新增的 hook 事件类型（不在新版框架中）应被保留"""
        monkeypatch.chdir(tmp_path)
        os.makedirs(".claude")

        cur = {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Bash",
                        "hooks": [{"type": "command", "command": "echo pre"}],
                    }
                ],
                "Stop": [
                    {
                        "matcher": "",
                        "hooks": [{"type": "command", "command": "echo stop"}],
                    }
                ],
            }
        }
        self._write_settings(".claude/settings.json", cur)

        src = tmp_path / "new"
        os.makedirs(src / ".claude")
        new = {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Bash",
                        "hooks": [{"type": "command", "command": "echo pre"}],
                    }
                ]
            }
        }
        self._write_settings(str(src / ".claude" / "settings.json"), new)

        merge_settings(str(src))

        with open(".claude/settings.json", "r") as f:
            merged = json.load(f)

        # 用户独有的 Stop 事件类型应保留
        assert "Stop" in merged["hooks"]
        assert merged["hooks"]["Stop"][0]["hooks"][0]["command"] == "echo stop"

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

    def test_mcp_servers_user_config_wins(self, tmp_path, monkeypatch):
        """同名 MCP server：用户配置应优先于新版框架配置"""
        monkeypatch.chdir(tmp_path)
        os.makedirs(".claude")

        cur = {
            "mcpServers": {
                "shared-mcp": {"url": "user-url", "env": {"TOKEN": "secret"}}
            }
        }
        self._write_settings(".claude/settings.json", cur)

        src = tmp_path / "new"
        os.makedirs(src / ".claude")
        new = {"mcpServers": {"shared-mcp": {"url": "framework-url"}}}
        self._write_settings(str(src / ".claude" / "settings.json"), new)

        merge_settings(str(src))

        with open(".claude/settings.json", "r") as f:
            merged = json.load(f)

        # 用户的 url 和 env 应保留，不被框架版本覆盖
        assert merged["mcpServers"]["shared-mcp"]["url"] == "user-url"
        assert merged["mcpServers"]["shared-mcp"]["env"]["TOKEN"] == "secret"
