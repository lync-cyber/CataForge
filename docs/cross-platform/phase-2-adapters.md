# Phase 2: 平台适配器 — 详细执行计划

> 前置条件: Phase 0-1 完成（`.cataforge/runtime/` 包、接口、Claude Code 适配器）
> 预计工时: 2-3 周（3 个适配器按优先级串行，可部分并行）
> 优先级: P0 OpenCode → P1 Cursor → P2 Codex CLI

---

## 优先级排序依据

| 优先级 | 平台 | 兼容成本 | 理由 |
|:------:|------|:--------:|------|
| P0 | OpenCode | 最低 | Agent 定义零拷贝（扫描 `.claude/agents/`）、指令文件零配置（读 `CLAUDE.md`）、`task` tool 参数几乎相同 |
| P1 | Cursor | 中等 | Agent 定义零拷贝、Hook 事件名映射（camelCase）、需生成 `.cursor/rules/` |
| P2 | Codex CLI | 最高 | TOML 格式转换、ThreadManager 5 工具封装、Hook 仅 5 事件 |

---

## Step 2.1: OpenCode 适配器 (P0)

### 新增: `.cataforge/runtime/adapters/opencode.py`

```python
"""OpenCode 适配器 — 与 Claude Code 最相似的平台。

OpenCode 特征:
- 调度工具: task（参数: subagent_type, description, prompt）
- Agent 定义: Markdown + YAML frontmatter (.opencode/agents/ 或 .claude/agents/ fallback)
- 指令文件: AGENTS.md（兼容 CLAUDE.md fallback）
- Hooks: 插件系统（JS/TS 模块，无原生 Hook）
- 独有字段: permission（14 类细粒度权限）

与 Claude Code 的关键差异:
1. 调度工具名: task (非 Agent)
2. 无原生 Hook → 框架内嵌或生成插件
3. permission 14 类字段通过 platform_extras 透传
"""
from ..interfaces import AgentDispatcher
from ..types import DispatchRequest, AgentResult


class OpenCodeDispatcher(AgentDispatcher):
    def dispatch(self, request: DispatchRequest) -> AgentResult:
        raise NotImplementedError(
            "OpenCodeDispatcher.dispatch() — prompt 模板驱动调度。"
            "调度格式: task(subagent_type=agent_id, description=..., prompt=...)"
        )

    def platform_id(self) -> str:
        return "opencode"
```

### Agent 定义处理

OpenCode 原生扫描 `.claude/agents/` 作为 fallback → **零拷贝**，无需额外目录。
能力标识符由 ToolNameResolver 在调度时翻译。

### 指令文件处理

OpenCode 原生读取 `CLAUDE.md` 作为 fallback → **零配置**。

### Hook 处理

OpenCode 无原生 Hook 系统，使用插件系统（event emitter）。
**Phase 2 策略**: 全部降级为框架内嵌逻辑（不生成插件），在 Phase 3 决定是否生成。

### 验收标准

| # | 标准 |
|---|------|
| AC-2.1.1 | `_registry.py` 能返回 OpenCode 适配器实例 |
| AC-2.1.2 | `tool_map.yaml` 的 opencode 段落被正确加载 |
| AC-2.1.3 | ToolNameResolver 正确翻译: `agent_dispatch` → `task`, `shell_exec` → `bash` 等 |

---

## Step 2.2: Cursor 适配器 (P1)

### 新增: `.cataforge/runtime/adapters/cursor.py`

```python
"""Cursor 适配器。

Cursor 特征:
- 调度工具: Task（参数: subagent_type, prompt, model, max_turns）
- Agent 定义: Markdown + YAML frontmatter (.cursor/agents/ 或 .claude/agents/ fallback)
- 指令文件: .cursor/rules/ (MDC 格式) + .cursorrules
- Hooks: .cursor/hooks.json（15+ 事件，camelCase 命名）
- 独有字段: readonly (frontmatter), is_background (frontmatter)
- Task tool 独有参数: max_turns (其他平台在 frontmatter 定义 maxTurns)

与 Claude Code 的关键差异:
1. 调度工具名: Task (非 Agent)
2. Hook 事件名: camelCase (preToolUse vs PreToolUse)
3. 工具名不同: Shell(非Bash), StrReplace(非Edit)
4. 无 disallowedTools frontmatter — 由平台自身控制
5. 指令文件: .cursor/rules/ MDC 格式（非 CLAUDE.md）
"""
from ..interfaces import AgentDispatcher
from ..types import DispatchRequest, AgentResult


class CursorDispatcher(AgentDispatcher):
    def dispatch(self, request: DispatchRequest) -> AgentResult:
        raise NotImplementedError(
            "CursorDispatcher.dispatch() — prompt 模板驱动调度。"
            "调度格式: Task(subagent_type=agent_id, prompt=..., max_turns=...)"
        )

    def platform_id(self) -> str:
        return "cursor"
```

