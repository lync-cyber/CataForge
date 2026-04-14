"""AGENT.md YAML frontmatter → Codex TOML 转换。"""
from __future__ import annotations
import os
import re
from pathlib import Path

try:
    import tomli_w
except ImportError:
    tomli_w = None  # type: ignore[assignment]


def convert_agent_to_toml(agent_md_path: Path, platform_id: str = "codex") -> str:
    """将 AGENT.md 转换为 Codex TOML 格式。"""
    content = agent_md_path.read_text(encoding="utf-8")
    fm, body = _split_frontmatter(content)

    if not fm:
        raise ValueError(f"No YAML frontmatter in {agent_md_path}")

    toml_data = {
        "name": fm.get("name", ""),
        "description": fm.get("description", ""),
        "developer_instructions": body.strip(),
    }

    if fm.get("model") and fm["model"] != "inherit":
        toml_data["model"] = fm["model"]

    if tomli_w:
        return tomli_w.dumps(toml_data)
    return _manual_toml(toml_data)


def sync_agents_to_codex(source_dir: Path, codex_dir: Path) -> list[str]:
    """批量转换 .cataforge/agents/ → .codex/agents/。"""
    codex_dir.mkdir(parents=True, exist_ok=True)
    generated: list[str] = []

    for agent_name in sorted(os.listdir(source_dir)):
        agent_md = source_dir / agent_name / "AGENT.md"
        if not agent_md.is_file():
            continue

        toml_content = convert_agent_to_toml(agent_md)
        toml_path = codex_dir / f"{agent_name}.toml"
        toml_path.write_text(toml_content, encoding="utf-8")
        generated.append(str(toml_path))

    return generated


def _split_frontmatter(content: str) -> tuple[dict | None, str]:
    try:
        import yaml
    except ImportError:
        return None, content

    m = re.match(r"^---\n(.*?)\n---\n?(.*)", content, re.DOTALL)
    if not m:
        return None, content
    try:
        fm = yaml.safe_load(m.group(1))
    except Exception:
        fm = None
    return fm, m.group(2)


def _manual_toml(data: dict) -> str:
    lines: list[str] = []
    for key, value in data.items():
        if isinstance(value, str):
            if "\n" in value:
                lines.append(f'{key} = """\n{value}\n"""')
            else:
                lines.append(f'{key} = "{value}"')
    return "\n".join(lines) + "\n"
