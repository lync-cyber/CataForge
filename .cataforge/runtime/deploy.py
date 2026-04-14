"""CataForge 平台部署编排。

从 .cataforge/（源定义）生成平台目录（部署产物）。
实现 D-1（源/产物分离）和 D-4（PROJECT-STATE.md → CLAUDE.md）。
"""
from __future__ import annotations
import json
import os
import platform as platform_mod
import shutil
from pathlib import Path

from .profile_loader import load_profile, detect_platform
from .frontmatter_translator import translate_agent_md
from .template_renderer import render_template


def get_project_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def deploy(platform_id: str) -> list[str]:
    """执行指定平台的完整部署。返回操作日志。"""
    root = get_project_root()
    profile = load_profile(platform_id)
    actions: list[str] = []

    if profile.get("agent_definition", {}).get("needs_deploy"):
        actions.extend(_deploy_agents(root, platform_id, profile))

    if profile.get("instruction_file", {}).get("reads_claude_md"):
        actions.extend(_deploy_claude_md(root, platform_id, profile))

    hooks_conf = profile.get("hooks", {})
    if hooks_conf.get("config_format"):
        actions.extend(_deploy_hooks(root, platform_id, profile))

    for output in profile.get("instruction_file", {}).get("additional_outputs", []):
        actions.extend(_deploy_additional_output(root, platform_id, output))

    actions.extend(_deploy_rules(root, platform_id, profile))

    _write_deploy_state(root, platform_id)

    return actions


def _deploy_agents(root: Path, platform_id: str, profile: dict) -> list[str]:
    """翻译并部署 AGENT.md 到平台目录。"""
    actions: list[str] = []
    source_dir = root / ".cataforge" / "agents"
    scan_dirs = profile.get("agent_definition", {}).get("scan_dirs", [])

    if not scan_dirs or not source_dir.is_dir():
        return actions

    target_dir = root / scan_dirs[0]
    target_dir.mkdir(parents=True, exist_ok=True)

    for agent_name in sorted(os.listdir(source_dir)):
        agent_src = source_dir / agent_name
        if not agent_src.is_dir():
            continue

        agent_dst = target_dir / agent_name
        agent_dst.mkdir(exist_ok=True)

        for md_file in sorted(agent_src.glob("*.md")):
            content = md_file.read_text(encoding="utf-8")
            translated = translate_agent_md(content, platform_id)
            (agent_dst / md_file.name).write_text(translated, encoding="utf-8")
            actions.append(
                f"agents/{agent_name}/{md_file.name} → {scan_dirs[0]}"
            )

    return actions


def _deploy_claude_md(root: Path, platform_id: str, profile: dict) -> list[str]:
    """从 PROJECT-STATE.md 生成 CLAUDE.md。"""
    state_path = root / ".cataforge" / "PROJECT-STATE.md"
    claude_md_path = root / "CLAUDE.md"

    if not state_path.is_file():
        return ["SKIP: PROJECT-STATE.md 不存在"]

    content = state_path.read_text(encoding="utf-8")
    content = content.replace("运行时: {platform}", f"运行时: {platform_id}")

    claude_md_path.write_text(content, encoding="utf-8")
    return [f"CLAUDE.md ← PROJECT-STATE.md (platform={platform_id})"]


def _deploy_hooks(root: Path, platform_id: str, profile: dict) -> list[str]:
    """从 hooks.yaml + profile 生成平台 Hook 配置。"""
    try:
        from .hook_bridge import generate_platform_hooks
        hooks_config = generate_platform_hooks(platform_id)
    except Exception as e:
        return [f"hooks: 生成失败 — {e}"]

    config_path_str = profile.get("hooks", {}).get("config_path")
    if not config_path_str:
        return []

    config_path = root / config_path_str
    config_path.parent.mkdir(parents=True, exist_ok=True)

    if config_path.is_file():
        try:
            existing = json.loads(config_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing = {}
    else:
        existing = {}

    existing["hooks"] = hooks_config
    config_path.write_text(
        json.dumps(existing, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return [f"hooks → {config_path_str}"]


def _deploy_additional_output(
    root: Path, platform_id: str, output: dict
) -> list[str]:
    """部署额外指令文件。"""
    target = output.get("target", "")
    fmt = output.get("format", "")

    if fmt == "mdc" and target:
        try:
            from ..platforms.cursor.deploy_rules import generate_cursor_rules
        except ImportError:
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "deploy_rules",
                root / ".cataforge" / "platforms" / "cursor" / "deploy_rules.py",
            )
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                return mod.generate_cursor_rules(
                    root / ".cataforge" / "rules",
                    root / ".cataforge" / "platforms" / "cursor" / "overrides" / "rules",
                    root / target,
                )
        return [f"additional: {target} (mdc generation skipped)"]

    return [f"additional: {target} (format={fmt})"]


def _deploy_rules(root: Path, platform_id: str, profile: dict) -> list[str]:
    """复制规则文件到平台目录。"""
    scan_dirs = profile.get("agent_definition", {}).get("scan_dirs", [])
    if not scan_dirs:
        return []

    platform_root = Path(scan_dirs[0]).parent
    target = root / platform_root / "rules"
    source = root / ".cataforge" / "rules"

    if not source.is_dir():
        return []

    if target.is_symlink():
        target.unlink()
    elif target.is_junction() if hasattr(target, "is_junction") else False:
        target.rmdir()
    elif target.exists() and target.is_dir():
        shutil.rmtree(target)

    target.parent.mkdir(parents=True, exist_ok=True)

    if platform_mod.system() != "Windows":
        rel = os.path.relpath(source, target.parent)
        target.symlink_to(rel)
        return [f"{target} → {source} (symlink)"]

    try:
        import subprocess
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(target), str(source)],
            check=True, capture_output=True,
        )
        return [f"{target} → {source} (junction)"]
    except (subprocess.CalledProcessError, FileNotFoundError):
        shutil.copytree(source, target)
        return [f"{target} ← {source} (copy)"]


def _write_deploy_state(root: Path, platform_id: str) -> None:
    """记录当前部署的平台。"""
    state_file = root / ".cataforge" / ".deploy-state"
    state_file.write_text(
        json.dumps({"platform": platform_id}, indent=2) + "\n",
        encoding="utf-8",
    )
