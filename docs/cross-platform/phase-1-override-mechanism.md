# Phase 1: Override 机制 + 核心抽象

> 前置条件：Phase 0 完成（关键假设已验证）
> 预计工时：1-2 周
> 核心产出：Override 机制、PROJECT-STATE.md、platform profile 体系、runtime 工具层

---

## 目标

1. 建立段落级 Override 机制（D-2 的完整实现）
2. 引入 PROJECT-STATE.md 作为平台无关状态文件（D-4）
3. 建立 platform profile 体系（profile.yaml + tool_map）
4. 引入规范 hooks.yaml 作为 Hook 的源定义（D-3）
5. 实现 runtime 工具层（resolver、parser、renderer、deploy）

---

## Step 1.1: 平台配置体系

### 新增：`.cataforge/platforms/_schema.yaml`

定义 profile.yaml 的规范结构，所有平台 profile 必须符合此 schema。

```yaml
# profile.yaml 字段定义（文档性 schema，非 JSON Schema）
required_fields:
  platform_id: string       # 唯一标识: claude-code | cursor | codex | opencode
  display_name: string      # 用户可读名
  version_tested: string    # 最后验证的平台版本号

  tool_map:                  # 能力标识符 → 平台原生工具名
    file_read: string | null
    file_write: string | null
    file_edit: string | null
    file_glob: string | null
    file_grep: string | null
    shell_exec: string | null
    web_search: string | null
    web_fetch: string | null
    user_question: string | null
    agent_dispatch: string | null

  agent_definition:
    format: enum[yaml-frontmatter, toml]
    scan_dirs: list[string]       # 平台原生扫描的 Agent 目录
    needs_deploy: boolean         # 是否需要 deploy 翻译能力标识符

  instruction_file:
    reads_claude_md: boolean      # 平台是否原生读取 CLAUDE.md
    additional_outputs: list      # deploy 额外生成的指令文件
      # - target: string          # 目标路径
      #   format: enum[mdc, toml, markdown]
      #   source: string          # 来源描述

  dispatch:
    tool_name: string             # 调度工具名
    is_async: boolean             # 是否两步异步调度
    params: list[string]          # 工具参数列表

  hooks:
    config_format: enum[json, yaml, null]
    config_path: string | null    # 平台 Hook 配置文件路径
    event_map: map[string, string | null]    # CataForge事件 → 平台事件
    matcher_map: map[string, string | null]  # CataForge matcher → 平台 matcher
    degradation: map[string, enum[native, degraded, unsupported]]
```

### 新增：`.cataforge/platforms/claude-code/profile.yaml`

```yaml
platform_id: claude-code
display_name: Claude Code
version_tested: "1.0"

tool_map:
  file_read: Read
  file_write: Write
  file_edit: Edit
  file_glob: Glob
  file_grep: Grep
  shell_exec: Bash
  web_search: WebSearch
  web_fetch: WebFetch
  user_question: AskUserQuestion
  agent_dispatch: Agent

agent_definition:
  format: yaml-frontmatter
  scan_dirs:
    - .claude/agents
  needs_deploy: true    # 需要将能力标识符翻译为原生工具名

instruction_file:
  reads_claude_md: true
  additional_outputs: []  # Claude Code 直接读 CLAUDE.md，无额外产出

dispatch:
  tool_name: Agent
  is_async: false
  params: [subagent_type, prompt, description]

hooks:
  config_format: json
  config_path: .claude/settings.json
  event_map:
    PreToolUse: PreToolUse
    PostToolUse: PostToolUse
    Stop: Stop
    SessionStart: SessionStart
    Notification: Notification
  matcher_map:
    Bash: Bash
    Agent: Agent
    "Edit|Write": "Edit|Write"
    AskUserQuestion: AskUserQuestion
  degradation:
    guard_dangerous: native
    log_agent_dispatch: native
    validate_agent_result: native
    lint_format: native
    detect_correction: native
    notify_done: native
    notify_permission: native
    session_context: native
```

### 新增：`.cataforge/platforms/cursor/profile.yaml`

