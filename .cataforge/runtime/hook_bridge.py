"""Hook 桥接层 — 从 hooks.yaml + profile 生成平台 Hook 配置。

职责:
1. 读取 .cataforge/hooks/hooks.yaml（规范源）
2. 读取目标平台的 profile.yaml（event_map + matcher_map + degradation）
3. 生成平台原生 Hook 配置文件
4. 对 degraded Hook 生成替代内容（rules 注入 / prompt checklist）
"""
from __future__ import annotations
import json
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]

from .profile_loader import load_profile

_HOOKS_YAML = Path(__file__).resolve().parent.parent / "hooks" / "hooks.yaml"


def load_hooks_spec() -> dict:
    """加载规范 Hook 定义。"""
    if yaml is None:
        raise ImportError("PyYAML required for hooks.yaml parsing")
    with open(_HOOKS_YAML, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def generate_platform_hooks(platform_id: str) -> dict:
    """生成平台原生 Hook 配置。

    Returns:
        平台格式的 hooks dict（可直接 json.dump 写入配置文件）。
    """
    spec = load_hooks_spec()
    profile = load_profile(platform_id)
    hooks_profile = profile.get("hooks", {})

    event_map = hooks_profile.get("event_map", {})
    degradation = hooks_profile.get("degradation", {})

    platform_hooks: dict = {}

    for event_name, hook_list in spec.get("hooks", {}).items():
        platform_event = event_map.get(event_name)
        if platform_event is None:
            continue

        translated = []
        for hook_entry in hook_list:
            capability = hook_entry.get("matcher_capability", "")
            hook_name = _script_to_hook_name(hook_entry.get("script", ""))

            if degradation.get(hook_name) != "native":
                continue

            if capability:
                tool_map = profile.get("tool_map", {})
                native_tool = tool_map.get(capability)
                if native_tool is None:
                    continue
                platform_matcher = native_tool
            else:
                platform_matcher = ""

            translated.append({
                "matcher": platform_matcher,
                "hooks": [{
                    "type": hook_entry.get("type", "observe"),
                    "command": (
                        f'python "$CLAUDE_PROJECT_DIR/.cataforge/hooks/'
                        f'{hook_entry["script"]}"'
                    ),
                }],
            })

        if translated:
            platform_hooks[platform_event] = translated

    return platform_hooks


def get_degraded_hooks(platform_id: str) -> list[dict]:
    """获取需要退化处理的 Hook 列表及其替代策略。"""
    spec = load_hooks_spec()
    profile = load_profile(platform_id)
    degradation = profile.get("hooks", {}).get("degradation", {})
    templates = spec.get("degradation_templates", {})

    result = []
    for hook_name, status in degradation.items():
        if status == "degraded" and hook_name in templates:
            template = templates[hook_name]
            result.append({
                "name": hook_name,
                "strategy": template.get("strategy", "skip"),
                "content": template.get("content", ""),
                "reason": template.get("reason", ""),
            })
    return result


def apply_degradation(platform_id: str, project_root: Path) -> list[str]:
    """将退化策略具体化为文件变更。"""
    degraded = get_degraded_hooks(platform_id)
    actions: list[str] = []

    rules_content_parts = []

    for entry in degraded:
        strategy = entry["strategy"]
        content = entry["content"]

        if strategy == "rules_injection":
            rules_content_parts.append(content)
        elif strategy == "skip":
            actions.append(f"SKIP: {entry['name']} — {entry.get('reason', '')}")

    if rules_content_parts:
        auto_rules_dir = (
            project_root / ".cataforge" / "platforms" / platform_id
            / "overrides" / "rules"
        )
        auto_rules_dir.mkdir(parents=True, exist_ok=True)
        auto_rules_path = auto_rules_dir / "auto-safety-degradation.md"
        auto_rules_path.write_text(
            "# Auto-generated Safety Rules (Hook Degradation)\n\n"
            + "\n\n".join(rules_content_parts),
            encoding="utf-8",
        )
        actions.append(f"rules_injection → {auto_rules_path}")

    return actions


def _script_to_hook_name(script: str) -> str:
    """从脚本文件名推断 Hook 名: guard_dangerous.py → guard_dangerous"""
    return script.replace(".py", "")
