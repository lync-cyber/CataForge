"""AGENT.md / SKILL.md 结构校验测试

参考 skill-creator 的 quick_validate.py 设计，对 CataForge 框架文件做结构校验。
使用 pytest.mark.parametrize 动态扫描所有 agents/skills 目录，
每个文件为独立测试用例，确保框架交付物结构合规。
"""

import os
import re

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENTS_DIR = os.path.join(PROJECT_ROOT, ".claude", "agents")
SKILLS_DIR = os.path.join(PROJECT_ROOT, ".claude", "skills")

# CataForge AGENT.md 允许的 frontmatter 字段
AGENT_ALLOWED_FIELDS = {
    "name",
    "description",
    "tools",
    "disallowedTools",
    "allowed_paths",
    "skills",
    "model",
    "maxTurns",
}

# CataForge SKILL.md 允许的 frontmatter 字段
SKILL_ALLOWED_FIELDS = {
    "name",
    "description",
    "argument-hint",
    "suggested-tools",
    "depends",
    "disable-model-invocation",
    "user-invocable",
}

# 已知合法工具名
KNOWN_TOOLS = {
    "Read",
    "Write",
    "Edit",
    "Glob",
    "Grep",
    "Bash",
    "Agent",
    "AskUserQuestion",
    "WebSearch",
    "WebFetch",
    "TodoWrite",
    "EnterPlanMode",
    "ExitPlanMode",
    "NotebookEdit",
}

KEBAB_CASE_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


# ============================================================================
# 辅助函数
# ============================================================================


def parse_frontmatter(filepath: str) -> dict | None:
    """解析 YAML frontmatter，返回字典。解析失败返回 None。"""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    if not content.startswith("---"):
        return None

    match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return None

    # 简易 YAML 解析（避免依赖 pyyaml）
    fm = {}
    current_key = None
    current_list = None

    for line in match.group(1).split("\n"):
        # 列表项: "  - value"
        list_match = re.match(r"^\s+-\s+(.+)$", line)
        if list_match and current_key:
            if current_list is None:
                current_list = []
                fm[current_key] = current_list
            val = list_match.group(1).strip()
            # 去除 YAML 行内注释
            if " #" in val:
                val = val[: val.index(" #")].strip()
            current_list.append(val)
            continue

        # 键值对: "key: value"
        kv_match = re.match(r"^([a-zA-Z_-]+)\s*:\s*(.*?)$", line)
        if kv_match:
            current_key = kv_match.group(1).strip()
            value = kv_match.group(2).strip()
            current_list = None

            # 去除引号
            if value and value[0] in ('"', "'") and value[-1] == value[0]:
                value = value[1:-1]

            # 空值（后续可能是列表）
            if value == "" or value == "[]":
                fm[current_key] = [] if value == "[]" else value
            elif value.startswith("[") and value.endswith("]"):
                # 内联数组: [item1, item2, item3]
                inner = value[1:-1].strip()
                if inner:
                    fm[current_key] = [v.strip() for v in inner.split(",") if v.strip()]
                else:
                    fm[current_key] = []
            elif value.lower() in ("true", "false"):
                fm[current_key] = value.lower() == "true"
            elif value.isdigit():
                fm[current_key] = int(value)
            else:
                fm[current_key] = value

    return fm


def collect_agents() -> list[str]:
    """收集所有 agent 目录名"""
    if not os.path.exists(AGENTS_DIR):
        return []
    return [
        d
        for d in sorted(os.listdir(AGENTS_DIR))
        if os.path.isdir(os.path.join(AGENTS_DIR, d))
        and os.path.exists(os.path.join(AGENTS_DIR, d, "AGENT.md"))
    ]


def collect_skills() -> list[str]:
    """收集所有 skill 目录名"""
    if not os.path.exists(SKILLS_DIR):
        return []
    return [
        d
        for d in sorted(os.listdir(SKILLS_DIR))
        if os.path.isdir(os.path.join(SKILLS_DIR, d))
        and os.path.exists(os.path.join(SKILLS_DIR, d, "SKILL.md"))
    ]