```yaml
platform_id: cursor
display_name: Cursor
version_tested: "0.48"    # Phase 0 验证时更新

tool_map:
  file_read: Read
  file_write: Write
  file_edit: StrReplace
  file_glob: Glob
  file_grep: Grep
  shell_exec: Shell
  web_search: WebSearch
  web_fetch: WebFetch
  user_question: null       # Cursor 无等价工具
  agent_dispatch: Task

agent_definition:
  format: yaml-frontmatter
  scan_dirs:
    - .claude/agents          # Cursor 原生扫描 .claude/agents/
    - .cursor/agents          # 也可使用专属目录
  needs_deploy: true

instruction_file:
  reads_claude_md: true       # Cursor 也读 CLAUDE.md 作为 workspace rule
  additional_outputs:
    - target: .cursor/rules/
      format: mdc
      source: rules + platform overrides

dispatch:
  tool_name: Task
  is_async: false
  params: [subagent_type, prompt, description, model]

hooks:
  config_format: json
  config_path: .cursor/hooks.json
  event_map:
    PreToolUse: preToolUse
    PostToolUse: postToolUse
    Stop: stop
    SessionStart: sessionStart
    Notification: null
  matcher_map:
    Bash: Shell
    Agent: Task
    "Edit|Write": Write
    AskUserQuestion: null
  degradation:
    guard_dangerous: native
    log_agent_dispatch: native
    validate_agent_result: native
    lint_format: native
    detect_correction: degraded
    notify_done: native
    notify_permission: degraded
    session_context: native
```

### 新增：`.cataforge/platforms/codex/profile.yaml`

```yaml
platform_id: codex
display_name: Codex CLI
version_tested: "0.1"       # 待 Phase 3 验证

tool_map:
  file_read: shell           # 通过 shell cat
  file_write: apply_patch
  file_edit: apply_patch
  file_glob: shell           # 通过 shell find
  file_grep: shell           # 通过 shell grep
  shell_exec: shell
  web_search: web_search
  web_fetch: shell           # 通过 shell curl
  user_question: null         # 无（异步线程模式）
  agent_dispatch: spawn_agent

agent_definition:
  format: toml
  scan_dirs:
    - .codex/agents
  needs_deploy: true          # 需要 YAML→TOML 转换

instruction_file:
  reads_claude_md: true       # 可配置 fallback
  additional_outputs: []

dispatch:
  tool_name: spawn_agent
  is_async: true              # spawn_agent → wait_agent 两步
  params: [agent, fork_context, prompt]

hooks:
  config_format: json
  config_path: .codex/hooks.json
  event_map:
    PreToolUse: PreToolUse
    PostToolUse: PostToolUse
    Stop: Stop
    SessionStart: SessionStart
    Notification: null
  matcher_map:
    Bash: shell
    Agent: null               # Codex PreToolUse 仅匹配 shell
    "Edit|Write": null
    AskUserQuestion: null
  degradation:
    guard_dangerous: native
    log_agent_dispatch: degraded
    validate_agent_result: degraded
    lint_format: degraded
    detect_correction: degraded
    notify_done: native
    notify_permission: degraded
    session_context: native
```

### 新增：`.cataforge/platforms/opencode/profile.yaml`

```yaml
platform_id: opencode
display_name: OpenCode
version_tested: "0.1"       # 待验证

tool_map:
  file_read: read
  file_write: write
  file_edit: edit
  file_glob: glob
  file_grep: grep
  shell_exec: bash
  web_search: websearch
  web_fetch: webfetch
  user_question: question
  agent_dispatch: task

agent_definition:
  format: yaml-frontmatter
  scan_dirs:
    - .claude/agents          # OpenCode 原生扫描 .claude/agents/ 作为 fallback
  needs_deploy: false         # 零拷贝（格式兼容，且 OpenCode 忽略未知 frontmatter）

instruction_file:
  reads_claude_md: true       # 原生读取
  additional_outputs: []

dispatch:
  tool_name: task
  is_async: false
  params: [subagent_type, description, prompt]

hooks:
  config_format: null         # OpenCode 无原生 Hook 系统
  config_path: null
  event_map: {}
  matcher_map: {}
  degradation:
    guard_dangerous: degraded
    log_agent_dispatch: degraded
    validate_agent_result: degraded
    lint_format: degraded
    detect_correction: degraded
    notify_done: degraded
    notify_permission: degraded
    session_context: degraded
```

---

## Step 1.2: 模板 Override 机制

### 设计规范

#### Override 标记语法

基础模板中使用成对 HTML 注释标记可覆盖区域：

```markdown
<!-- OVERRIDE:section_name -->
默认内容（当平台无 override 时使用）
<!-- /OVERRIDE:section_name -->
```

规则：

- 标记名使用 `snake_case`，全局唯一
- 标记必须成对出现
- 标记之间的内容为"默认实现"（通常是 Claude Code 的行为）
- 标记可嵌套在代码块内（模板渲染时处理）

#### Override 文件格式

平台 override 文件（如 `.cataforge/platforms/cursor/overrides/dispatch-prompt.md`）仅包含需要替换的段落：

```markdown
<!-- OVERRIDE:section_name -->
平台特化内容
<!-- /OVERRIDE:section_name -->
```

文件中只出现需要覆盖的段落。未出现的段落保留基础模板默认内容。

#### 渲染流程