### 新增: `.cataforge/runtime/adapters/cursor_hooks.py`

```python
"""Cursor Hook 事件名映射。

Claude Code 使用 PascalCase，Cursor 使用 camelCase。
仅映射 CataForge 实际使用的事件。
"""

EVENT_MAP = {
    # CataForge Hook → Cursor 事件名
    "PreToolUse": "preToolUse",
    "PostToolUse": "postToolUse",
    "Stop": "stop",
    "SessionStart": "sessionStart",
    "Notification": None,  # Cursor 无等价事件 → 降级
}

MATCHER_MAP = {
    # CataForge matcher → Cursor matcher
    "Bash": "Shell",
    "Agent": "Task",
    "Edit|Write": "Write",  # Cursor 的 afterFileEdit 覆盖
    "AskUserQuestion": None,  # Cursor 无等价 → 降级
}


def translate_hooks_config(claude_settings: dict) -> dict:
    """将 .claude/settings.json 的 hooks 段翻译为 .cursor/hooks.json 格式。

    返回 Cursor hooks.json 格式的 dict。
    不支持的事件/matcher 被跳过（graceful degrade）。
    """
    cursor_hooks = {}
    for event_name, hook_list in claude_settings.get("hooks", {}).items():
        cursor_event = EVENT_MAP.get(event_name)
        if not cursor_event:
            continue

        translated = []
        for hook_entry in hook_list:
            matcher = hook_entry.get("matcher", "")
            cursor_matcher = MATCHER_MAP.get(matcher, matcher)
            if cursor_matcher is None:
                continue

            translated.append({
                "matcher": cursor_matcher,
                "hooks": hook_entry.get("hooks", []),
            })

        if translated:
            cursor_hooks[cursor_event] = translated

    return cursor_hooks
```

### 新增: `.cataforge/runtime/adapters/cursor_rules_gen.py`

```python
"""从 CLAUDE.md 生成 .cursor/rules/ MDC 格式文件。

Cursor rules 使用 MDC (Markdown Configuration) 格式:
- YAML frontmatter: description, globs, alwaysApply
- Markdown body: 规则内容

生成策略:
1. CLAUDE.md §全局约定 → .cursor/rules/project-conventions.mdc (alwaysApply: true)
2. CLAUDE.md §框架机制 → .cursor/rules/framework.mdc (alwaysApply: true)
3. .cataforge/rules/COMMON-RULES.md → .cursor/rules/common-rules.mdc (alwaysApply: true)
"""
import os
import re


def generate_cursor_rules(claude_md_path: str, output_dir: str) -> list[str]:
    """从 CLAUDE.md 提取规则生成 .cursor/rules/ 文件。

    Returns:
        生成的文件路径列表。
    """
    os.makedirs(output_dir, exist_ok=True)
    generated = []

    with open(claude_md_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 提取 §全局约定 段落
    conventions = _extract_section(content, "全局约定")
    if conventions:
        path = os.path.join(output_dir, "project-conventions.mdc")
        _write_mdc(path, "CataForge 项目全局约定", conventions, always_apply=True)
        generated.append(path)

    # 提取 §框架机制 段落
    framework = _extract_section(content, "框架机制")
    if framework:
        path = os.path.join(output_dir, "framework.mdc")
        _write_mdc(path, "CataForge 框架机制", framework, always_apply=True)
        generated.append(path)

    return generated


def _extract_section(content: str, heading: str) -> str | None:
    """提取指定 ## 标题下的内容（到下一个 ## 为止）。"""
    pattern = rf"^## {re.escape(heading)}\s*\n(.*?)(?=^## |\Z)"
    m = re.search(pattern, content, re.MULTILINE | re.DOTALL)
    return m.group(1).strip() if m else None


def _write_mdc(path: str, description: str, body: str, always_apply: bool = False):
    """写出 MDC 格式文件。"""
    frontmatter = f"---\ndescription: \"{description}\"\nalwaysApply: {str(always_apply).lower()}\n---\n\n"
    with open(path, "w", encoding="utf-8") as f:
        f.write(frontmatter + body + "\n")
```

### Agent 定义处理

Cursor 原生扫描 `.claude/agents/` → **零拷贝**。
Cursor 不识别的 frontmatter 字段（`skills`, `hooks`, `allowed_paths`）被忽略，由 CataForge 框架层自行解释。

### 验收标准

| # | 标准 |
|---|------|
| AC-2.2.1 | `_registry.py` 返回 Cursor 适配器实例 |
| AC-2.2.2 | `cursor_hooks.py` 正确翻译 PreToolUse→preToolUse, Agent→Task |
| AC-2.2.3 | `cursor_rules_gen.py` 从示例 CLAUDE.md 生成合法 MDC 文件 |
| AC-2.2.4 | ToolNameResolver 正确翻译: `file_edit` → `StrReplace`, `shell_exec` → `Shell` |

