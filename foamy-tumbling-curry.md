# CataForge 跨平台通用框架演进方案（v2 — 基于 2026 年实际平台能力）

## Context

CataForge 当前是 Claude Code 专用的 Agent/Skill 编排框架（13 Agent、22 Skill、7 阶段流程、3 种执行模式）。`agent-dispatch/SKILL.md:74` 明确声明"当前版本仅支持 claude-code runtime"。

**v1 方案的核心假设已被推翻**：2026 年的主流 AI 编程工具（Cursor、Codex CLI、OpenCode）**全部支持子代理调度、上下文隔离、项目指令注入和 Hooks 系统**。平台间差异从"有无"降级为"API 细节不同"。

本 v2 方案基于对四个平台的深度 API 研究，重新设计跨平台抽象层。

---

## 一、工具能力精确对比

### 1.1 子代理调度机制

| 维度 | Claude Code | Cursor | Codex CLI (OpenAI) | OpenCode |
|------|-------------|--------|---------------------|----------|
| **调度工具名** | `Agent` (v2.1.63 由 Task 重命名) | `Task` | `spawn_agent` + `send_input` + `resume_agent` + `wait_agent` + `close_agent` (5 工具协作) | `task` |
| **调度参数** | `subagent_type`, `description`, `prompt`, `model`, `run_in_background`, `isolation` | `subagent_type`, `prompt`, `model`("fast"/inherit), `max_turns` | `fork_context`(bool, 分叉父上下文) + 目标 agent name | `subagent_type`, `description`, `prompt` |
| **定义格式** | Markdown + YAML frontmatter (`.claude/agents/`) | Markdown + YAML frontmatter (`.cursor/agents/`) | **TOML** (`~/.codex/agents/`, `.codex/agents/`) | Markdown + YAML frontmatter (`.opencode/agents/`) **或** JSON (`opencode.json`) |
| **上下文隔离** | 独立 200K 窗口；子代理间完全隔离 | 独立上下文窗口；`agent_id` 可恢复 | 独立线程 (`ThreadManager`)；`fork_context=true` 可分叉父上下文 | 独立会话和上下文窗口 |
| **子代理可再嵌套** | 否（`disallowedTools: Agent`）；主线程 Agent 可通过 `Agent(worker,researcher)` 白名单限制 | 否（子代理不可调度） | 是（`max_depth` 控制，默认 1） | 否（子代理禁用 `task` 工具） |
| **后台执行** | `background: true` 或 `run_in_background` 参数 | `is_background: true` frontmatter | 天然支持（线程异步） | 不支持 |
| **批量调度** | Agent Teams（实验性，`TeamCreate`/`SendMessage`） | 并行工作流 | `spawn_agents_on_csv`（结构化输出 + schema 验证） | 不支持 |
| **兼容性扫描** | — | 扫描 `.claude/agents/`、`.codex/agents/` 作为 fallback | `project_doc_fallback_filenames` 可配置 `CLAUDE.md` | 扫描 `.claude/agents/`、`CLAUDE.md` 作为 fallback |

### 1.2 Agent 定义 frontmatter 字段对比

| 字段 | Claude Code | Cursor | Codex CLI | OpenCode |
|------|-------------|--------|-----------|----------|
| `name` | Yes (必需) | Yes (可选,默认文件名) | Yes (TOML `name`字段) | 文件名即标识 |
| `description` | Yes (必需) | Yes | Yes (TOML) | Yes |
| `model` | sonnet/opus/haiku/inherit/具体ID | inherit/fast/具体ID (ID暂不生效) | gpt-5.4等 (TOML) | provider/model-id 格式 |
| `tools` | 逗号分隔或列表；`Agent(x,y)` 白名单语法 | — | — | `tools: { write: false }` 对象格式 |
| `disallowedTools` | Yes | — | — | — |
| `allowed_paths` | Yes (CataForge 自定义) | — | — | — |
| `skills` | Yes (启动时注入) | — | `[[skills.config]]` (TOML) | — |
| `maxTurns` | Yes | — (通过 Task tool `max_turns` 参数) | — | Yes |
| `hooks` | Yes (每 Agent 独立 Hook) | — | — | — |
| `memory` | user/project/local | — | — | — |
| `background` | Yes | `is_background` | 天然异步 | — |
| `readonly` | — | Yes | — | — |
| `sandbox_mode` | — | — | read-only/workspace-write/full | — |
| `permission` | — | — | — | 14 类细粒度权限 |
| `permissionMode` | default/acceptEdits/auto/dontAsk/bypassPermissions/plan | — | — | — |
| `effort` | low/medium/high/max | — | `model_reasoning_effort` (TOML) | — |
| `isolation` | worktree | — | — | — |

