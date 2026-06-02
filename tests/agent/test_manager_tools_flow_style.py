"""AgentManager — tools field supports flow-style YAML list."""

from __future__ import annotations

from pathlib import Path

from cataforge.runtime.agent.manager import AgentManager, _parse_tools_from_frontmatter


class TestParseToolsFromFrontmatter:
    def test_flow_style_list(self) -> None:
        content = "---\nname: agent\ntools: [file_read, file_edit]\n---\nBody\n"
        result = _parse_tools_from_frontmatter(content)
        assert result == ["file_read", "file_edit"]

    def test_comma_separated_string(self) -> None:
        content = "---\nname: agent\ntools: file_read, file_edit\n---\nBody\n"
        result = _parse_tools_from_frontmatter(content)
        assert result == ["file_read", "file_edit"]

    def test_block_style_list(self) -> None:
        content = "---\nname: agent\ntools:\n  - file_read\n  - file_edit\n---\nBody\n"
        result = _parse_tools_from_frontmatter(content)
        assert result == ["file_read", "file_edit"]

    def test_no_tools_key_returns_none(self) -> None:
        content = "---\nname: agent\n---\nBody\n"
        result = _parse_tools_from_frontmatter(content)
        assert result is None

    def test_no_frontmatter_returns_none(self) -> None:
        content = "# No frontmatter\nBody\n"
        result = _parse_tools_from_frontmatter(content)
        assert result is None

    def test_flow_style_with_spaces(self) -> None:
        content = "---\nname: agent\ntools: [ file_read , file_edit ]\n---\nBody\n"
        result = _parse_tools_from_frontmatter(content)
        assert result == ["file_read", "file_edit"]

    def test_list_form_equals_comma_string_form(self) -> None:
        """D1: after migrating off the local regex onto the shared
        ``split_yaml_frontmatter`` utility, the two surface forms (YAML
        flow-style list ``tools: [a, b]`` and comma-string
        ``tools: a, b``) must still produce identical results. The shared
        utility returns the YAML-parsed dict, so the list/string branch
        choice lives entirely in ``_parse_tools_from_frontmatter`` — this
        test pins that the convergence kept both forms equivalent.
        """
        list_form = "---\nname: agent\ntools: [file_read, file_edit, shell_exec]\n---\nBody\n"
        comma_form = "---\nname: agent\ntools: file_read, file_edit, shell_exec\n---\nBody\n"
        assert (
            _parse_tools_from_frontmatter(list_form)
            == _parse_tools_from_frontmatter(comma_form)
            == ["file_read", "file_edit", "shell_exec"]
        )


class TestAgentManagerValidateFlowStyle:
    def test_valid_flow_style_tools_no_issues(self, tmp_path: Path) -> None:
        agents_dir = tmp_path / ".cataforge" / "agents" / "my-agent"
        agents_dir.mkdir(parents=True)
        (agents_dir / "AGENT.md").write_text(
            "---\nname: my-agent\ntools: [file_read, file_edit]\n---\nBody\n",
            encoding="utf-8",
        )
        mgr = AgentManager(project_root=tmp_path)
        issues = mgr.validate("my-agent")
        assert issues == []

    def test_invalid_flow_style_tool_reports_issue(self, tmp_path: Path) -> None:
        agents_dir = tmp_path / ".cataforge" / "agents" / "bad-agent"
        agents_dir.mkdir(parents=True)
        (agents_dir / "AGENT.md").write_text(
            "---\nname: bad-agent\ntools: [file_read, NotARealCapability]\n---\nBody\n",
            encoding="utf-8",
        )
        mgr = AgentManager(project_root=tmp_path)
        issues = mgr.validate("bad-agent")
        assert any("NotARealCapability" in issue for issue in issues)

    def test_block_style_tools_valid(self, tmp_path: Path) -> None:
        agents_dir = tmp_path / ".cataforge" / "agents" / "block-agent"
        agents_dir.mkdir(parents=True)
        (agents_dir / "AGENT.md").write_text(
            "---\nname: block-agent\ntools:\n  - file_read\n  - shell_exec\n---\nBody\n",
            encoding="utf-8",
        )
        mgr = AgentManager(project_root=tmp_path)
        issues = mgr.validate("block-agent")
        assert issues == []