```
template_renderer.render(
    base_path="skills/agent-dispatch/templates/dispatch-prompt.md",
    platform_id="cursor"
)
  ↓
1. 读取基础模板
2. 解析所有 OVERRIDE 标记点
3. 检查 platforms/cursor/overrides/dispatch-prompt.md 是否存在
4. 存在 → 解析 override 文件中的同名段落
5. 合并: 用 override 段落替换基础模板中的对应段落
6. 返回渲染后的最终文本
```

### dispatch-prompt.md Override 标记点设计

基础模板定义 5 个 override 标记点：


| 标记点               | 默认行为（Claude Code）                         | Cursor 覆盖                                       | Codex 覆盖                                            |
| ----------------- | ----------------------------------------- | ----------------------------------------------- | --------------------------------------------------- |
| `dispatch_syntax` | `Agent tool: subagent_type: "{agent_id}"` | `Task: subagent_type: "{agent_id}", model: ...` | `spawn_agent(agent="{agent_id}") → wait_agent(...)` |
| `startup_notes`   | `COMMON-RULES.md 已通过 .claude/rules/ 自动注入` | `COMMON-RULES.md 已通过 .cursor/rules/ 自动注入`       | `请先读取 .cataforge/rules/COMMON-RULES.md`             |
| `return_format`   | 标准 `<agent-result>` XML                   | 同默认（Cursor 子代理返回值格式兼容）                          | 简化版 `<agent-result>`（适配上下文限制）                       |
| `tool_usage`      | （空，无额外说明）                                 | `使用 Shell 而非 Bash，使用 StrReplace 而非 Edit`        | `使用 apply_patch 编辑文件，使用 shell 执行命令`                 |
| `context_limits`  | （空，无额外说明）                                 | （空）                                             | `Codex 上下文较小，优先传路径引用`                               |


### 新增：改造后的 `dispatch-prompt.md`

```markdown
# Agent Dispatch Prompt Template
> 本文件为 agent-dispatch 的核心 prompt 模板。
> 含 OVERRIDE 标记点，由 template_renderer 根据当前平台合并 override 后使用。

<!-- OVERRIDE:dispatch_syntax -->
Agent tool:
  subagent_type: "{agent_id}"
  description: "Phase {N}: {简短描述}"
  prompt: |
<!-- /OVERRIDE:dispatch_syntax -->

    当前项目: {项目名}。

    <!-- BEGIN COMMON-SECTIONS -->
<!-- OVERRIDE:startup_notes -->
    === 启动须知 ===
    - COMMON-RULES.md 已通过 .claude/rules/ 自动注入上下文，无需手动读取
    - 你的 AGENT.md 已通过 subagent_type 自动加载
<!-- /OVERRIDE:startup_notes -->
    - 开始工作前，阅读你的核心 Skill 的 SKILL.md（见 AGENT.md skills 列表）
    - 通用 Skill（doc-gen/doc-nav）仅在需要操作时查阅
    - 所有文档和报告输出使用中文（代码、变量命名、框架参数除外）
    - 信息不足时标注[ASSUMPTION]并给出合理默认值

    === 任务信息 ===
    任务: {task}
    任务类型: {task_type}
    输入文档: {input_docs}
    输出要求: {expected_output}
    {仅revision: REVIEW报告: {review_path}}
    {仅continuation: 用户回答: {answers}}
    {仅continuation: 上次中间产出: {intermediate_outputs}}
    {仅continuation: 恢复指引: {resume_guidance}}
    {仅amendment: 变更分析: {change_analysis}}

<!-- OVERRIDE:tool_usage -->
<!-- /OVERRIDE:tool_usage -->

    === 执行约束 ===
    - 新建文档(task_type=new_creation)至少执行一轮用户确认

<!-- OVERRIDE:return_format -->
    === 返回格式(必须严格遵循) ===
    完成后，你的最终回复中**必须**包含以下XML块:

    <agent-result>
    <status>completed|needs_input|blocked|approved|approved_with_notes|needs_revision|rolled-back</status>
    <outputs>产出物文件路径，逗号+空格分隔</outputs>
    <summary>执行摘要(≤3句)</summary>
    </agent-result>

    status 值含义见 COMMON-RULES §统一状态码。

    needs_input 时**必须**追加:
    <questions>[{"id":"Q1","text":"问题","options":["A: 说明","B: 说明"]}]</questions>
    <completed-steps>已完成的Skill步骤编号</completed-steps>
    <resume-guidance>从第N步恢复，具体上下文</resume-guidance>
<!-- /OVERRIDE:return_format -->

<!-- OVERRIDE:context_limits -->
<!-- /OVERRIDE:context_limits -->

    <!-- END COMMON-SECTIONS -->
```

### 新增：Cursor override 示例

`.cataforge/platforms/cursor/overrides/dispatch-prompt.md`：

