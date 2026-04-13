# Phase 3: Hook 桥接层 — 详细执行计划

> 前置条件: Phase 0-1（runtime 包）+ Phase 2 部分（tool_map 和 _registry）
> 可与 Phase 2 后半段并行: _hook_base.py 改造不依赖具体适配器
> 预计工时: 1 周

---

## 目标

1. 改造 `_hook_base.py` 实现统一的跨平台 stdin 解析
2. 将 8 个 Hook 脚本中硬编码的 Claude Code 工具名替换为动态解析
3. 实现 HookBridge 基础逻辑，支持事件映射和 graceful degrade

---

## 当前 Hook 脚本平台硬编码清单

| 脚本 | 硬编码 | 行号 | 影响 |
|------|--------|:----:|------|
| `_hook_base.py` | stdin JSON 解析（格式可能随平台变化） | L13-27 | 所有 Hook 的基础 |
| `guard_dangerous.py` | `data.get("tool_name") != "Bash"` | L61 | 安全守卫 |
| `log_agent_dispatch.py` | `data.get("tool_name") != "Agent"` | L55 | 调度审计 |
| `validate_agent_result.py` | `data.get("tool_name") != "Agent"` | L69 | 结果验证 |
| `detect_correction.py` | `data.get("tool_name") != "AskUserQuestion"` | L136 | 纠正学习 |
| `lint_format.py` | 无 tool_name 检查（通过 matcher 触发） | — | 自动格式化 |
| `notify_done.py` | `"Claude Code"` 字符串 | L27 | 通知 |
| `notify_permission.py` | 未检查（需确认） | — | 通知 |
| `session_context.py` | 未检查（需确认） | — | 会话初始化 |

---

## Step 3.1: _hook_base.py 统一解析层

### 修改: `.cataforge/hooks/_hook_base.py`

当前实现（L13-27）仅做 stdin JSON 读取。需扩展为：

1. **平台检测**: 从环境变量或 framework.json 判断当前平台
2. **字段名规范化**: 不同平台的 stdin JSON 字段名可能不同
3. **工具名解析**: 提供 `resolve_tool_name()` 便捷方法

```python
"""CataForge Hook Infrastructure — 跨平台共享工具。

提供:
- read_hook_input(): 统一 stdin JSON 读取 + Windows UTF-8 处理
- hook_main(): Hook 入口装饰器
- get_platform(): 当前运行时平台标识
- matches_tool(): 跨平台工具名匹配
"""
import json
import os
import sys


def read_hook_input() -> dict:
    """读取并解析 stdin JSON，带稳健的编码处理。

    各平台 stdin 格式差异由此函数内部吸收:
    - Claude Code: {"tool_name": "Agent", "tool_input": {...}, ...}
    - Cursor: {"tool_name": "Task", "tool_input": {...}, ...}  (camelCase 事件名但 payload 相似)
    - Codex: {"tool_name": "shell", "tool_input": {...}, ...}  (仅 5 事件)
    - OpenCode: 插件系统，无 stdin Hook（本函数不会被调用）
    """
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
    2. 环境变量特征检测:
       - CURSOR_PROJECT_DIR → cursor
       - CODEX_HOME → codex
       - CLAUDE_PROJECT_DIR（无其他特征） → claude-code
    3. fallback → claude-code
    """
    explicit = os.environ.get("CATAFORGE_PLATFORM")
    if explicit:
        return explicit

    if os.environ.get("CURSOR_PROJECT_DIR"):
        return "cursor"
    if os.environ.get("CODEX_HOME"):
        return "codex"

    return "claude-code"


# 能力标识符 → 各平台工具名（内联精简版，完整映射在 tool_map.yaml）
_DISPATCH_TOOL_NAMES = {
    "claude-code": "Agent",
    "cursor": "Task",
    "codex": "spawn_agent",
    "opencode": "task",
}

_SHELL_TOOL_NAMES = {
    "claude-code": "Bash",
    "cursor": "Shell",
    "codex": "shell",
    "opencode": "bash",
}

_USER_QUESTION_TOOL_NAMES = {
    "claude-code": "AskUserQuestion",
    "cursor": None,
    "codex": None,
    "opencode": "question",
}

_FILE_EDIT_TOOL_NAMES = {
    "claude-code": {"Edit", "Write"},
    "cursor": {"Write", "StrReplace"},
    "codex": {"apply_patch"},
    "opencode": {"edit", "write"},
}


def get_dispatch_tool_name(platform: str | None = None) -> str:
    """获取当前平台的调度工具名。"""
    return _DISPATCH_TOOL_NAMES.get(platform or get_platform(), "Agent")


def get_shell_tool_name(platform: str | None = None) -> str:
    """获取当前平台的 shell 工具名。"""
    return _SHELL_TOOL_NAMES.get(platform or get_platform(), "Bash")


def get_user_question_tool_name(platform: str | None = None) -> str | None:
    """获取当前平台的用户提问工具名。None 表示不支持。"""
    return _USER_QUESTION_TOOL_NAMES.get(platform or get_platform())


def get_file_edit_tool_names(platform: str | None = None) -> set[str]:
    """获取当前平台的文件编辑工具名集合。"""
    return _FILE_EDIT_TOOL_NAMES.get(platform or get_platform(), {"Edit", "Write"})


def matches_capability(data: dict, capability: str) -> bool:
    """检查 Hook stdin 数据中的 tool_name 是否匹配指定能力。

    Args:
        data: Hook stdin 解析后的 dict
        capability: 能力标识符 (agent_dispatch, shell_exec, user_question, file_edit)
    """
    tool_name = data.get("tool_name", "")
    platform = get_platform()

    if capability == "agent_dispatch":
        return tool_name == get_dispatch_tool_name(platform)
    elif capability == "shell_exec":
        return tool_name == get_shell_tool_name(platform)
    elif capability == "user_question":
        expected = get_user_question_tool_name(platform)
        return expected is not None and tool_name == expected
    elif capability == "file_edit":
        return tool_name in get_file_edit_tool_names(platform)
    return False


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

---

## Step 3.2: Hook 脚本去硬编码

### 修改: `.cataforge/hooks/guard_dangerous.py`

```python
# 旧 (L61)
if data.get("tool_name") != "Bash":
    sys.exit(0)