### 1.3 Hook 系统对比

| 维度 | Claude Code | Cursor | Codex CLI | OpenCode |
|------|-------------|--------|-----------|----------|
| **配置文件** | `settings.json` | `.cursor/hooks.json` | `.codex/hooks.json` | 插件系统（JS/TS 模块） |
| **事件数量** | **26** 种 | **15+** 种 | **5** 种（WIP） | 插件 API（event emitter） |
| **Hook 类型** | command/http/prompt/agent | command/prompt | command | JS 模块 |
| **关键事件** | PreToolUse, PostToolUse, SubagentStart/Stop, SessionStart/End, TaskCreated/Completed, TeammateIdle, FileChanged, PreCompact, InstructionsLoaded | preToolUse, postToolUse, subagentStart/Stop, beforeShellExecution, afterFileEdit, sessionStart/End, stop, beforeSubmitPrompt | PreToolUse(仅Bash), PostToolUse(仅Bash), SessionStart, UserPromptSubmit, Stop | tool.execute.before/after, session 生命周期 |
| **退出码语义** | 0=继续, 2=阻止 | 0=继续, 2=阻止 | 0=继续, 2=阻止 | N/A（函数返回值） |
| **结构化输出** | `hookSpecificOutput` + `permissionDecision` | `permission: allow/deny` + `updated_input` | `permissionDecision: deny` | N/A |
| **环境变量** | `$CLAUDE_PROJECT_DIR` | `$CURSOR_PROJECT_DIR`, `$CLAUDE_PROJECT_DIR` | `$CODEX_HOME` | N/A |

### 1.4 项目指令/上下文注入

| 维度 | Claude Code | Cursor | Codex CLI | OpenCode |
|------|-------------|--------|-----------|----------|
| **指令文件** | `CLAUDE.md` | `.cursor/rules/` (MDC格式) + `.cursorrules` | `AGENTS.md` + `AGENTS.override.md` | `AGENTS.md`（兼容 `CLAUDE.md`） |
| **加载机制** | 每次会话自动加载 + `.claude/rules/` 自动注入 | 项目打开时加载 rules；Skills 按需 | 目录遍历 root→cwd 拼接；override 优先 | 目录遍历 + `opencode.json` `instructions` 数组 |
| **大小限制** | 无文档限制 | — | `project_doc_max_bytes: 32768` | — |
| **Override 机制** | 目录层级 | 优先级链 | `AGENTS.override.md` 同级覆盖 | 目录层级 |

### 1.5 关键差异总结（v2 修正）

原 v1 方案认为的"CRITICAL 阻塞"已大幅降级：

| v1 评估 | v2 实际情况 |
|---------|------------|
| "仅 Claude Code 有子代理" | **所有平台**均支持子代理调度+隔离 |
| "仅 Claude Code 有 Hooks" | Cursor 15+ 事件、Codex 5 事件（WIP）、OpenCode 插件系统 |
| "Cursor 无上下文隔离" | Cursor 子代理有独立上下文窗口 |
| "CodeX 仅异步执行" | Codex CLI 支持同步 TUI + 异步线程 |
| "无平台有项目指令" | 全部有：CLAUDE.md / AGENTS.md / .cursorrules |