```markdown
<!-- OVERRIDE:dispatch_syntax -->
Task:
  subagent_type: "{agent_id}"
  description: "Phase {N}: {简短描述}"
  prompt: |
<!-- /OVERRIDE:dispatch_syntax -->

<!-- OVERRIDE:startup_notes -->
    === 启动须知 ===
    - COMMON-RULES.md 已通过 .cursor/rules/ 或 .claude/rules/ 自动注入上下文
    - 你的 AGENT.md 已通过 subagent_type 自动加载
<!-- /OVERRIDE:startup_notes -->

<!-- OVERRIDE:tool_usage -->
    === 平台工具说明 ===
    - 文件编辑使用 StrReplace（非 Edit）
    - 命令执行使用 Shell（非 Bash）
    - 子代理调度使用 Task（非 Agent）
<!-- /OVERRIDE:tool_usage -->
```

### 新增：Codex override 示例

`.cataforge/platforms/codex/overrides/dispatch-prompt.md`：

```markdown
<!-- OVERRIDE:dispatch_syntax -->
调度（两步式）:
  Step 1: spawn_agent(agent="{agent_id}", fork_context=false, prompt=下方prompt内容)
  Step 2: wait_agent(thread_id=<step1返回的thread_id>)
  prompt: |
<!-- /OVERRIDE:dispatch_syntax -->

<!-- OVERRIDE:startup_notes -->
    === 启动须知 ===
    - 请首先读取 .cataforge/rules/COMMON-RULES.md（Codex 不自动注入规则文件）
    - 你的角色定义见 .cataforge/agents/{agent_id}/AGENT.md
<!-- /OVERRIDE:startup_notes -->

<!-- OVERRIDE:tool_usage -->
    === 平台工具说明 ===
    - 文件编辑使用 apply_patch
    - 命令执行使用 shell
    - 不可使用 AskUserQuestion（异步模式，如需输入返回 blocked）
<!-- /OVERRIDE:tool_usage -->

<!-- OVERRIDE:context_limits -->
    === 上下文限制 ===
    Codex CLI 上下文窗口较小:
    - 输入文档仅传递路径引用，不内嵌全文
    - 优先分拆为多个子任务而非一次性完成
    - 产出中避免复制输入内容
<!-- /OVERRIDE:context_limits -->
```

---

## Step 1.3: PROJECT-STATE.md

### 设计原理

`PROJECT-STATE.md` 是项目状态的平台无关单一事实来源（D-4）。当前 `CLAUDE.md` 混合了两类内容：


| 内容                | 性质            | 去向                                   |
| ----------------- | ------------- | ------------------------------------ |
| §项目信息、§项目状态、§全局约定 | 项目元数据（平台无关）   | → PROJECT-STATE.md                   |
| §执行环境             | 技术栈检测结果（平台无关） | → PROJECT-STATE.md                   |
| §文档导航             | 框架路径引用（需适配）   | → PROJECT-STATE.md（用 .cataforge/ 路径） |
| §框架机制             | 运行时行为描述（需适配）  | → PROJECT-STATE.md（平台无关描述）           |
| 运行时: claude-code  | 平台专属字段        | → deploy 时由 profile.yaml 填入          |


### PROJECT-STATE.md 格式

```markdown
# {项目名}

## 项目信息

- 技术栈: {框架/语言/工具}
- 运行时: {platform}                ← deploy 时从 profile.yaml 读取填入
- 框架版本: pyproject.toml `[project].version`
- 语言定位: 中文框架
- 执行模式: standard
- 阶段配置: ...
- model 继承: ...

## 执行环境

{由 setup.py --emit-env-block 填入，与平台无关}

## 项目状态 (orchestrator专属写入区)

- 当前阶段: {阶段名}
- 上次完成: ...
- 下一步行动: ...
- 已完成阶段: []
- 当前Sprint: —
- 文档状态: ...
- Learnings Registry: ...

## 文档导航

- 导航索引: docs/NAV-INDEX.md
- 通用规则: .cataforge/rules/COMMON-RULES.md
- 子代理协议: .cataforge/rules/SUB-AGENT-PROTOCOLS.md
- 编排协议: .cataforge/agents/orchestrator/ORCHESTRATOR-PROTOCOLS.md
- 状态码Schema: .cataforge/schemas/agent-result.schema.json

## 全局约定

- 命名: {规范}
- Commit: {格式}
- ...

## 框架机制

- Agent编排: orchestrator 通过 agent-dispatch skill 激活子代理
- DEV阶段: orchestrator 通过 tdd-engine skill 编排三阶段子代理
- 运行时: 由 framework.json runtime.platform 决定（deploy 自动适配）
- 写权限: PROJECT-STATE.md 由 orchestrator 独占写入
- 统一配置: .cataforge/framework.json
```

### CLAUDE.md 生成规则

deploy 从 PROJECT-STATE.md 生成 CLAUDE.md 时：

