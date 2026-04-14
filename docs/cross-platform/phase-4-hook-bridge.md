# Phase 4: Hook 桥接层

> 前置条件：Phase 2（目录结构）+ Phase 3 部分（profile.yaml 完善）
> 可与 Phase 3 后半段并行：_hook_base.py 改造不依赖具体适配器
> 预计工时：1 周

---

## 目标

1. 改造 `_hook_base.py`，实现跨平台 stdin 解析（工具名从 profile.yaml 单源获取）
2. 将 8 个 Hook 脚本中硬编码的 Claude Code 工具名替换为动态解析
3. 实现 `hook_bridge.py`，从 `hooks.yaml` + profile 生成平台 Hook 配置
4. 实现退化策略的具体行为（rules 注入、prompt checklist 等）

---

## 设计原理

### 单一事实来源

v1 方案存在双源问题：`tool_map.yaml` 和 `_hook_base.py` 内联字典维护各自的映射。v2 方案统一到 `profile.yaml`：

```
profile.yaml (tool_map)
       │
       ├──→ _hook_base.py 运行时查询（get_platform_tool_name）
       │
       └──→ hook_bridge.py deploy 时翻译（生成平台 Hook 配置）
```

Hook 脚本运行时通过 `_hook_base.py` 查询 `profile.yaml` 判断当前工具名，而非硬编码。

### hooks.yaml 作为规范源

`.cataforge/hooks/hooks.yaml`（Phase 1 已创建）定义了所有 Hook 的规范行为。deploy 时 `hook_bridge.py` 读取 hooks.yaml + profile 的 event_map/matcher_map 生成平台配置。

---

## Step 4.1: _hook_base.py 跨平台解析

### 修改：`.cataforge/hooks/_hook_base.py`

```python
#!/usr/bin/env python3
"""CataForge Hook Infrastructure — 跨平台共享工具。

提供:
- read_hook_input(): 统一 stdin JSON 读取
- hook_main(): Hook 入口装饰器
- get_platform(): 当前运行时平台标识
- matches_capability(): 跨平台工具名匹配（从 profile.yaml 单源查询）
"""
import json
import os
import sys
from pathlib import Path


def read_hook_input() -> dict:
    """读取并解析 stdin JSON，带稳健的编码处理。"""
    try:
        raw = sys.stdin.buffer.read()
        text = raw.decode("utf-8", errors="replace")
        return json.loads(text)
    except (json.JSONDecodeError, ValueError, UnicodeDecodeError, AttributeError):
        return {}


def get_platform() -> str:
    """获取当前运行时平台标识。

    检测顺序:
    1. 环境变量 CATAFORGE_PLATFORM（显式覆盖）
    2. 环境变量特征检测
    3. framework.json fallback
    """
    explicit = os.environ.get("CATAFORGE_PLATFORM")
    if explicit:
        return explicit

    if os.environ.get("CURSOR_PROJECT_DIR"):
        return "cursor"
    if os.environ.get("CODEX_HOME"):
        return "codex"

    return _detect_from_framework_json()


def _detect_from_framework_json() -> str:
    """从 framework.json 读取平台标识。"""
    try:
        fj_path = Path(__file__).resolve().parent.parent / "framework.json"
        with open(fj_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        return config.get("runtime", {}).get("platform", "claude-code")
    except (OSError, json.JSONDecodeError):
        return "claude-code"


# --- 工具名解析（从 profile.yaml 单源加载，运行时缓存）---

_tool_map_cache: dict[str, dict] | None = None


def _load_tool_map() -> dict[str, dict]:
    """加载当前平台的 tool_map，带缓存。"""
    global _tool_map_cache
    if _tool_map_cache is not None:
        return _tool_map_cache

    platform_id = get_platform()
    try:
        import yaml
        profile_path = (
            Path(__file__).resolve().parent.parent
            / "platforms" / platform_id / "profile.yaml"
        )
        with open(profile_path, "r", encoding="utf-8") as f:
            profile = yaml.safe_load(f)
        _tool_map_cache = profile.get("tool_map", {})
    except Exception:
        # Fallback: Claude Code 默认映射（零依赖，不需要 yaml）
        _tool_map_cache = {
            "file_read": "Read", "file_write": "Write", "file_edit": "Edit",
            "file_glob": "Glob", "file_grep": "Grep", "shell_exec": "Bash",
            "web_search": "WebSearch", "web_fetch": "WebFetch",
            "user_question": "AskUserQuestion", "agent_dispatch": "Agent",
        }
    return _tool_map_cache


def get_platform_tool_name(capability: str) -> str | None:
    """获取当前平台的工具名。None 表示不支持。"""
    return _load_tool_map().get(capability)


def matches_capability(data: dict, capability: str) -> bool:
    """检查 Hook stdin 中的 tool_name 是否匹配指定能力。

    Args:
        data: Hook stdin 解析后的 dict
        capability: 能力标识符 (agent_dispatch, shell_exec, ...)
    """
    tool_name = data.get("tool_name", "")
    expected = get_platform_tool_name(capability)

    if expected is None:
        return False

    # file_edit 特殊处理: 某些平台有多个编辑工具
    if capability == "file_edit":
        edit_tools = {expected}
        write_name = get_platform_tool_name("file_write")
        if write_name:
            edit_tools.add(write_name)
        return tool_name in edit_tools

    return tool_name == expected


def hook_main(func):
    """Hook 入口装饰器。异常捕获 + 保证 exit 0。"""
    def wrapper():
        try:
            return func()
        except SystemExit:
            raise
        except Exception as e:
            print(
                f"[HOOK-ERROR] {func.__module__}.{func.__name__}: {e}",
                file=sys.stderr,
            )
            sys.exit(0)
    return wrapper
```