**真正的差异点**在于 API 细节层面：
1. **调度工具名称和参数不同**（Agent vs Task vs spawn_agent vs task）
2. **Agent 定义格式不同**（Markdown YAML vs TOML）
3. **Hook 事件覆盖度不同**（26 vs 15+ vs 5 vs 插件）
4. **Codex 独有 ThreadManager 生命周期**（5 工具 vs 其他平台单一工具）
5. **权限模型实现不同**（allowed_paths vs readonly vs sandbox_mode vs 14 类权限）
6. **Agent 目录约定不同**（.claude/ vs .cursor/ vs .codex/ vs .opencode/）

---

## 二、问题清单（v2 — 基于实际差异重新评估）

### HIGH — 需要适配层

| # | 问题 | 位置 | 实际差异 | 适配策略 |
|---|------|------|---------|---------|
| H-1 | **Agent 定义格式差异** | 所有 `.claude/agents/*/AGENT.md` | Claude Code/Cursor/OpenCode 用 Markdown YAML；Codex 用 TOML | 以 Markdown YAML 为规范格式（3/4 平台原生支持）；Codex 适配器做格式转换 |
| H-2 | **调度工具 API 差异** | `agent-dispatch/SKILL.md:38-44`, `tdd-engine/SKILL.md:22-26` | 工具名、参数名、返回格式各不相同 | 统一 `DispatchRequest` → 各适配器翻译为平台 API |
| H-3 | **CataForge 自定义 frontmatter 字段** | 所有 AGENT.md 的 `allowed_paths`, `skills` (列表注入), `disallowedTools` | 这些是 CataForge 框架层概念，非平台原生 | 保留为框架层元数据，由框架运行时解释执行（不依赖平台 enforce） |
| H-4 | **Hook 事件覆盖度差异** | `.claude/settings.json:56-138` | Claude Code 26 事件 vs Codex 5 事件（仅 Bash） | 按功能分类：Safety/Audit/Format/Learning → 核心功能用 PreToolUse/PostToolUse（全平台有），高级功能 graceful degrade |
| H-5 | **项目指令文件差异** | `CLAUDE.md` | 文件名和加载方式不同 | 生成平台对应文件：CLAUDE.md / AGENTS.md / .cursorrules + 共享内容源 |

### MEDIUM — 需要映射但不阻塞

| # | 问题 | 位置 | 适配策略 |
|---|------|------|---------|
| M-1 | **工具名称硬编码** | 所有 AGENT.md `tools:` 字段 | 工具能力映射表（file_read→Read/Shell cat 等），已有方案 |
| M-2 | **Codex ThreadManager 生命周期** | Codex 独有 5 工具 | Codex 适配器将 dispatch→spawn_agent, 结果收集→wait_agent 封装为统一接口 |
| M-3 | **权限模型差异** | `allowed_paths` vs `sandbox_mode` vs `permission` 14 类 | 翻译为各平台原生权限（不自建权限引擎） |
| M-4 | **Agent 目录约定** | `.claude/agents/` | 多路径扫描或符号链接；Cursor/OpenCode 已原生扫描 `.claude/agents/` |

### LOW — 微调级别

| # | 问题 | 位置 | 说明 |
|---|------|------|------|
| L-1 | `model: inherit` 语义差异 | 各 AGENT.md | 全平台支持 inherit，但 Codex 默认继承、OpenCode 需显式 `provider/model-id` |
| L-2 | `maxTurns` 支持差异 | 各 AGENT.md | Claude Code/OpenCode 原生支持；Cursor 通过 Task 参数；Codex 用超时 |
| L-3 | 后台执行支持差异 | `background` 字段 | Claude Code/Cursor 支持；Codex 天然异步；OpenCode 不支持 |

### 架构异味（保留自 v1，仍然适用）

| 异味 | 建议 |
|------|------|
| 运行时身份分散在文本中 | `framework.json` 添加 `runtime.platform` |
| 调度机制与编排逻辑混合（tdd-engine） | 拆分编排序列 vs 平台调度模板 |
| Hook 按触发器分类而非功能 | 按 Safety/Audit/Format/Learning 重新分类 |

---

## 三、通用框架抽象设计（v2 — 利用共性而非补偿差异）

### 设计原则变化

v1 思路："其他平台缺少能力 → 需要补偿/模拟"
v2 思路："所有平台都有核心能力 → 抽象共性 API → 适配器只做格式翻译"