1. 复制全部内容
2. `运行时: {platform}` → `运行时: claude-code`
3. 路径保持 `.cataforge/`（Claude Code 可直接访问）
4. 追加 Claude Code 专属提示（如 `Agent tool` 用法简述，可选）

其他平台按需生成各自的指令文件（如 Cursor 生成 `.cursor/rules/*.mdc`）。

### orchestrator 行为变更

Phase 2 之后，orchestrator 写入目标从 `CLAUDE.md` 改为 `.cataforge/PROJECT-STATE.md`。deploy 负责同步到 `CLAUDE.md`。

同步时机：

- **手动**: `python .cataforge/scripts/framework/deploy.py`
- **自动（推荐）**: SessionStart hook 在会话启动时调用 deploy，确保 CLAUDE.md 与 PROJECT-STATE.md 同步

---

## Step 1.4: 规范 hooks.yaml

### 设计原理

v1 方案使用 `.claude/settings.json` 作为 Hook 的规范源，但该文件是 Claude Code 平台专属配置。根据 D-1（源定义在 `.cataforge/`），引入平台无关的 `hooks.yaml` 作为 Hook 源定义。

### 新增：`.cataforge/hooks/hooks.yaml`

```yaml
# CataForge Hook 规范定义（平台无关）
# deploy 读取此文件 + 平台 profile 的 event_map/matcher_map 生成平台配置

hooks:
  PreToolUse:
    - matcher_capability: shell_exec
      script: guard_dangerous.py
      type: block               # block = 可阻止工具执行
      description: "危险命令拦截"
      safety_critical: true     # 不可降级为框架内嵌
    - matcher_capability: agent_dispatch
      script: log_agent_dispatch.py
      type: observe             # observe = 仅观察，不阻止
      description: "子代理调度审计"

  PostToolUse:
    - matcher_capability: agent_dispatch
      script: validate_agent_result.py
      type: observe
      description: "子代理返回值验证"
    - matcher_capability: file_edit
      script: lint_format.py
      type: observe
      description: "文件编辑后自动格式化"
    - matcher_capability: user_question
      script: detect_correction.py
      type: observe
      description: "用户纠正信号捕获"

  Stop:
    - script: notify_done.py
      type: observe
      description: "会话结束通知"

  Notification:
    - script: notify_permission.py
      type: observe
      description: "权限请求通知"

  SessionStart:
    - script: session_context.py
      type: observe
      description: "会话初始化 + deploy 同步"

# 退化策略模板（当平台不支持某事件时的替代行为）
degradation_templates:
  guard_dangerous:
    strategy: rules_injection       # 注入到规则文件
    content: |
      SAFETY RULES (auto-generated — platform lacks PreToolUse hook):
      - NEVER run rm -rf, DROP TABLE, or other destructive commands without explicit user confirmation
      - NEVER modify files outside the project directory

  validate_agent_result:
    strategy: prompt_checklist      # 嵌入 dispatch prompt
    content: |
      === 返回值自检 ===
      返回前请确认:
      - [ ] 包含 <agent-result> 标签
      - [ ] status 为有效枚举值
      - [ ] outputs 列出所有产出文件路径

  detect_correction:
    strategy: skip                  # 安全跳过
    reason: "纠正学习为非关键功能"

  notify_permission:
    strategy: skip
    reason: "通知为非关键功能"

  log_agent_dispatch:
    strategy: prompt_instruction    # 在 prompt 中要求手动调用 logger
    content: |
      调度完成后，请运行:
      python .cataforge/scripts/framework/event_logger.py --event agent_dispatch --data '{...}'
```

---

## Step 1.5: runtime 工具层

runtime 包仅包含**真正有运行时价值的可执行工具**（D-7），不定义空壳抽象接口。

### 新增：`.cataforge/runtime/__init__.py`

```python
"""CataForge Cross-Platform Runtime — 可执行工具层。

提供:
- profile_loader: 加载平台 profile 和 tool_map
- template_renderer: 基础模板 + override 合并
- result_parser: Agent 返回值容错解析
- frontmatter_translator: AGENT.md 能力标识符翻译
- hook_bridge: Hook 配置翻译与退化计算
- deploy: 部署编排
"""
```

### 新增：`.cataforge/runtime/types.py`