---

## Step 2.3: Codex CLI 适配器 (P2)

### 新增: `.cataforge/runtime/adapters/codex.py`

```python
"""Codex CLI 适配器 — 差异最大的平台。

Codex CLI 特征:
- 调度工具: spawn_agent + send_input + resume_agent + wait_agent + close_agent（5 工具协作）
- Agent 定义: TOML 格式 (.codex/agents/ 或 ~/.codex/agents/)
- 指令文件: AGENTS.md + AGENTS.override.md（可配置 fallback 读 CLAUDE.md）
- Hooks: .codex/hooks.json（仅 5 事件: PreToolUse(Bash), PostToolUse(Bash), SessionStart, UserPromptSubmit, Stop）
- 独有特性: fork_context（分叉父上下文）、max_depth（嵌套深度）、sandbox_mode

与 Claude Code 的关键差异:
1. 两步调度: spawn_agent → wait_agent
2. Agent 定义: TOML（非 Markdown YAML）
3. Hook 仅 5 事件（PreToolUse/PostToolUse 仅 Bash matcher）
4. 无 AskUserQuestion（异步线程模式）
5. 工具名: shell/apply_patch（非 Bash/Edit）
"""
from ..interfaces import AgentDispatcher
from ..types import DispatchRequest, AgentResult


class CodexDispatcher(AgentDispatcher):
    def dispatch(self, request: DispatchRequest) -> AgentResult:
        raise NotImplementedError(
            "CodexDispatcher.dispatch() — prompt 模板驱动调度。"
            "调度格式: spawn_agent(agent=agent_id, fork_context=false, prompt=...) → wait_agent(thread_id)"
        )

    def platform_id(self) -> str:
        return "codex"
```

### 新增: `.cataforge/runtime/adapters/codex_definition.py`

```python
"""Markdown YAML frontmatter → Codex TOML 转换器。

规范格式（.cataforge/agents/*/AGENT.md）使用 Markdown + YAML frontmatter。
Codex CLI 使用 TOML 格式（.codex/agents/*.toml）。
本模块负责双向转换。
"""
import os
import re

try:
    import tomli_w  # TOML 写入
except ImportError:
    tomli_w = None

try:
    import tomllib  # Python 3.11+ 内置
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None


def yaml_frontmatter_to_toml(agent_md_path: str) -> str:
    """将 AGENT.md 的 YAML frontmatter 转换为 Codex TOML 格式。

    字段映射:
        name → name
        description → description
        model → model (能力标识符保留，Codex 平台自行解释)
        Markdown body → developer_instructions
        tools → (Codex 不使用此字段，跳过)
        disallowedTools → (Codex 不使用，跳过)
        allowed_paths → sandbox.writable_roots (如 Codex 支持)
        skills → [[skills.config]] (TOML 数组表)
        maxTurns → (Codex 用超时，跳过)
    """
    with open(agent_md_path, "r", encoding="utf-8") as f:
        content = f.read()

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

    skills = fm.get("skills", [])
    if skills:
        toml_data["skills"] = {"config": [{"name": s} for s in skills]}

    if tomli_w:
        return tomli_w.dumps(toml_data)
    else:
        return _manual_toml_format(toml_data)


def sync_agents_to_codex(canonical_dir: str, codex_dir: str) -> list[str]:
    """批量转换 .cataforge/agents/ → .codex/agents/。

    Returns:
        生成的 TOML 文件路径列表。
    """
    os.makedirs(codex_dir, exist_ok=True)
    generated = []

    for agent_name in os.listdir(canonical_dir):
        agent_md = os.path.join(canonical_dir, agent_name, "AGENT.md")
        if not os.path.isfile(agent_md):
            continue

        toml_content = yaml_frontmatter_to_toml(agent_md)
        toml_path = os.path.join(codex_dir, f"{agent_name}.toml")
        with open(toml_path, "w", encoding="utf-8") as f:
            f.write(toml_content)
        generated.append(toml_path)

    return generated


def _split_frontmatter(content: str) -> tuple[dict | None, str]:
    """拆分 YAML frontmatter 和 Markdown body。"""
    import yaml
    m = re.match(r"^---\n(.*?)\n---\n?(.*)", content, re.DOTALL)
    if not m:
        return None, content
    try:
        fm = yaml.safe_load(m.group(1))
    except Exception:
        fm = None
    return fm, m.group(2)


def _manual_toml_format(data: dict) -> str:
    """简易 TOML 格式化（无 tomli_w 时的 fallback）。"""
    lines = []
    for key, value in data.items():
        if isinstance(value, str):
            if "\n" in value:
                lines.append(f'{key} = """\n{value}\n"""')
            else:
                lines.append(f'{key} = "{value}"')
        elif isinstance(value, dict):
            lines.append(f"\n[{key}]")
            for k, v in value.items():
                lines.append(f'  {k} = {repr(v)}')
    return "\n".join(lines) + "\n"
```