### 分层架构

```
┌────────────────────────────────────────────────────────┐
│  Orchestration Layer (平台无关 — 现有 CataForge 核心)    │
│  ┌─────────────┐ ┌──────────┐ ┌────────────────────┐   │
│  │ Protocols   │ │ Skills   │ │ Templates          │   │
│  │ (ORCH-PROTO,│ │ (22个    │ │ (doc-gen 模板,     │   │
│  │  SUB-AGENT) │ │  工作流) │ │  dispatch-prompt)  │   │
│  └─────────────┘ └──────────┘ └────────────────────┘   │
├────────────────────────────────────────────────────────┤
│  Abstraction Layer (薄接口 — 仅抽象真正不同的部分)       │
│  ┌──────────────────┐ ┌───────────────────────────┐    │
│  │ AgentDispatcher   │ │ AgentDefinitionAdapter    │    │
│  │ (调度+结果收集)   │ │ (YAML↔TOML 格式转换)     │    │
│  └──────────────────┘ └───────────────────────────┘    │
│  ┌──────────────────┐ ┌───────────────────────────┐    │
│  │ HookBridge       │ │ InstructionFileSync       │    │
│  │ (事件名映射)     │ │ (CLAUDE.md↔AGENTS.md)     │    │
│  └──────────────────┘ └───────────────────────────┘    │
│  ┌──────────────────┐                                  │
│  │ ToolNameResolver │                                  │
│  │ (能力→工具名)    │                                  │
│  └──────────────────┘                                  │
├────────────────────────────────────────────────────────┤
│  Platform Adapters (格式翻译层)                          │
│  ┌───────────┐ ┌────────┐ ┌────────┐ ┌──────────┐     │
│  │Claude Code│ │Cursor  │ │Codex   │ │OpenCode  │     │
│  └───────────┘ └────────┘ └────────┘ └──────────┘     │
├────────────────────────────────────────────────────────┤
│  Infrastructure (已跨平台 — 无需修改)                    │
│  event_logger.py, load_section.py, doc_check.py, ...   │
└────────────────────────────────────────────────────────┘
```

### 核心接口定义

#### 1. AgentDispatcher — 调度抽象（v2：所有平台都支持调度）

```python
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
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
    """平台无关的调度请求 — 由 orchestrator 构建"""
    agent_id: str              # "architect", "implementer" 等
    task: str                  # 任务描述
    task_type: str             # new_creation | revision | continuation | ...
    input_docs: list[str]      # 文件路径
    expected_output: str
    phase: str
    project_name: str
    # 运行时选项（框架层，非平台层）
    background: bool = False
    max_turns: int | None = None
    # 条件字段
    review_path: str | None = None
    answers: dict | None = None
    intermediate_outputs: list[str] | None = None
    resume_guidance: str | None = None
    change_analysis: str | None = None

@dataclass
class AgentResult:
    """平台无关的返回值 — 由适配器从平台输出解析"""
    status: AgentStatus
    outputs: list[str]
    summary: str
    questions: list[dict] | None = None
    completed_steps: str | None = None
    resume_guidance: str | None = None

class AgentDispatcher(ABC):
    @abstractmethod
    def dispatch(self, request: DispatchRequest) -> AgentResult:
        """分派任务给子代理。适配器负责：
        1. 构建平台专属 prompt（使用 PromptBuilder）
        2. 调用平台调度工具（Agent/Task/spawn_agent/task）
        3. 解析返回值为 AgentResult（使用 ResultParser）
        """
        ...

    @abstractmethod
    def platform_id(self) -> str:
        """返回平台标识: claude-code | cursor | codex | opencode"""
        ...
```

**为什么比 v1 更简单**：不再需要 `capabilities()` 方法检测"是否支持隔离/交互"——所有平台都支持。

#### 2. AgentDefinitionAdapter — 定义格式转换