# 新
from _hook_base import matches_capability
# ...
if not matches_capability(data, "shell_exec"):
    sys.exit(0)
```

### 修改: `.cataforge/hooks/log_agent_dispatch.py`

```python
# 旧 (L55)
if not data or data.get("tool_name") != "Agent":
    sys.exit(0)

# 新
from _hook_base import matches_capability
# ...
if not data or not matches_capability(data, "agent_dispatch"):
    sys.exit(0)
```

### 修改: `.cataforge/hooks/validate_agent_result.py`

```python
# 旧 (L69)
if not data or data.get("tool_name") != "Agent":
    sys.exit(0)

# 新
from _hook_base import matches_capability
# ...
if not data or not matches_capability(data, "agent_dispatch"):
    sys.exit(0)
```

### 修改: `.cataforge/hooks/detect_correction.py`

```python
# 旧 (L136)
if not data or data.get("tool_name") != "AskUserQuestion":
    sys.exit(0)

# 新
from _hook_base import matches_capability
# ...
if not data or not matches_capability(data, "user_question"):
    sys.exit(0)
```

### 修改: `.cataforge/hooks/notify_done.py`

```python
# 旧 (L27)
send_notification("Claude Code", f"Task finished ({stop_reason})", beep_count=1)

# 新
from _hook_base import get_platform

_PLATFORM_DISPLAY = {
    "claude-code": "Claude Code",
    "cursor": "Cursor",
    "codex": "Codex CLI",
    "opencode": "OpenCode",
}
# ...
platform_name = _PLATFORM_DISPLAY.get(get_platform(), "CataForge")
send_notification(platform_name, f"Task finished ({stop_reason})", beep_count=1)
```

### lint_format.py — 无 tool_name 检查

`lint_format.py` 不检查 tool_name（通过 settings.json matcher 触发），但其 matcher `"Edit|Write"` 在 `settings.json` 中是 Claude Code 专用的。

**处理**: settings.json 的 matcher 值由 Phase 3 Step 3.3 处理（各平台 Hook 配置生成器负责翻译 matcher）。`lint_format.py` 自身无需修改。

---

## Step 3.3: Hook 配置生成

### 新增: `.cataforge/runtime/hook_bridge.py`

```python
"""HookBridge — Hook 事件映射与配置生成。

按功能分类 CataForge 的 8 个 Hook:

| 类别 | Hook | 最低要求事件 | Claude Code | Cursor | Codex | OpenCode |
|------|------|-------------|:-----------:|:------:|:-----:|:--------:|
| Safety | guard_dangerous | PreToolUse:shell | ✓ | ✓ | ✓ | 降级 |
| Audit | log_agent_dispatch | PreToolUse:dispatch | ✓ | ✓ | 降级 | 降级 |
| Audit | validate_agent_result | PostToolUse:dispatch | ✓ | ✓ | 降级 | 降级 |
| Format | lint_format | PostToolUse:file_edit | ✓ | ✓(afterFileEdit) | 降级 | 降级 |
| Learning | detect_correction | PostToolUse:user_question | ✓ | 降级 | 降级 | 降级 |
| Notification | notify_done | Stop | ✓ | ✓ | ✓ | 降级 |
| Notification | notify_permission | Notification | ✓ | 降级 | 降级 | 降级 |
| Context | session_context | SessionStart | ✓ | ✓ | ✓ | 降级 |

降级策略:
- Safety 类 Hook 不可降级，必须通过其他机制实现（如 Codex sandbox_mode）
- Audit/Format/Learning 类降级为框架内嵌（在调度前后的 Python 逻辑中执行）
- Notification 类可安全跳过
"""
import json
import os