# ============================================================================
# AGENT.md 校验
# ============================================================================


class TestAgentIntegrity:
    @pytest.mark.parametrize("agent_name", collect_agents())
    def test_frontmatter_parseable(self, agent_name):
        """AGENT.md frontmatter 存在且可解析"""
        path = os.path.join(AGENTS_DIR, agent_name, "AGENT.md")
        fm = parse_frontmatter(path)
        assert fm is not None, f"{agent_name}/AGENT.md: frontmatter 解析失败"

    @pytest.mark.parametrize("agent_name", collect_agents())
    def test_required_fields(self, agent_name):
        """AGENT.md 包含必填字段"""
        path = os.path.join(AGENTS_DIR, agent_name, "AGENT.md")
        fm = parse_frontmatter(path)
        if fm is None:
            pytest.skip("frontmatter 解析失败")

        for field in ("name", "description", "tools", "model", "maxTurns"):
            assert field in fm, f"{agent_name}: 缺少必填字段 '{field}'"

    @pytest.mark.parametrize("agent_name", collect_agents())
    def test_name_matches_directory(self, agent_name):
        """name 字段与目录名一致"""
        path = os.path.join(AGENTS_DIR, agent_name, "AGENT.md")
        fm = parse_frontmatter(path)
        if fm is None:
            pytest.skip("frontmatter 解析失败")
        assert fm.get("name") == agent_name, (
            f"name='{fm.get('name')}' 与目录名 '{agent_name}' 不一致"
        )

    @pytest.mark.parametrize("agent_name", collect_agents())
    def test_name_kebab_case(self, agent_name):
        """name 为 kebab-case"""
        path = os.path.join(AGENTS_DIR, agent_name, "AGENT.md")
        fm = parse_frontmatter(path)
        if fm is None:
            pytest.skip("frontmatter 解析失败")
        name = fm.get("name", "")
        assert KEBAB_CASE_RE.match(name), f"name='{name}' 不是 kebab-case"

    @pytest.mark.parametrize("agent_name", collect_agents())
    def test_skills_exist(self, agent_name):
        """skills 列表中的每个 skill 目录存在"""
        path = os.path.join(AGENTS_DIR, agent_name, "AGENT.md")
        fm = parse_frontmatter(path)
        if fm is None:
            pytest.skip("frontmatter 解析失败")

        skills = fm.get("skills", [])
        if not isinstance(skills, list):
            pytest.skip("skills 不是列表")

        for skill_name in skills:
            if not isinstance(skill_name, str):
                continue
            skill_dir = os.path.join(SKILLS_DIR, skill_name)
            assert os.path.isdir(skill_dir), (
                f"{agent_name} 引用了不存在的 skill: '{skill_name}'"
            )

    @pytest.mark.parametrize("agent_name", collect_agents())
    def test_model_valid(self, agent_name):
        """model 值为 inherit 或合法 model-id 格式"""
        path = os.path.join(AGENTS_DIR, agent_name, "AGENT.md")
        fm = parse_frontmatter(path)
        if fm is None:
            pytest.skip("frontmatter 解析失败")

        model = fm.get("model", "")
        valid_models = {"inherit", "sonnet", "opus", "haiku"}
        # 允许 inherit 或已知短名，也允许 claude-xxx 格式
        assert model in valid_models or model.startswith("claude-"), (
            f"model='{model}' 不合法"
        )

    @pytest.mark.parametrize("agent_name", collect_agents())
    def test_max_turns_positive(self, agent_name):
        """maxTurns 为正整数"""
        path = os.path.join(AGENTS_DIR, agent_name, "AGENT.md")
        fm = parse_frontmatter(path)
        if fm is None:
            pytest.skip("frontmatter 解析失败")

        max_turns = fm.get("maxTurns")
        assert isinstance(max_turns, int) and max_turns > 0, (
            f"maxTurns={max_turns} 应为正整数"
        )

    @pytest.mark.parametrize("agent_name", collect_agents())
    def test_no_unknown_fields(self, agent_name):
        """不包含未知的 frontmatter 字段"""
        path = os.path.join(AGENTS_DIR, agent_name, "AGENT.md")
        fm = parse_frontmatter(path)
        if fm is None:
            pytest.skip("frontmatter 解析失败")

        unknown = set(fm.keys()) - AGENT_ALLOWED_FIELDS
        assert len(unknown) == 0, (
            f"{agent_name}: 未知字段 {unknown}，允许: {AGENT_ALLOWED_FIELDS}"
        )