```python
@dataclass
class AgentDefinition:
    """统一的 Agent 定义（从 YAML/TOML 解析后的中间表示）"""
    name: str
    description: str
    system_prompt: str         # Markdown body
    model: str = "inherit"
    max_turns: int | None = None
    background: bool = False
    # CataForge 框架层元数据（非平台字段）
    tools: list[str] = field(default_factory=list)
    disallowed_tools: list[str] = field(default_factory=list)
    allowed_paths: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    # 平台专属字段（透传）
    platform_extras: dict = field(default_factory=dict)

class AgentDefinitionAdapter(ABC):
    @abstractmethod
    def load(self, agent_id: str) -> AgentDefinition:
        """从平台原生格式加载 Agent 定义"""
        ...

    @abstractmethod
    def save(self, definition: AgentDefinition) -> None:
        """写出为平台原生格式"""
        ...

    @abstractmethod
    def sync_from_canonical(self, canonical_dir: str) -> None:
        """从规范目录（.claude/agents/）同步到平台目录
        Claude Code: no-op（已是规范目录）
        Cursor: .claude/agents/ → .cursor/agents/（格式相同）
        Codex: .claude/agents/ Markdown → .codex/agents/ TOML
        OpenCode: .claude/agents/ → .opencode/agents/（格式相同）
        """
        ...
```

**关键设计决策**：以 Markdown YAML frontmatter 为**规范格式**（canonical format），因为 3/4 平台原生支持。Codex 适配器负责 YAML→TOML 转换。Cursor 和 OpenCode 已原生扫描 `.claude/agents/`，可能甚至无需复制。

#### 3. HookBridge — Hook 事件映射

```python
@dataclass
class HookEvent:
    """平台无关的 Hook 事件"""
    category: str     # safety | audit | format | learning | notification
    timing: str       # pre_dispatch | post_dispatch | pre_tool | post_tool | session_start | session_end
    data: dict        # 事件数据

class HookBridge(ABC):
    @abstractmethod
    def translate_config(self, cataforge_hooks: dict) -> dict:
        """将 CataForge Hook 配置翻译为平台格式。
        Claude Code: settings.json hooks（最丰富，基本透传）
        Cursor: .cursor/hooks.json（映射事件名）
        Codex: .codex/hooks.json（仅覆盖 5 事件，其余 degrade）
        OpenCode: 生成插件代码（JS/TS 模块）
        """
        ...

    @abstractmethod
    def get_supported_events(self) -> list[str]:
        """当前平台支持的事件列表，编排层据此 graceful degrade"""
        ...
```

**Hook 功能分类与平台覆盖矩阵**：

| 功能 | CataForge Hook | 最低要求事件 | Claude Code | Cursor | Codex | OpenCode |
|------|----------------|-------------|-------------|--------|-------|----------|
| 危险命令守卫 | guard_dangerous | PreToolUse:Bash | 26事件全覆盖 | preToolUse:Shell | PreToolUse:Bash | 插件 |
| 调度审计 | log_agent_dispatch | SubagentStart/PreToolUse:Agent | SubagentStart | subagentStart | 无直接等价(degrade) | 插件 |
| 结果验证 | validate_agent_result | PostToolUse:Agent | PostToolUse:Agent | postToolUse:Task | PostToolUse(WIP) | 插件 |
| 自动格式化 | lint_format | PostToolUse:Edit/Write | PostToolUse | afterFileEdit | 无(degrade) | 插件 |
| 纠正学习 | detect_correction | PostToolUse:AskUserQuestion | PostToolUse:AskUserQuestion | 无直接等价(degrade) | 无(degrade) | 插件 |
| 会话初始化 | session_context | SessionStart | SessionStart | sessionStart | SessionStart | 插件 |

**Degrade 策略**：不支持的事件 → 由框架在调度前后的 Python 逻辑中内嵌执行（不依赖平台 Hook）。

#### 4. InstructionFileSync — 指令文件同步

```python
class InstructionFileSync(ABC):
    @abstractmethod
    def sync(self, claude_md_path: str) -> None:
        """将 CLAUDE.md 内容同步到平台指令文件。
        Claude Code: no-op（CLAUDE.md 即原生指令文件）
        Cursor: 提取项目状态和规则 → 生成 .cursor/rules/ 文件
        Codex: 复制/转换 → AGENTS.md（Codex 已支持 fallback 读 CLAUDE.md）
        OpenCode: no-op（OpenCode 已原生读取 CLAUDE.md 作为 fallback）
        """
        ...
```