from .adapters._registry import detect_platform


def get_hook_coverage(platform_id: str | None = None) -> dict[str, str]:
    """返回各 Hook 在指定平台上的覆盖状态。

    Returns:
        {hook_name: "native" | "degraded" | "unsupported"}
    """
    pid = platform_id or detect_platform()

    coverage = {
        "claude-code": {
            "guard_dangerous": "native",
            "log_agent_dispatch": "native",
            "validate_agent_result": "native",
            "lint_format": "native",
            "detect_correction": "native",
            "notify_done": "native",
            "notify_permission": "native",
            "session_context": "native",
        },
        "cursor": {
            "guard_dangerous": "native",
            "log_agent_dispatch": "native",
            "validate_agent_result": "native",
            "lint_format": "native",
            "detect_correction": "degraded",
            "notify_done": "native",
            "notify_permission": "degraded",
            "session_context": "native",
        },
        "codex": {
            "guard_dangerous": "native",
            "log_agent_dispatch": "degraded",
            "validate_agent_result": "degraded",
            "lint_format": "degraded",
            "detect_correction": "degraded",
            "notify_done": "native",
            "notify_permission": "degraded",
            "session_context": "native",
        },
        "opencode": {
            "guard_dangerous": "degraded",
            "log_agent_dispatch": "degraded",
            "validate_agent_result": "degraded",
            "lint_format": "degraded",
            "detect_correction": "degraded",
            "notify_done": "degraded",
            "notify_permission": "degraded",
            "session_context": "degraded",
        },
    }
    return coverage.get(pid, coverage["claude-code"])


def generate_platform_hooks_config(
    claude_settings_path: str,
    platform_id: str | None = None,
) -> dict:
    """从 .claude/settings.json 生成指定平台的 Hook 配置。

    Returns:
        平台原生格式的 Hook 配置 dict。
    """
    pid = platform_id or detect_platform()

    with open(claude_settings_path, "r", encoding="utf-8") as f:
        settings = json.load(f)

    if pid == "claude-code":
        return settings.get("hooks", {})

    elif pid == "cursor":
        from .adapters.cursor_hooks import translate_hooks_config
        return translate_hooks_config(settings)

    elif pid == "codex":
        from .adapters.codex_hooks import translate_hooks_config
        return translate_hooks_config(settings)

    elif pid == "opencode":
        return {}  # OpenCode 无原生 Hook，全部框架内嵌

    return {}
```

---

## settings.json matcher 问题

`.claude/settings.json` 的 hooks 段 matcher 值（`"Bash"`, `"Agent"`, `"Edit|Write"`, `"AskUserQuestion"`）是 Claude Code 专用的。

**处理策略**: 不修改 `.claude/settings.json`——它始终是 Claude Code 的原生配置。其他平台通过 `hook_bridge.generate_platform_hooks_config()` 从中翻译生成各自的配置文件:
- Cursor: `.cursor/hooks.json`
- Codex: `.codex/hooks.json`
- OpenCode: 无（全框架内嵌）

这意味着 `.claude/settings.json` 保持不变，作为"规范源"存在。

---

## 验收标准

| # | 标准 | 验证方式 |
|---|------|---------|
| AC-3.1 | `_hook_base.py` 的 `get_platform()` 能正确检测 4 个平台 | 设置环境变量测试 |
| AC-3.2 | `matches_capability()` 对 4 个平台均正确返回 | 单元测试 |
| AC-3.3 | 所有 Hook 脚本无 `"Agent"`, `"Bash"`, `"AskUserQuestion"` 字面量 | `grep -rn '"Agent"\|"Bash"\|"AskUserQuestion"' .cataforge/hooks/` 仅 `_hook_base.py` 内映射表命中 |
| AC-3.4 | `notify_done.py` 不含 `"Claude Code"` 字面量 | grep 验证 |
| AC-3.5 | `hook_bridge.py` 能为 Cursor 和 Codex 生成合法的 hooks 配置 | 输出 JSON 校验 |
| AC-3.6 | `.claude/settings.json` 未被修改 | `git diff .claude/settings.json` 为空 |

---

## 风险项

| 风险 | 影响 | 缓解方案 |
|------|------|---------|
| Cursor 的 Hook stdin 格式未完全文档化 | `_hook_base.py` 的字段映射可能不准确 | 在 Cursor 中实际运行一个简单 Hook 验证 stdin 格式 |
| `get_platform()` 环境变量检测可能有平台交叉 | 如 Cursor 同时设置 `CLAUDE_PROJECT_DIR` 和 `CURSOR_PROJECT_DIR` | 检测顺序已设计为 Cursor 优先 |
| OpenCode 全框架内嵌降级了所有 Hook | 安全守卫无法通过 Hook 实现 | OpenCode 可通过其 `permission` 14 类权限体系替代 guard_dangerous |
