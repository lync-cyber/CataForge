#!/usr/bin/env python3
"""
Validate a generated workflow framework for structural completeness,
platform compatibility, and architectural quality.

Usage:
    python validate_framework.py <framework_dir> [--platform <platform_id>]

Exit codes:
    0 = all checks passed
    1 = validation errors found
    2 = invalid arguments
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path


def split_yaml_frontmatter(text: str) -> tuple[dict | None, str]:
    """Extract YAML frontmatter from a Markdown file."""
    if not text.startswith("---"):
        return None, text
    end = text.find("\n---", 3)
    if end < 0:
        return None, text
    import yaml
    try:
        fm = yaml.safe_load(text[3:end])
    except yaml.YAMLError:
        fm = None
    body = text[end + 4:].lstrip("\n")
    return fm, body


CAPABILITY_IDS = {
    "file_read", "file_write", "file_edit", "file_glob", "file_grep",
    "shell_exec", "web_search", "web_fetch", "user_question", "agent_dispatch",
}

PLATFORM_NATIVE_NAMES = {
    "Read", "Write", "Edit", "Glob", "Grep", "Bash", "Shell",
    "WebSearch", "WebFetch", "AskUserQuestion", "Agent", "Task",
    "apply_patch", "shell", "spawn_agent", "read", "write", "edit",
    "glob", "grep", "bash", "websearch", "webfetch", "question", "task",
    "web_search", "NotebookEdit",
}

VALID_STATUSES = {"completed", "needs_input", "needs_revision", "blocked"}

KEBAB_CASE_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")

PLACEHOLDER_PATTERNS = re.compile(
    r"\bTODO\b|\bFIXME\b|\bXXX\b|\bHACK\b|\bstub\b|"
    r"\{\{[^}]+\}\}",
    re.IGNORECASE,
)


class ValidationResult:
    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, msg: str):
        self.errors.append(msg)

    def warn(self, msg: str):
        self.warnings.append(msg)

    @property
    def passed(self) -> bool:
        return len(self.errors) == 0


def validate_agent(agent_dir: Path, result: ValidationResult) -> dict | None:
    """Validate a single agent definition. Returns frontmatter if valid."""
    agent_id = agent_dir.name
    agent_md = agent_dir / "AGENT.md"

    if not agent_md.exists():
        result.error(f"Agent '{agent_id}': AGENT.md not found")
        return None

    if not KEBAB_CASE_RE.match(agent_id):
        result.error(f"Agent '{agent_id}': directory name must be kebab-case")

    text = agent_md.read_text(encoding="utf-8")
    fm, body = split_yaml_frontmatter(text)

    if fm is None:
        result.error(f"Agent '{agent_id}': missing or invalid YAML frontmatter")
        return None

    if "name" not in fm:
        result.error(f"Agent '{agent_id}': frontmatter missing 'name' field")
    elif fm["name"] != agent_id:
        result.warn(f"Agent '{agent_id}': name '{fm['name']}' differs from directory name")

    if "description" not in fm:
        result.error(f"Agent '{agent_id}': frontmatter missing 'description' field")

    # Check tools use capability IDs
    if "tools" in fm:
        tools_str = fm["tools"] if isinstance(fm["tools"], str) else ""
        if isinstance(fm["tools"], list):
            tools = fm["tools"]
        else:
            tools = [t.strip() for t in tools_str.split(",") if t.strip()]
        for tool in tools:
            if tool in PLATFORM_NATIVE_NAMES and tool not in CAPABILITY_IDS:
                result.error(
                    f"Agent '{agent_id}': tool '{tool}' is a platform-native name, "
                    f"use capability ID instead"
                )

    # Check for placeholders in body
    placeholders = PLACEHOLDER_PATTERNS.findall(body)
    if placeholders:
        unique = sorted(set(placeholders))
        result.error(
            f"Agent '{agent_id}': contains placeholder(s): {', '.join(unique)}"
        )

    # Check required sections
    required_sections = ["Role", "Anti-Patterns"]
    for section in required_sections:
        if f"# " not in body and f"## {section}" not in body:
            pass  # Only warn for truly missing main sections
        pattern = re.compile(rf"#{{1,3}}\s+.*{re.escape(section)}", re.IGNORECASE)
        if not pattern.search(body):
            result.warn(f"Agent '{agent_id}': missing recommended section '{section}'")

    return fm


def validate_skill(skill_dir: Path, result: ValidationResult) -> dict | None:
    """Validate a single skill definition. Returns frontmatter if valid."""
    skill_id = skill_dir.name
    skill_md = skill_dir / "SKILL.md"

    if not skill_md.exists():
        result.error(f"Skill '{skill_id}': SKILL.md not found")
        return None

    if not KEBAB_CASE_RE.match(skill_id):
        result.error(f"Skill '{skill_id}': directory name must be kebab-case")

    text = skill_md.read_text(encoding="utf-8")
    fm, body = split_yaml_frontmatter(text)

    if fm is None:
        result.error(f"Skill '{skill_id}': missing or invalid YAML frontmatter")
        return None

    if "name" not in fm:
        result.error(f"Skill '{skill_id}': frontmatter missing 'name' field")
    elif fm["name"] != skill_id:
        result.warn(f"Skill '{skill_id}': name '{fm['name']}' differs from directory name")

    if "description" not in fm:
        result.error(f"Skill '{skill_id}': frontmatter missing 'description' field")

    # Check for placeholders
    placeholders = PLACEHOLDER_PATTERNS.findall(body)
    if placeholders:
        unique = sorted(set(placeholders))
        result.error(
            f"Skill '{skill_id}': contains placeholder(s): {', '.join(unique)}"
        )

    return fm


def validate_workflow(workflow_file: Path, result: ValidationResult) -> dict | None:
    """Validate a workflow definition YAML. Returns parsed data if valid."""
    import yaml

    if not workflow_file.exists():
        result.error(f"Workflow file not found: {workflow_file}")
        return None

    try:
        data = yaml.safe_load(workflow_file.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        result.error(f"Workflow '{workflow_file.name}': invalid YAML: {e}")
        return None

    if not isinstance(data, dict):
        result.error(f"Workflow '{workflow_file.name}': root must be a mapping")
        return None

    for field in ("id", "name", "phases"):
        if field not in data:
            result.error(f"Workflow '{workflow_file.name}': missing required field '{field}'")

    if "phases" in data and isinstance(data["phases"], list):
        phase_ids = set()
        for phase in data["phases"]:
            if not isinstance(phase, dict):
                result.error(f"Workflow '{workflow_file.name}': phase must be a mapping")
                continue
            pid = phase.get("id")
            if pid:
                if pid in phase_ids:
                    result.error(f"Workflow '{workflow_file.name}': duplicate phase id '{pid}'")
                phase_ids.add(pid)

    return data


def validate_framework_json(framework_json: Path, result: ValidationResult) -> dict | None:
    """Validate framework.json."""
    if not framework_json.exists():
        result.error("framework.json not found")
        return None

    try:
        data = json.loads(framework_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        result.error(f"framework.json: invalid JSON: {e}")
        return None

    if "version" not in data:
        result.error("framework.json: missing 'version' field")
    if "runtime" not in data:
        result.error("framework.json: missing 'runtime' field")
    elif "platform" not in data.get("runtime", {}):
        result.error("framework.json: missing 'runtime.platform' field")

    return data


def validate_profile(profile_file: Path, result: ValidationResult) -> dict | None:
    """Validate a platform profile.yaml."""
    import yaml

    if not profile_file.exists():
        result.error(f"Platform profile not found: {profile_file}")
        return None

    try:
        data = yaml.safe_load(profile_file.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        result.error(f"Profile '{profile_file}': invalid YAML: {e}")
        return None

    if "platform_id" not in data:
        result.error(f"Profile '{profile_file}': missing 'platform_id'")
    if "tool_map" not in data:
        result.error(f"Profile '{profile_file}': missing 'tool_map'")

    return data


def check_cross_references(
    framework_dir: Path,
    agents: dict[str, dict],
    skills: dict[str, dict],
    workflows: dict[str, dict],
    result: ValidationResult,
):
    """Check that all cross-references between agents, skills, and workflows are valid."""
    agent_ids = set(agents.keys())
    skill_ids = set(skills.keys())

    # Check agent → skill references
    for agent_id, fm in agents.items():
        if fm and "skills" in fm:
            agent_skills = fm["skills"]
            if isinstance(agent_skills, list):
                for sid in agent_skills:
                    if sid not in skill_ids:
                        result.error(
                            f"Agent '{agent_id}' references skill '{sid}' which does not exist"
                        )

    # Check workflow → agent references
    for wf_name, wf_data in workflows.items():
        if not wf_data or "phases" not in wf_data:
            continue
        phases = wf_data["phases"]
        if not isinstance(phases, list):
            continue
        for phase in phases:
            if not isinstance(phase, dict):
                continue
            agent = phase.get("agent")
            if agent and agent not in agent_ids:
                result.error(
                    f"Workflow '{wf_name}' phase '{phase.get('id', '?')}' references "
                    f"agent '{agent}' which does not exist"
                )
            phase_skills = phase.get("skills", [])
            if isinstance(phase_skills, list):
                for sid in phase_skills:
                    if sid not in skill_ids:
                        result.error(
                            f"Workflow '{wf_name}' phase '{phase.get('id', '?')}' references "
                            f"skill '{sid}' which does not exist"
                        )

    # Check for orphan skills (warning only)
    referenced_skills: set[str] = set()
    for fm in agents.values():
        if fm and "skills" in fm and isinstance(fm["skills"], list):
            referenced_skills.update(fm["skills"])
    for wf_data in workflows.values():
        if not wf_data or "phases" not in wf_data:
            continue
        for phase in wf_data.get("phases", []):
            if isinstance(phase, dict):
                for sid in phase.get("skills", []):
                    referenced_skills.add(sid)
    for sid in skill_ids:
        if sid not in referenced_skills:
            result.warn(f"Skill '{sid}' is not referenced by any agent or workflow")


def check_dag(agents: dict[str, dict], result: ValidationResult):
    """Check that agent dependency graph is a DAG (no cycles)."""
    # Build adjacency from agent instructions (upstream/downstream)
    # This is a best-effort check based on frontmatter
    pass  # Agent dependencies are defined at workflow level, not in frontmatter


def validate_framework(framework_dir: str, platform_id: str | None = None) -> ValidationResult:
    """Run all validation checks on a generated framework."""
    root = Path(framework_dir)
    cataforge = root / ".cataforge"
    result = ValidationResult()

    if not cataforge.exists():
        result.error(f".cataforge/ directory not found in {framework_dir}")
        return result

    # 1. Validate framework.json
    fw_data = validate_framework_json(cataforge / "framework.json", result)

    # 2. Validate agents
    agents_dir = cataforge / "agents"
    agents: dict[str, dict] = {}
    if agents_dir.exists():
        for agent_dir in sorted(agents_dir.iterdir()):
            if agent_dir.is_dir():
                fm = validate_agent(agent_dir, result)
                agents[agent_dir.name] = fm
    else:
        result.error("agents/ directory not found")

    # 3. Validate skills
    skills_dir = cataforge / "skills"
    skills: dict[str, dict] = {}
    if skills_dir.exists():
        for skill_dir in sorted(skills_dir.iterdir()):
            if skill_dir.is_dir():
                fm = validate_skill(skill_dir, result)
                skills[skill_dir.name] = fm
    else:
        result.warn("skills/ directory not found (may be intentional for simple workflows)")

    # 4. Validate workflows
    workflows_dir = cataforge / "workflows"
    workflows: dict[str, dict] = {}
    if workflows_dir.exists():
        for wf_file in sorted(workflows_dir.glob("*.yaml")):
            wf_data = validate_workflow(wf_file, result)
            workflows[wf_file.stem] = wf_data
        for wf_file in sorted(workflows_dir.glob("*.yml")):
            wf_data = validate_workflow(wf_file, result)
            workflows[wf_file.stem] = wf_data

    # 5. Validate platform profile
    if platform_id:
        profile_path = cataforge / "platforms" / platform_id / "profile.yaml"
        validate_profile(profile_path, result)
    elif fw_data and "runtime" in fw_data:
        pid = fw_data["runtime"].get("platform")
        if pid:
            profile_path = cataforge / "platforms" / pid / "profile.yaml"
            if profile_path.exists():
                validate_profile(profile_path, result)

    # 6. Validate hooks.yaml
    hooks_file = cataforge / "hooks" / "hooks.yaml"
    if hooks_file.exists():
        import yaml
        try:
            yaml.safe_load(hooks_file.read_text(encoding="utf-8"))
        except yaml.YAMLError as e:
            result.error(f"hooks.yaml: invalid YAML: {e}")

    # 7. Validate rules
    rules_dir = cataforge / "rules"
    if rules_dir.exists():
        for md_file in rules_dir.glob("*.md"):
            text = md_file.read_text(encoding="utf-8")
            placeholders = PLACEHOLDER_PATTERNS.findall(text)
            if placeholders:
                unique = sorted(set(placeholders))
                result.error(
                    f"Rules '{md_file.name}': contains placeholder(s): {', '.join(unique)}"
                )

    # 8. Cross-reference checks
    check_cross_references(root, agents, skills, workflows, result)

    return result


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <framework_dir> [--platform <platform_id>]")
        sys.exit(2)

    framework_dir = sys.argv[1]
    platform_id = None
    if "--platform" in sys.argv:
        idx = sys.argv.index("--platform")
        if idx + 1 < len(sys.argv):
            platform_id = sys.argv[idx + 1]

    if not os.path.isdir(framework_dir):
        print(f"Error: '{framework_dir}' is not a directory")
        sys.exit(2)

    result = validate_framework(framework_dir, platform_id)

    if result.warnings:
        print(f"\n--- Warnings ({len(result.warnings)}) ---")
        for w in result.warnings:
            print(f"  WARN: {w}")

    if result.errors:
        print(f"\n--- Errors ({len(result.errors)}) ---")
        for e in result.errors:
            print(f"  ERROR: {e}")
        print(f"\nValidation FAILED: {len(result.errors)} error(s), {len(result.warnings)} warning(s)")
        sys.exit(1)
    else:
        print(f"\nValidation PASSED: 0 errors, {len(result.warnings)} warning(s)")
        sys.exit(0)


if __name__ == "__main__":
    main()