**重要发现**：Cursor 扫描 `.claude/agents/`，OpenCode 直接读取 `CLAUDE.md`，Codex 可配置 `project_doc_fallback_filenames: ["CLAUDE.md"]`。这意味着跨平台兼容的工作量远小于预期 — 很多情况下原生兼容。

#### 5. ToolNameResolver — 工具名映射

```python
# tool_map.yaml — 精简为实际需要映射的部分
# 注意：很多平台工具名几乎相同

claude-code:
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
  task_tracking: TaskCreate  # v2.1.63+ Task 工具族

cursor:
  file_read: Read        # Cursor hook 中为 "Read"
  file_write: Write
  file_edit: Write       # Cursor 合并了 edit/write
  file_glob: Read        # 通过文件读取
  file_grep: Read        # 通过搜索
  shell_exec: Shell
  web_search: null
  web_fetch: null
  user_question: null    # Chat 替代
  agent_dispatch: Task
  task_tracking: null

codex:
  file_read: shell       # 通过 shell cat
  file_write: apply_patch
  file_edit: apply_patch
  file_glob: shell       # 通过 shell find
  file_grep: shell       # 通过 shell grep
  shell_exec: shell
  web_search: web_search
  web_fetch: shell       # curl
  user_question: null    # 无（异步线程模式）
  agent_dispatch: spawn_agent
  task_tracking: null

opencode:
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
  task_tracking: todowrite
```

### 模块依赖关系

```
orchestrator (ORCHESTRATOR-PROTOCOLS.md)
  ├── AgentDispatcher.dispatch()        # 唯一调度入口
  ├── ResultParser.parse()              # 统一解析 <agent-result>
  ├── HookBridge.translate_config()     # 初始化时一次性生成
  └── InstructionFileSync.sync()        # 阶段切换时同步状态

AgentDispatcher (各平台实现)
  ├── AgentDefinitionAdapter.load()     # 读取 Agent 定义
  ├── PromptBuilder.build()             # 构建调度 prompt
  └── ToolNameResolver.resolve()        # 翻译工具名
```

---

## 四、适配器设计（v2 — 4 个平台）

### 4.1 Claude Code 适配器（身份适配，最小改动）

```python
class ClaudeCodeDispatcher(AgentDispatcher):
    def dispatch(self, request):
        prompt = self.prompt_builder.build(request)
        # 直接使用 Agent tool（现有行为不变）
        raw = Agent(subagent_type=request.agent_id,
                    description=f"Phase {request.phase}: ...",
                    prompt=prompt,
                    model=request.model or "inherit",
                    run_in_background=request.background)
        return self.result_parser.parse(raw)
```

- **Agent 定义**：`.claude/agents/` Markdown，原生格式，无需转换
- **Hooks**：`settings.json` 透传，全部 26 事件可用
- **指令文件**：`CLAUDE.md` 原生，无需同步
- **改动量**：近乎零 — 包装现有行为

### 4.2 Cursor 适配器

```python
class CursorDispatcher(AgentDispatcher):
    def dispatch(self, request):
        # Cursor 的 Task tool 参数与 Claude Code 的 Agent tool 非常相似
        prompt = self.prompt_builder.build(request)
        raw = Task(subagent_type=request.agent_id,
                   prompt=prompt,
                   max_turns=request.max_turns)
        return self.result_parser.parse(raw)
```

- **Agent 定义**：Cursor 原生扫描 `.claude/agents/`，大多数情况 zero-copy
  - 不兼容的 frontmatter 字段（`skills` 注入、`hooks` per-agent）由 CataForge 框架层处理
- **Hooks**：`.cursor/hooks.json` 映射事件名（如 `PreToolUse` → `preToolUse`）
  - detect_correction (AskUserQuestion) 无直接等价 → 框架层内嵌逻辑