### 新增: `.cataforge/runtime/adapters/codex_hooks.py`

```python
"""Codex CLI Hook 子集映射。

Codex CLI 仅支持 5 个 Hook 事件（均为 WIP 状态）:
- PreToolUse (仅 Bash matcher)
- PostToolUse (仅 Bash matcher)
- SessionStart
- UserPromptSubmit
- Stop

CataForge 的 8 个 Hook 中，可映射到 Codex 的:
- guard_dangerous (PreToolUse:Bash → PreToolUse:shell) ✓
- session_context (SessionStart → SessionStart) ✓
- notify_done (Stop → Stop) ✓
- log_agent_dispatch → 无等价（降级为框架内嵌）
- validate_agent_result → 无等价（降级为框架内嵌）
- lint_format → 无等价（降级为框架内嵌）
- detect_correction → 无等价（降级为框架内嵌）
- notify_permission → 无等价（降级为框架内嵌）
"""

SUPPORTED_EVENTS = ["PreToolUse", "PostToolUse", "SessionStart", "UserPromptSubmit", "Stop"]

MATCHER_MAP = {
    "Bash": "shell",  # Codex 的 PreToolUse/PostToolUse 仅匹配 shell
}

DEGRADED_HOOKS = [
    "log_agent_dispatch",
    "validate_agent_result",
    "lint_format",
    "detect_correction",
    "notify_permission",
]


def translate_hooks_config(claude_settings: dict) -> dict:
    """将 .claude/settings.json hooks 翻译为 .codex/hooks.json 格式。

    仅保留 Codex 支持的事件，其余标记为降级。
    """
    codex_hooks = {}
    for event_name, hook_list in claude_settings.get("hooks", {}).items():
        if event_name not in SUPPORTED_EVENTS:
            continue

        translated = []
        for hook_entry in hook_list:
            matcher = hook_entry.get("matcher", "")
            codex_matcher = MATCHER_MAP.get(matcher, matcher)

            if event_name in ("PreToolUse", "PostToolUse") and codex_matcher != "shell":
                continue

            translated.append({
                "matcher": codex_matcher,
                "hooks": hook_entry.get("hooks", []),
            })

        if translated:
            codex_hooks[event_name] = translated

    return codex_hooks
```

### 指令文件处理

Codex CLI 可配置 `project_doc_fallback_filenames: ["CLAUDE.md"]` 原生读取。
在 Codex 项目配置中添加此行即可，无需额外同步逻辑。

### 验收标准

| # | 标准 |
|---|------|
| AC-2.3.1 | `_registry.py` 返回 Codex 适配器实例 |
| AC-2.3.2 | `codex_definition.py` 能将 orchestrator/AGENT.md 转换为合法 TOML |
| AC-2.3.3 | `codex_hooks.py` 仅保留 3 个可映射 Hook（guard_dangerous, session_context, notify_done） |
| AC-2.3.4 | ToolNameResolver 正确翻译: `shell_exec` → `shell`, `agent_dispatch` → `spawn_agent` |
| AC-2.3.5 | `sync_agents_to_codex()` 批量转换 13 个 AGENT.md 无报错 |

---

## 修改: `.cataforge/runtime/adapters/_registry.py`

Phase 2 完成后，_registry.py 的 `get_dispatcher()` 应能返回 4 个平台中任意一个的适配器。
此文件在 Phase 1 中已包含完整的分支逻辑，Phase 2 仅需确认 import 路径正确。

---

## 风险项

| 风险 | 影响 | 缓解方案 |
|------|------|---------|
| Codex TOML 格式可能有未文档化的必填字段 | 生成的 TOML 被 Codex 拒绝 | 先在 Codex CLI 环境中手动创建一个 agent TOML，确认最小必填字段集 |
| Cursor 扫描 `.claude/agents/` 时可能不识别能力标识符 | Cursor 子代理启动失败 | Cursor 适配器中添加 `sync_from_canonical()` 将能力标识符翻译回 Cursor 原生工具名后写入 `.cursor/agents/` |
| OpenCode 插件系统变更频繁 | Hook 降级策略可能需要更新 | Phase 2 暂不实现 OpenCode 插件生成，全部框架内嵌 |
| PyYAML / tomli_w 依赖 | 部分平台环境无这些包 | codex_definition.py 已含 manual fallback；tool_map 可提供 JSON 备选 |