```python
"""平台无关的数据类型定义。"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum


class AgentStatus(Enum):
    COMPLETED = "completed"
    NEEDS_INPUT = "needs_input"
    BLOCKED = "blocked"
    APPROVED = "approved"
    APPROVED_WITH_NOTES = "approved_with_notes"
    NEEDS_REVISION = "needs_revision"
    ROLLED_BACK = "rolled-back"


@dataclass
class DispatchRequest:
    agent_id: str
    task: str
    task_type: str
    input_docs: list[str]
    expected_output: str
    phase: str
    project_name: str
    background: bool = False
    max_turns: int | None = None
    review_path: str | None = None
    answers: dict | None = None
    intermediate_outputs: list[str] | None = None
    resume_guidance: str | None = None
    change_analysis: str | None = None


@dataclass
class AgentResult:
    status: AgentStatus
    outputs: list[str]
    summary: str
    questions: list[dict] | None = None
    completed_steps: str | None = None
    resume_guidance: str | None = None


CAPABILITY_IDS = [
    "file_read", "file_write", "file_edit", "file_glob", "file_grep",
    "shell_exec", "web_search", "web_fetch", "user_question", "agent_dispatch",
]
```

### 新增：`.cataforge/runtime/profile_loader.py`

```python
"""平台 profile 加载与工具名解析。

从 .cataforge/platforms/{platform_id}/profile.yaml 加载配置。
是工具名映射的单一事实来源（消除 v1 方案中 tool_map.yaml + hook 内联的双源问题）。
"""
from __future__ import annotations
import json
import os
from pathlib import Path

import yaml


_PLATFORMS_DIR = Path(__file__).resolve().parent.parent / "platforms"
_FRAMEWORK_JSON = Path(__file__).resolve().parent.parent / "framework.json"


def detect_platform() -> str:
    """从 framework.json 读取 runtime.platform，缺省 claude-code。"""
    try:
        with open(_FRAMEWORK_JSON, "r", encoding="utf-8") as f:
            config = json.load(f)
        return config.get("runtime", {}).get("platform", "claude-code")
    except (OSError, json.JSONDecodeError):
        return "claude-code"


def load_profile(platform_id: str | None = None) -> dict:
    """加载指定平台的 profile.yaml。"""
    pid = platform_id or detect_platform()
    path = _PLATFORMS_DIR / pid / "profile.yaml"
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_tool_map(platform_id: str | None = None) -> dict[str, str | None]:
    """获取能力标识符 → 平台原生工具名映射。"""
    profile = load_profile(platform_id)
    return profile.get("tool_map", {})


def resolve_tool_name(capability: str, platform_id: str | None = None) -> str | None:
    """将单个能力标识符翻译为平台工具名。None 表示不支持。"""
    return get_tool_map(platform_id).get(capability)


def resolve_tools_list(capabilities: list[str], platform_id: str | None = None) -> list[str]:
    """批量翻译，跳过不支持的能力。"""
    tool_map = get_tool_map(platform_id)
    return [name for cap in capabilities if (name := tool_map.get(cap)) is not None]


def get_dispatch_info(platform_id: str | None = None) -> dict:
    """获取调度工具信息。"""
    profile = load_profile(platform_id)
    return profile.get("dispatch", {})


def get_hook_degradation(platform_id: str | None = None) -> dict[str, str]:
    """获取 Hook 退化配置。"""
    profile = load_profile(platform_id)
    return profile.get("hooks", {}).get("degradation", {})
```

### 新增：`.cataforge/runtime/template_renderer.py`

```python
"""模板 Override 渲染引擎。

实现 D-2 的继承覆盖策略:
1. 读取基础模板（含 OVERRIDE 标记）
2. 读取平台 override 文件（如果存在）
3. 用 override 段落替换基础模板中的对应段落
"""
from __future__ import annotations
import os
import re
from pathlib import Path

_CATAFORGE_DIR = Path(__file__).resolve().parent.parent

_OVERRIDE_PATTERN = re.compile(
    r"<!-- OVERRIDE:(\w+) -->\n(.*?)<!-- /OVERRIDE:\1 -->",
    re.DOTALL,
)


def render_template(
    template_rel_path: str,
    platform_id: str,
) -> str:
    """渲染模板：base + platform override。

    Args:
        template_rel_path: 相对于 .cataforge/ 的模板路径
            例: "skills/agent-dispatch/templates/dispatch-prompt.md"
        platform_id: 平台标识

    Returns:
        合并后的模板文本。
    """
    base_path = _CATAFORGE_DIR / template_rel_path
    base_content = base_path.read_text(encoding="utf-8")

    override_path = (
        _CATAFORGE_DIR / "platforms" / platform_id / "overrides"
        / Path(template_rel_path).name
    )

    if not override_path.is_file():
        return _strip_override_markers(base_content)

    override_content = override_path.read_text(encoding="utf-8")
    overrides = _parse_overrides(override_content)

    def replacer(match: re.Match) -> str:
        name = match.group(1)
        if name in overrides:
            return overrides[name]
        return match.group(2)  # 保留默认内容

    merged = _OVERRIDE_PATTERN.sub(replacer, base_content)
    return merged


def list_override_points(template_rel_path: str) -> list[str]:
    """列出模板中所有 OVERRIDE 标记点名。"""
    base_path = _CATAFORGE_DIR / template_rel_path
    content = base_path.read_text(encoding="utf-8")
    return [m.group(1) for m in _OVERRIDE_PATTERN.finditer(content)]


def _parse_overrides(content: str) -> dict[str, str]:
    """从 override 文件中提取各段落内容。"""
    return {m.group(1): m.group(2) for m in _OVERRIDE_PATTERN.finditer(content)}


def _strip_override_markers(content: str) -> str:
    """移除 OVERRIDE 标记，保留默认内容。"""
    return _OVERRIDE_PATTERN.sub(r"\2", content)
```