- **指令文件**：`.cursor/rules/` 从 CLAUDE.md 提取静态规则生成
- **改动量**：适配器 + hook 映射 + rules 生成器

### 4.3 Codex CLI 适配器

```python
class CodexDispatcher(AgentDispatcher):
    def dispatch(self, request):
        prompt = self.prompt_builder.build(request)
        # Codex 使用 spawn_agent + wait_agent 两步调度
        thread_id = spawn_agent(
            agent=request.agent_id,
            fork_context=False,  # CataForge 子代理不需要父上下文
            prompt=prompt
        )
        result = wait_agent(thread_id)
        return self.result_parser.parse(result)
```

- **Agent 定义**：`.claude/agents/` Markdown → `.codex/agents/` TOML 自动转换
  ```
  YAML frontmatter → TOML 字段映射：
    name → name
    description → description
    model → model (需要翻译: "opus" → "gpt-5.4" 或保留 Anthropic 模型名)
    Markdown body → developer_instructions
    allowed_paths → (无直接等价，翻译为 sandbox writable_roots)
  ```
- **Hooks**：`.codex/hooks.json` 仅 5 事件 → guard_dangerous 和 session_context 可映射；其余由框架内嵌
- **指令文件**：配置 `project_doc_fallback_filenames: ["CLAUDE.md"]` 即可原生读取
- **改动量**：适配器 + YAML→TOML 转换器 + hook 子集映射

### 4.4 OpenCode 适配器

```python
class OpenCodeDispatcher(AgentDispatcher):
    def dispatch(self, request):
        prompt = self.prompt_builder.build(request)
        # OpenCode 的 task tool 参数结构几乎相同
        raw = task(subagent_type=request.agent_id,
                   description=f"Phase {request.phase}: ...",
                   prompt=prompt)
        return self.result_parser.parse(raw)
```

- **Agent 定义**：OpenCode 原生扫描 `.claude/agents/` 作为 fallback，zero-copy
  - OpenCode 独有的 `permission` 14 类字段可通过 `platform_extras` 透传
- **Hooks**：OpenCode 无原生 Hook → 生成 JS/TS 插件模块（或全部框架内嵌）
- **指令文件**：OpenCode 原生读取 `CLAUDE.md` 作为 fallback，无需额外处理
- **改动量**：适配器 + 可选插件生成

### 关键流程示例：TDD RED → GREEN（v2 对比）

| 步骤 | Claude Code | Cursor | Codex CLI | OpenCode |
|------|-------------|--------|-----------|----------|
| RED 调度 | `Agent(subagent_type="test-writer", ...)` | `Task(subagent_type="test-writer", ...)` | `spawn_agent("test-writer", ...)` → `wait_agent(tid)` | `task(subagent_type="test-writer", ...)` |
| RED 隔离 | 独立 200K 窗口 | 独立上下文窗口 | 独立线程 | 独立会话 |
| RED 结果 | `<agent-result>` XML | `<agent-result>` XML | `<agent-result>` XML | `<agent-result>` XML |
| GREEN 调度 | 同上，注入 test_files | 同上 | 同上 | 同上 |
| 差异 | 无 | `Task` 替代 `Agent` | 两步调度 | `task` 替代 `Agent` |

**核心发现**：TDD 引擎的编排逻辑在 v2 下**完全平台无关** — 唯一的差异是调度工具的名称和参数格式，由 `AgentDispatcher` 适配器处理。

---

## 五、演进路径（v2 — 大幅简化）

### 整体策略变化

v1："大规模重构 → 补偿平台缺失能力"
v2："薄翻译层 → 利用平台原生能力"

由于所有平台已支持核心能力，重构工作量大幅减少。

### Phase 1: 最小抽象提取（1-2 周）

**Step 1.1: 建立运行时包**
```
.claude/runtime/
  __init__.py
  interfaces.py          # AgentDispatcher, AgentDefinitionAdapter 等
  types.py               # DispatchRequest, AgentResult 等
  result_parser.py       # 从 agent-dispatch SKILL.md 提取的 XML 解析 + 4 级容错
  tool_map.yaml          # 工具能力映射
  adapters/
    __init__.py
    claude_code.py       # 身份适配器
    _registry.py         # 平台检测 + 适配器选择
```