### 设计要点

1. **单源查询**：`_load_tool_map()` 从 `profile.yaml` 加载，而非硬编码映射字典
2. **缓存**：profile 仅加载一次，后续调用使用缓存
3. **零依赖 fallback**：如果 yaml 模块不存在或 profile 文件缺失，回退到 Claude Code 默认映射
4. **兼容性**：`matches_capability()` 的 API 与 v1 设计兼容，Hook 脚本仅需替换判断逻辑

---

## Step 4.2: Hook 脚本去硬编码

### 变更清单


| 脚本                       | 旧代码                                          | 新代码                                              |
| ------------------------ | -------------------------------------------- | ------------------------------------------------ |
| guard_dangerous.py       | `data.get("tool_name") != "Bash"`            | `not matches_capability(data, "shell_exec")`     |
| log_agent_dispatch.py    | `data.get("tool_name") != "Agent"`           | `not matches_capability(data, "agent_dispatch")` |
| validate_agent_result.py | `data.get("tool_name") != "Agent"`           | `not matches_capability(data, "agent_dispatch")` |
| detect_correction.py     | `data.get("tool_name") != "AskUserQuestion"` | `not matches_capability(data, "user_question")`  |
| notify_done.py           | `"Claude Code"` 字符串                          | `get_platform_display_name()`                    |
| lint_format.py           | 无 tool_name 检查                               | 无变更（matcher 由 Hook 配置控制）                         |
| notify_permission.py     | 无平台硬编码                                       | 无变更                                              |
| session_context.py       | 无平台硬编码                                       | **新增**: deploy 自动同步触发                            |


### session_context.py 增强

SessionStart hook 新增 deploy 自动同步，确保会话启动时 CLAUDE.md 与 PROJECT-STATE.md 同步：

```python
# session_context.py 新增逻辑
def _auto_deploy():
    """会话启动时自动运行 deploy 同步。"""
    try:
        import subprocess
        cataforge_dir = Path(__file__).resolve().parent.parent
        deploy_script = cataforge_dir / "scripts" / "framework" / "deploy.py"
        if deploy_script.is_file():
            subprocess.run(
                [sys.executable, str(deploy_script)],
                timeout=15, capture_output=True,
            )
    except Exception:
        pass  # deploy 失败不阻塞会话
```

### notify_done.py 平台显示名

```python
# 旧
send_notification("Claude Code", f"Task finished ({stop_reason})")

# 新
from _hook_base import get_platform

_DISPLAY_NAMES = {
    "claude-code": "Claude Code",
    "cursor": "Cursor",
    "codex": "Codex CLI",
    "opencode": "OpenCode",
}

platform_name = _DISPLAY_NAMES.get(get_platform(), "CataForge")
send_notification(platform_name, f"Task finished ({stop_reason})")
```

---

## Step 4.3: hook_bridge.py — Hook 配置生成与退化

### 修改：`.cataforge/runtime/hook_bridge.py`