### 新增：`.cataforge/runtime/frontmatter_translator.py`

```python
"""AGENT.md frontmatter 能力标识符翻译。

源 AGENT.md 使用能力标识符（file_read, file_edit 等）。
deploy 时翻译为平台原生工具名（Read, StrReplace 等）。
"""
from __future__ import annotations
import re
from .profile_loader import resolve_tools_list, get_tool_map


def translate_agent_md(content: str, platform_id: str) -> str:
    """翻译 AGENT.md 的 tools 和 disallowedTools 字段。

    Args:
        content: AGENT.md 全文
        platform_id: 目标平台

    Returns:
        翻译后的 AGENT.md 全文（仅 frontmatter 变更）。
    """
    tool_map = get_tool_map(platform_id)

    def translate_field(match: re.Match) -> str:
        field_name = match.group(1)  # "tools" 或 "disallowedTools"
        caps_str = match.group(2)
        caps = [c.strip() for c in caps_str.split(",") if c.strip()]

        native_names = []
        for cap in caps:
            name = tool_map.get(cap)
            if name is not None:
                native_names.append(name)
            # null（不支持）→ 从列表中移除

        return f"{field_name}: {', '.join(native_names)}"

    content = re.sub(
        r"^(tools|disallowedTools):\s*(.+)$",
        translate_field,
        content,
        flags=re.MULTILINE,
    )
    return content
```

### 新增：`.cataforge/runtime/result_parser.py`

（内容与 v1 方案 Phase 1 Step 1.3 相同，此处省略。4 级容错解析器逻辑已验证，无需修改。）

---

## Step 1.6: deploy 脚本骨架

### 新增：`.cataforge/runtime/deploy.py`