# ============================================================================
# SKILL.md 校验
# ============================================================================


class TestSkillIntegrity:
    @pytest.mark.parametrize("skill_name", collect_skills())
    def test_frontmatter_parseable(self, skill_name):
        """SKILL.md frontmatter 存在且可解析"""
        path = os.path.join(SKILLS_DIR, skill_name, "SKILL.md")
        fm = parse_frontmatter(path)
        assert fm is not None, f"{skill_name}/SKILL.md: frontmatter 解析失败"

    @pytest.mark.parametrize("skill_name", collect_skills())
    def test_required_fields(self, skill_name):
        """SKILL.md 包含必填字段"""
        path = os.path.join(SKILLS_DIR, skill_name, "SKILL.md")
        fm = parse_frontmatter(path)
        if fm is None:
            pytest.skip("frontmatter 解析失败")

        for field in ("name", "description"):
            assert field in fm, f"{skill_name}: 缺少必填字段 '{field}'"

    @pytest.mark.parametrize("skill_name", collect_skills())
    def test_name_matches_directory(self, skill_name):
        """name 字段与目录名一致"""
        path = os.path.join(SKILLS_DIR, skill_name, "SKILL.md")
        fm = parse_frontmatter(path)
        if fm is None:
            pytest.skip("frontmatter 解析失败")
        assert fm.get("name") == skill_name, (
            f"name='{fm.get('name')}' 与目录名 '{skill_name}' 不一致"
        )

    @pytest.mark.parametrize("skill_name", collect_skills())
    def test_name_kebab_case(self, skill_name):
        """name 为 kebab-case"""
        path = os.path.join(SKILLS_DIR, skill_name, "SKILL.md")
        fm = parse_frontmatter(path)
        if fm is None:
            pytest.skip("frontmatter 解析失败")
        name = fm.get("name", "")
        assert KEBAB_CASE_RE.match(name), f"name='{name}' 不是 kebab-case"

    @pytest.mark.parametrize("skill_name", collect_skills())
    def test_depends_exist(self, skill_name):
        """depends 列表中的每个 skill 目录存在"""
        path = os.path.join(SKILLS_DIR, skill_name, "SKILL.md")
        fm = parse_frontmatter(path)
        if fm is None:
            pytest.skip("frontmatter 解析失败")

        depends = fm.get("depends", [])
        if not isinstance(depends, list):
            pytest.skip("depends 不是列表")

        for dep_name in depends:
            if not isinstance(dep_name, str):
                continue
            dep_dir = os.path.join(SKILLS_DIR, dep_name)
            assert os.path.isdir(dep_dir), (
                f"{skill_name} 依赖了不存在的 skill: '{dep_name}'"
            )

    @pytest.mark.parametrize("skill_name", collect_skills())
    def test_scripts_exist(self, skill_name):
        """SKILL.md 中引用的 scripts/*.py 文件实际存在"""
        path = os.path.join(SKILLS_DIR, skill_name, "SKILL.md")
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        # 查找 python .claude/skills/xxx/scripts/yyy.py 引用
        refs = re.findall(
            r"python\s+\.claude/skills/([^/]+)/scripts/(\S+\.py)", content
        )
        for ref_skill, ref_script in refs:
            script_path = os.path.join(
                PROJECT_ROOT, ".claude", "skills", ref_skill, "scripts", ref_script
            )
            assert os.path.exists(script_path), (
                f"{skill_name} 引用了不存在的脚本: "
                f".claude/skills/{ref_skill}/scripts/{ref_script}"
            )

    @pytest.mark.parametrize("skill_name", collect_skills())
    def test_templates_exist(self, skill_name):
        """SKILL.md 中引用的 templates/*.md 文件实际存在"""
        path = os.path.join(SKILLS_DIR, skill_name, "SKILL.md")
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        # 查找 templates/xxx.md 引用，排除占位符如 {template_id}.md
        refs = re.findall(r"\.claude/skills/([^/]+)/templates/(\S+\.md)", content)
        for ref_skill, ref_template in refs:
            if "{" in ref_template or "}" in ref_template:
                continue
            tpl_path = os.path.join(
                PROJECT_ROOT, ".claude", "skills", ref_skill, "templates", ref_template
            )
            assert os.path.exists(tpl_path), (
                f"{skill_name} 引用了不存在的模板: "
                f".claude/skills/{ref_skill}/templates/{ref_template}"
            )

    @pytest.mark.parametrize("skill_name", collect_skills())
    def test_no_unknown_fields(self, skill_name):
        """不包含未知的 frontmatter 字段"""
        path = os.path.join(SKILLS_DIR, skill_name, "SKILL.md")
        fm = parse_frontmatter(path)
        if fm is None:
            pytest.skip("frontmatter 解析失败")

        unknown = set(fm.keys()) - SKILL_ALLOWED_FIELDS
        assert len(unknown) == 0, (
            f"{skill_name}: 未知字段 {unknown}，允许: {SKILL_ALLOWED_FIELDS}"
        )

    @pytest.mark.parametrize("skill_name", collect_skills())
    def test_line_count_warning(self, skill_name):
        """SKILL.md 不超过 500 行"""
        path = os.path.join(SKILLS_DIR, skill_name, "SKILL.md")
        with open(path, "r", encoding="utf-8") as f:
            line_count = sum(1 for _ in f)
        # 使用 warning 而非 hard fail（框架约定为建议值）
        if line_count > 500:
            import warnings

            warnings.warn(
                f"{skill_name}/SKILL.md 有 {line_count} 行，超过建议的 500 行上限"
            )