```python
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

import yaml

from .profile_loader import load_profile

_HOOKS_YAML = Path(__file__).resolve().parent.parent / "hooks" / "hooks.yaml"


def load_hooks_spec() -> dict:
    """加载规范 Hook 定义。"""
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
    matcher_map = hooks_profile.get("matcher_map", {})
    degradation = hooks_profile.get("degradation", {})

    platform_hooks = {}

    for event_name, hook_list in spec.get("hooks", {}).items():
        platform_event = event_map.get(event_name)
        if platform_event is None:
            continue  # 平台不支持此事件

        translated = []
        for hook_entry in hook_list:
            capability = hook_entry.get("matcher_capability", "")
            hook_name = _script_to_hook_name(hook_entry.get("script", ""))

            # 检查该 Hook 是否为 native
            if degradation.get(hook_name) != "native":
                continue  # degraded/unsupported → 不生成配置

            # 翻译 matcher
            if capability:
                tool_map = profile.get("tool_map", {})
                native_tool = tool_map.get(capability)
                if native_tool is None:
                    continue  # 平台不支持该能力 → 跳过

                # 构建 matcher（使用平台原生工具名）
                platform_matcher = native_tool
            else:
                platform_matcher = ""

            translated.append({
                "matcher": platform_matcher,
                "hooks": [{
                    "type": hook_entry.get("type", "observe"),
                    "command": f'python "$CLAUDE_PROJECT_DIR/.cataforge/hooks/{hook_entry["script"]}"',
                }],
            })

        if translated:
            platform_hooks[platform_event] = translated

    return platform_hooks


def get_degraded_hooks(platform_id: str) -> list[dict]:
    """获取需要退化处理的 Hook 列表及其替代策略。

    Returns:
        [{"name": "guard_dangerous", "strategy": "rules_injection", "content": "..."}]
    """
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
    """将退化策略具体化为文件变更。

    策略实现:
    - rules_injection: 写入 .cataforge/platforms/{id}/overrides/rules/auto-safety.md
    - prompt_checklist: 写入 override 的 return_format 段落
    - prompt_instruction: 写入 override 的 tool_usage 段落
    - skip: 无操作
    """
    degraded = get_degraded_hooks(platform_id)
    actions = []

    rules_content_parts = []
    prompt_additions = []

    for entry in degraded:
        strategy = entry["strategy"]
        content = entry["content"]

        if strategy == "rules_injection":
            rules_content_parts.append(content)
        elif strategy in ("prompt_checklist", "prompt_instruction"):
            prompt_additions.append(content)
        elif strategy == "skip":
            actions.append(f"SKIP: {entry['name']} — {entry.get('reason', '')}")

    # 写入自动生成的安全规则
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
```

---

## 验收标准


| #      | 标准                                                              | 验证方式                                                                            |
| ------ | --------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| AC-4.1 | `_hook_base.py` 的 `matches_capability()` 从 profile.yaml 单源查询    | 代码审查 + 单元测试                                                                     |
| AC-4.2 | 所有 Hook 脚本无 `"Agent"`, `"Bash"`, `"AskUserQuestion"` 硬编码        | `grep -rn '"Agent"|"Bash"|"AskUserQuestion"' .cataforge/hooks/` 仅 fallback 映射命中 |
| AC-4.3 | `hook_bridge.generate_platform_hooks("cursor")` 产出合法 JSON       | 单元测试                                                                            |
| AC-4.4 | `hook_bridge.get_degraded_hooks("opencode")` 返回 8 个 degraded 条目 | 单元测试                                                                            |
| AC-4.5 | `apply_degradation("opencode")` 生成 `auto-safety-degradation.md` | 文件检查                                                                            |
| AC-4.6 | `session_context.py` 在 SessionStart 时自动触发 deploy                | 手动验证                                                                            |
| AC-4.7 | `notify_done.py` 显示正确的平台名                                       | 手动验证                                                                            |


---

## 风险项


| 风险                          | 影响                        | 缓解                                            |
| --------------------------- | ------------------------- | --------------------------------------------- |
| PyYAML 在 Hook 运行时不可用        | `_load_tool_map()` 失败     | fallback 到 Claude Code 默认映射（已实现）              |
| profile.yaml 路径变更后 Hook 找不到 | 所有平台检测失败                  | `get_platform()` 优先用环境变量，profile 为最后 fallback |
| SessionStart deploy 超时      | 会话启动延迟                    | 设置 15s 超时，失败不阻塞                               |
| Cursor Hook stdin 格式与假设不同   | `matches_capability()` 误判 | Phase 0 H-3 已验证格式，Phase 4 基于验证结论实现            |