```python
"""CataForge 平台部署编排。

从 .cataforge/（源定义）生成平台目录（部署产物）。
实现 D-1（源/产物分离）和 D-4（PROJECT-STATE.md → CLAUDE.md）。

用法:
  python .cataforge/scripts/framework/deploy.py [--platform claude-code|cursor|codex|opencode|all]
  python .cataforge/scripts/framework/deploy.py --check
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
    actions = []

    # 1. 部署 Agent 定义（能力标识符 → 原生工具名）
    if profile.get("agent_definition", {}).get("needs_deploy"):
        actions.extend(_deploy_agents(root, platform_id, profile))

    # 2. 部署 CLAUDE.md（从 PROJECT-STATE.md 生成）
    if profile.get("instruction_file", {}).get("reads_claude_md"):
        actions.extend(_deploy_claude_md(root, platform_id, profile))

    # 3. 部署 Hook 配置
    hooks_conf = profile.get("hooks", {})
    if hooks_conf.get("config_format"):
        actions.extend(_deploy_hooks(root, platform_id, profile))

    # 4. 部署额外指令文件（如 .cursor/rules/）
    for output in profile.get("instruction_file", {}).get("additional_outputs", []):
        actions.extend(_deploy_additional_output(root, platform_id, output))

    # 5. 部署规则目录链接
    actions.extend(_deploy_rules_link(root, platform_id, profile))

    return actions


def _deploy_agents(root: Path, platform_id: str, profile: dict) -> list[str]:
    """翻译并部署 AGENT.md 到平台目录。"""
    actions = []
    source_dir = root / ".cataforge" / "agents"
    scan_dirs = profile.get("agent_definition", {}).get("scan_dirs", [])

    if not scan_dirs:
        return actions

    target_dir = root / scan_dirs[0]  # 使用第一个扫描目录
    target_dir.mkdir(parents=True, exist_ok=True)

    for agent_name in os.listdir(source_dir):
        agent_src = source_dir / agent_name
        if not agent_src.is_dir():
            continue

        agent_dst = target_dir / agent_name
        agent_dst.mkdir(exist_ok=True)

        for md_file in agent_src.glob("*.md"):
            content = md_file.read_text(encoding="utf-8")
            translated = translate_agent_md(content, platform_id)
            (agent_dst / md_file.name).write_text(translated, encoding="utf-8")
            actions.append(f"agents/{agent_name}/{md_file.name} → {target_dir.name}/")

    return actions


def _deploy_claude_md(root: Path, platform_id: str, profile: dict) -> list[str]:
    """从 PROJECT-STATE.md 生成 CLAUDE.md。"""
    state_path = root / ".cataforge" / "PROJECT-STATE.md"
    claude_md_path = root / "CLAUDE.md"

    if not state_path.is_file():
        return ["SKIP: PROJECT-STATE.md 不存在"]

    content = state_path.read_text(encoding="utf-8")

    # 替换 {platform} 占位符
    display_name = profile.get("display_name", platform_id)
    content = content.replace("运行时: {platform}", f"运行时: {platform_id}")

    claude_md_path.write_text(content, encoding="utf-8")
    return [f"CLAUDE.md ← PROJECT-STATE.md (platform={platform_id})"]


def _deploy_hooks(root: Path, platform_id: str, profile: dict) -> list[str]:
    """从 hooks.yaml + profile 生成平台 Hook 配置。"""
    # 具体实现在 Phase 4 hook_bridge.py 完善
    return [f"hooks: 待 Phase 4 实现"]


def _deploy_additional_output(root: Path, platform_id: str, output: dict) -> list[str]:
    """部署额外指令文件（如 Cursor MDC rules）。"""
    # 具体实现在 Phase 3 各适配器中完善
    return [f"additional: {output.get('target', '?')} 待 Phase 3 实现"]


def _deploy_rules_link(root: Path, platform_id: str, profile: dict) -> list[str]:
    """为平台创建 rules 目录链接。"""
    scan_dirs = profile.get("agent_definition", {}).get("scan_dirs", [])
    if not scan_dirs:
        return []

    # 确定平台根目录（如 .claude/）
    platform_root = Path(scan_dirs[0]).parent
    target = root / platform_root / "rules"
    source = root / ".cataforge" / "rules"

    if not source.is_dir():
        return []

    return [_create_link(source, target)]


def _create_link(source: Path, target: Path) -> str:
    """创建目录链接（跨平台）。"""
    if target.exists() or target.is_symlink():
        if target.is_symlink():
            target.unlink()
        elif target.is_dir():
            shutil.rmtree(target)

    target.parent.mkdir(parents=True, exist_ok=True)

    if platform_mod.system() != "Windows":
        rel = os.path.relpath(source, target.parent)
        target.symlink_to(rel)
        return f"{target} → {source} (symlink)"

    try:
        import subprocess
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(target), str(source)],
            check=True, capture_output=True,
        )
        return f"{target} → {source} (junction)"
    except (subprocess.CalledProcessError, FileNotFoundError):
        shutil.copytree(source, target)
        return f"{target} ← {source} (copy)"
```

### 新增：`.cataforge/scripts/framework/deploy.py`（CLI 入口）

```python
"""CLI 入口: python .cataforge/scripts/framework/deploy.py"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from runtime.deploy import deploy, get_project_root


def main():
    parser = argparse.ArgumentParser(description="CataForge 平台部署")
    parser.add_argument(
        "--platform",
        choices=["claude-code", "cursor", "codex", "opencode", "all"],
        default=None,
        help="目标平台（默认从 framework.json 读取）",
    )
    parser.add_argument("--check", action="store_true", help="检查部署状态")
    args = parser.parse_args()

    # ... CLI 逻辑
```

---

## 验收标准


| #      | 标准                                             | 验证方式      |
| ------ | ---------------------------------------------- | --------- |
| AC-1.1 | 4 个平台的 profile.yaml 存在且格式合法                    | YAML lint |
| AC-1.2 | dispatch-prompt.md 含 5 个 OVERRIDE 标记点          | grep 验证   |
| AC-1.3 | template_renderer 能正确合并 base + cursor override | 单元测试      |
| AC-1.4 | PROJECT-STATE.md 格式定义完成                        | 文档审查      |
| AC-1.5 | hooks.yaml 定义了 8 个 Hook 及其退化模板                 | 文档审查      |
| AC-1.6 | profile_loader 能从 profile.yaml 解析 tool_map     | 单元测试      |
| AC-1.7 | frontmatter_translator 正确翻译能力标识符               | 单元测试      |
| AC-1.8 | deploy.py 骨架可运行（--help 不报错）                    | CLI 测试    |


---

## 风险项


| 风险                               | 影响            | 缓解                                                 |
| -------------------------------- | ------------- | -------------------------------------------------- |
| PyYAML 依赖                        | 部分环境无 yaml 模块 | profile_loader 提供 JSON fallback（`profile.json` 备选） |
| Override 标记被用户误修改                | 模板渲染失败        | template_renderer 对未匹配的 OVERRIDE 标记输出警告            |
| PROJECT-STATE.md 与 CLAUDE.md 不同步 | 状态不一致         | SessionStart hook 自动触发 deploy                      |