# ============================================================================
# 交叉引用一致性
# ============================================================================


class TestCrossReferenceConsistency:
    def test_all_agent_skills_are_valid_skills(self):
        """所有 AGENT.md 中引用的 skills 在 skills/ 目录下有对应 SKILL.md"""
        agents = collect_agents()
        all_issues = []
        for agent_name in agents:
            path = os.path.join(AGENTS_DIR, agent_name, "AGENT.md")
            fm = parse_frontmatter(path)
            if fm is None:
                continue
            skills = fm.get("skills", [])
            if not isinstance(skills, list):
                continue
            for skill_name in skills:
                if not isinstance(skill_name, str):
                    continue
                skill_md = os.path.join(SKILLS_DIR, skill_name, "SKILL.md")
                if not os.path.exists(skill_md):
                    all_issues.append(f"{agent_name} → {skill_name}")

        assert len(all_issues) == 0, "断裂的 Agent→Skill 引用:\n" + "\n".join(
            f"  - {i}" for i in all_issues
        )

    def test_all_skill_depends_are_valid_skills(self):
        """所有 SKILL.md 中的 depends 在 skills/ 目录下有对应 SKILL.md"""
        skills = collect_skills()
        all_issues = []
        for skill_name in skills:
            path = os.path.join(SKILLS_DIR, skill_name, "SKILL.md")
            fm = parse_frontmatter(path)
            if fm is None:
                continue
            depends = fm.get("depends", [])
            if not isinstance(depends, list):
                continue
            for dep_name in depends:
                if not isinstance(dep_name, str):
                    continue
                dep_md = os.path.join(SKILLS_DIR, dep_name, "SKILL.md")
                if not os.path.exists(dep_md):
                    all_issues.append(f"{skill_name} → {dep_name}")

        assert len(all_issues) == 0, "断裂的 Skill→Skill 依赖:\n" + "\n".join(
            f"  - {i}" for i in all_issues
        )