**Step 1.2: framework.json 添加 runtime 配置**
```json
{
  "runtime": {
    "platform": "claude-code",
    "adapter": "adapters.claude_code"
  }
}
```

**Step 1.3: result_parser 提取**

将 `agent-dispatch/SKILL.md:46-60` 的自然语言容错逻辑转为 Python：
```python
def parse_agent_result(raw_output: str, doc_type: str = None) -> AgentResult:
    """4 级容错解析：
    1. 正常 <agent-result> XML
    2. 标签缺失 → Glob docs/ 推断
    3. 字段不完整 → 默认值
    4. maxTurns 截断 → git status 检查
    """
```

**Step 1.4: agent-dispatch SKILL.md 拆分**

当前 SKILL.md 中 `## claude-code 实现` 段落移入 Claude Code 适配器。保留平台无关的编排规范。

**不破坏现有功能**：Claude Code 适配器是当前行为的薄包装。

### Phase 2: 次要适配器（各 3-5 天）

**优先级排序**（基于兼容性成本从低到高）：

| 优先级 | 平台 | 理由 |
|--------|------|------|
| P0 | OpenCode | 与 Claude Code 最相似（Markdown agent、`CLAUDE.md` fallback、`task` tool）|
| P1 | Cursor | 次相似（Markdown agent、扫描 `.claude/agents/`、`Task` tool）|
| P2 | Codex CLI | 格式差异最大（TOML、ThreadManager 5 工具、WIP hooks）|

**Step 2.1: OpenCode 适配器**
- `task` tool 参数几乎相同
- Agent 定义：零拷贝（OpenCode 原生读 `.claude/agents/`）
- 指令文件：零配置（OpenCode 原生读 `CLAUDE.md`）
- Hooks：降级为框架内嵌（OpenCode 用插件系统）
- **预期工作量最小**

**Step 2.2: Cursor 适配器**
- `Task` tool 参数相似
- Agent 定义：Cursor 原生扫描 `.claude/agents/`
- hooks.json 事件名映射（camelCase vs PascalCase）
- `.cursor/rules/` 生成器（从 CLAUDE.md 提取规则）
- **预期中等工作量**

**Step 2.3: Codex 适配器**
- YAML→TOML 转换器
- spawn_agent + wait_agent 两步封装
- `project_doc_fallback_filenames: ["CLAUDE.md"]` 配置
- hooks.json 子集映射（5 事件）
- **预期最大工作量**

### Phase 3: 端到端验证

- OpenCode 上运行 agile-prototype 项目（最快验证路径）
- Cursor 上运行 agile-lite 项目
- Codex 上运行 TDD 引擎单任务（spawn_agent → wait_agent 循环）

### Phase 4: API 稳定化

- 锁定接口版本 `runtime_api_version: 1.0`
- 适配器合规测试套件
- Bootstrap 增加平台选择步骤

---

## 六、交付物总结

| 交付物 | 状态 |
|--------|------|
| 4 平台精确对比表 | 本文 §一 |
| 问题清单（v2 重新评估） | 本文 §二 |
| 通用架构设计（5 核心接口） | 本文 §三 |
| 4 平台适配器设计 | 本文 §四 |
| 分阶段重构路线图 | 本文 §五 |

### v1 → v2 关键变化总结

| 维度 | v1 | v2 |
|------|----|----|
| 核心假设 | 仅 Claude Code 有子代理/隔离/Hooks | 所有平台都有 |
| CRITICAL 问题数 | 3 | 0（全部降级为 HIGH/MEDIUM） |
| 接口数量 | 5（含 RuntimeCapabilities） | 5（去掉 capabilities，简化为格式翻译） |
| Cursor 适配复杂度 | 高（模拟隔离、补偿缺失） | 低（工具名映射 + hooks 事件名映射） |
| CodeX 适配复杂度 | 高（异步补偿、无交互） | 中（TOML 转换 + ThreadManager 封装） |
| 预计总工作量 | 大 | **减少约 60%** |
