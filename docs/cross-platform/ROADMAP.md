# CataForge 跨平台演进路线图 v2

> 基于 v1 方案审查反馈重构。核心变更：引入 Override 机制实现平台扩展性、
> 引入 PROJECT-STATE.md 作为平台无关状态源、先验证后建设的执行策略。

## 设计决策记录


| #   | 决策点         | 结论                                                        |
| --- | ----------- | --------------------------------------------------------- |
| D-1 | 源定义 vs 部署产物 | `.cataforge/` 为平台无关源定义；`.claude/`、`.cursor/` 等由 deploy 生成 |
| D-2 | Prompt 模板策略 | 基础模板 + 平台 override 片段（继承覆盖模式）                             |
| D-3 | Hook 退化策略   | 规范 hooks.yaml 为源定义 + 分级退化（native/degraded/unsupported）    |
| D-4 | 项目状态文件      | PROJECT-STATE.md 为单一事实来源；CLAUDE.md 由 deploy 生成            |
| D-5 | 能力标识符       | 源 AGENT.md 用能力标识符；deploy 翻译为平台原生工具名（零风险）                  |
| D-6 | 执行策略        | 先在 Cursor 上做最小验证，再做大规模重构                                  |
| D-7 | runtime 包定位 | 可执行工具层（resolver/parser/renderer），非空壳抽象接口                  |


## Phase 概览

```
Phase 0: 平台假设验证                    ████████░░░░░░░░░░░░  (3-5 天)
  └─ Cursor 上最小端到端验证，校正设计假设

Phase 1: Override 机制 + 核心抽象          ░░░░░░░░░░░░░░░░░░░░  (1-2 周)
  ├─ 1.1 平台配置体系 (profile.yaml + tool_map)
  ├─ 1.2 模板 Override 机制
  ├─ 1.3 PROJECT-STATE.md 引入
  ├─ 1.4 规范 hooks.yaml 引入
  ├─ 1.5 runtime 工具层 (resolver + parser + renderer)
  └─ 1.6 deploy 脚本骨架

Phase 2: 目录结构重构                    ░░░░░░░░░░░░░░░░░░░░  (3-5 天)
  ├─ 2.1 .claude/ → .cataforge/ 迁移
  ├─ 2.2 源 AGENT.md 能力标识符化
  ├─ 2.3 源 SKILL.md 平台无关化
  └─ 2.4 deploy 生成 .claude/ 部署产物

Phase 3: 平台适配器                      ░░░░░░░░░░░░░░░░░░░░  (2-3 周)
  ├─ 3.1 Claude Code 适配 (身份 deploy)
  ├─ 3.2 Cursor 适配 (P0, 已在 Phase 0 验证)
  ├─ 3.3 OpenCode 适配 (P1)
  └─ 3.4 Codex CLI 适配 (P2)

Phase 4: Hook 桥接层                     ░░░░░░░░░░░░░░░░░░░░  (1 周)
  ├─ 4.1 _hook_base.py 跨平台解析
  ├─ 4.2 Hook 脚本去硬编码
  └─ 4.3 退化策略具体实现

Phase 5: 端到端验证与 API 稳定化          ░░░░░░░░░░░░░░░░░░░░  (1 周)
  ├─ 5.1 测试套件
  ├─ 5.2 Bootstrap 平台选择
  └─ 5.3 API 版本锁定
```

## Override 机制总览

Override 是 CataForge 跨平台扩展性的核心。不同类型的文件使用不同粒度的 override 策略：


| Override 类型 | 适用对象                 | 机制                                            | 示例                                  |
| ----------- | -------------------- | --------------------------------------------- | ----------------------------------- |
| **段落级**     | Prompt 模板            | `<!-- OVERRIDE:name -->` 标记点，平台文件提供替换内容       | dispatch-prompt.md                  |
| **翻译级**     | AGENT.md frontmatter | 能力标识符 → 平台原生工具名（由 profile.yaml tool_map 驱动）   | `file_edit` → `StrReplace`          |
| **配置级**     | Hook 定义              | 规范 hooks.yaml + 平台 event_map/matcher_map      | PreToolUse → preToolUse             |
| **文件级**     | Rules                | 平台可新增专属规则文件                                   | `platforms/cursor/overrides/rules/` |
| **生成级**     | 指令文件                 | PROJECT-STATE.md → CLAUDE.md / .cursor/rules/ | deploy 渲染                           |


### 段落级 Override 流程

```
.cataforge/skills/agent-dispatch/templates/
├── dispatch-prompt.md              ← 基础模板，含 OVERRIDE 标记点
└── (override 内容在 platforms/ 下)

.cataforge/platforms/cursor/overrides/
├── dispatch-prompt.md              ← 仅覆盖标记段落
└── ...

deploy 时: base template + platform overrides → 最终 prompt
```

基础模板中使用成对标记划定可覆盖区域：

```markdown
<!-- OVERRIDE:dispatch_syntax -->
调度请求:
  agent_id: "{agent_id}"
<!-- /OVERRIDE:dispatch_syntax -->
```

平台 override 文件仅提供需要替换的段落（同名标记）。未提供的段落保留基础模板内容。

### 翻译级 Override 流程

```
源 AGENT.md (能力标识符)          profile.yaml (tool_map)
tools: file_read, file_edit  ──→  file_read: Read
                                  file_edit: StrReplace
                                        │
                              deploy 翻译 ▼
                         tools: Read, StrReplace
```

deploy 脚本读取源 AGENT.md 的能力标识符，通过 profile.yaml 的 tool_map 翻译为平台原生名，写入部署目录。**源文件始终使用能力标识符，部署产物始终使用原生名。**

## 目录结构

```
.cataforge/                              ← 框架核心（平台无关 single source of truth）
├── PROJECT-STATE.md                     ← 项目状态（D-4，替代 CLAUDE.md 的状态职能）
├── framework.json                       ← 框架配置
│
├── platforms/                           ← 平台配置与 override（D-2 核心）
│   ├── _schema.yaml                     ← 平台 profile 的 JSON Schema
│   ├── claude-code/
│   │   ├── profile.yaml                 ← 平台能力声明 + tool_map
│   │   └── overrides/                   ← 该平台的所有 override
│   │       ├── dispatch-prompt.md       ← 空或无（Claude Code 是基础模板默认目标）
│   │       └── rules/                   ← 平台专属规则（可选）
│   ├── cursor/
│   │   ├── profile.yaml
│   │   └── overrides/
│   │       ├── dispatch-prompt.md       ← 覆盖 §dispatch_syntax 和 §tool_usage
│   │       └── rules/
│   │           └── cursor-tool-conventions.md
│   ├── codex/
│   │   ├── profile.yaml
│   │   └── overrides/
│   │       ├── dispatch-prompt.md       ← 覆盖 §dispatch_syntax、§return_format、§context_limits
│   │       └── rules/
│   └── opencode/
│       ├── profile.yaml
│       └── overrides/
│           └── dispatch-prompt.md
│
├── runtime/                             ← 跨平台运行时工具层（D-7，可执行逻辑）
│   ├── __init__.py
│   ├── types.py                         ← AgentStatus, DispatchRequest, AgentResult
│   ├── result_parser.py                 ← 4 级容错解析器
│   ├── profile_loader.py                ← profile.yaml 加载 + tool_map 解析
│   ├── template_renderer.py             ← 基础模板 + override 合并
│   ├── frontmatter_translator.py        ← AGENT.md 能力标识符翻译
│   ├── hook_bridge.py                   ← Hook 翻译 + 退化计算
│   └── deploy.py                        ← 部署编排（生成平台目录）
│
├── agents/                              ← Agent 源定义（能力标识符）
│   ├── orchestrator/
│   │   ├── AGENT.md                     ← tools: file_read, file_write, ...
│   │   └── ORCHESTRATOR-PROTOCOLS.md
│   └── ... (13 个 Agent)
│
├── skills/                              ← Skill 源定义（平台无关）
│   ├── agent-dispatch/
│   │   ├── SKILL.md
│   │   └── templates/
│   │       └── dispatch-prompt.md       ← 基础模板（含 OVERRIDE 标记）
│   ├── tdd-engine/SKILL.md
│   └── ... (22 个 Skill)
│
├── rules/                               ← 通用规则（平台无关）
│   ├── COMMON-RULES.md
│   └── SUB-AGENT-PROTOCOLS.md
│
├── hooks/                               ← Hook 源定义
│   ├── hooks.yaml                       ← 规范 Hook 定义（D-3 源定义）
│   ├── _hook_base.py
│   └── *.py (8 个 Hook 脚本)
│
├── schemas/
├── scripts/
│   ├── framework/
│   │   ├── setup.py
│   │   ├── deploy.py                    ← CLI 入口: deploy 到平台目录
│   │   └── ...
│   └── docs/
└── integrations/

.claude/                                 ← Claude Code 部署产物（由 deploy 生成）
├── settings.json                        ← 唯一手动维护文件（包含 API key 等敏感配置）
├── agents/                              ← deploy 从 .cataforge/agents/ 翻译生成
│   └── (AGENT.md with native tool names)
└── rules/                               ← deploy 从 .cataforge/rules/ 复制/链接

.cursor/                                 ← Cursor 部署产物（由 deploy 生成）
├── hooks.json                           ← deploy 从 hooks.yaml 翻译生成
├── rules/                               ← deploy 从 rules/ + overrides 生成 MDC
└── agents/                              ← deploy 生成（可选，Cursor 也扫描 .claude/agents/）

CLAUDE.md                                ← deploy 从 PROJECT-STATE.md 生成（D-4）
```

## profile.yaml 结构

每个平台的 profile.yaml 是该平台所有配置的单一声明文件：

```yaml
platform_id: cursor
display_name: Cursor
version_tested: "0.48"

tool_map:
  file_read: Read
  file_write: Write
  file_edit: StrReplace
  file_glob: Glob
  file_grep: Grep
  shell_exec: Shell
  web_search: WebSearch
  web_fetch: WebFetch
  user_question: null        # 不支持 → 部署时从 tools 列表移除
  agent_dispatch: Task

agent_definition:
  format: yaml-frontmatter   # 与 Claude Code 相同
  scan_dirs:                  # 平台扫描 Agent 定义的目录
    - .claude/agents
    - .cursor/agents
  needs_deploy: true          # 需要翻译能力标识符后部署

instruction_file:
  reads_claude_md: true       # 原生读取 CLAUDE.md
  additional_outputs:         # deploy 额外生成的文件
    - target: .cursor/rules/
      format: mdc
      source: rules + overrides

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
    Notification: null          # 不支持
  matcher_map:
    Bash: Shell
    Agent: Task
    "Edit|Write": Write
    AskUserQuestion: null       # 不支持
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

## 依赖关系

```
Phase 0 (验证) ────► Phase 1 (Override机制) ────► Phase 2 (目录重构)
                                                       │
                                                       ├──► Phase 3 (适配器)
                                                       │       │
                                                       │       ├──► Phase 4 (Hook桥接)
                                                       │       │
                                                       └───────┴──► Phase 5 (验证)
```

Phase 0 产出的验证结论是 Phase 1 设计的输入。Phase 1 的 Override 机制是 Phase 2-5 的基础设施。

## 与 v1 方案的关键差异


| 维度            | v1 方案                     | v2 方案                       | 变更理由                     |
| ------------- | ------------------------- | --------------------------- | ------------------------ |
| 执行顺序          | 先迁移 87 文件，后验证             | 先在 Cursor 验证，后迁移            | 避免大规模重构后发现假设不成立          |
| Override 机制   | 无（文本通用化替代）                | 段落级标记 + 平台 override 文件      | 决策 D-2 要求                |
| 项目状态          | 继续用 CLAUDE.md             | 引入 PROJECT-STATE.md         | 决策 D-4 要求                |
| Hook 规范源      | .claude/settings.json     | .cataforge/hooks/hooks.yaml | 决策 D-1（源定义在 .cataforge/） |
| 能力标识符         | 直接替换 AGENT.md tools 字段    | 源用能力ID、deploy 翻译为原生名        | 消除 Claude Code 不识别的风险    |
| Dispatcher 接口 | ABC + NotImplementedError | PlatformProfile 声明式         | 避免空壳抽象                   |
| 工具名映射         | tool_map.yaml + hook 内联双源 | profile.yaml 单源             | 消除不一致风险                  |
| Deploy 自动化    | 仅手动 CLI                   | CLI + SessionStart hook 集成  | 决策 D-1 要求                |


## 跨会话执行指南

每个 Phase 对应独立文档（`phase-N-*.md`），包含设计细节、代码草案和验收标准。

会话恢复时：读取 ROADMAP.md → 确认上次完成的 Phase → 读取下一个 phase 文档 → 继续执行。

### 检查点命令

```bash
# Phase 0 完成检查: Cursor 上 agent 调度成功
# （手动验证，见 phase-0 文档）

# Phase 2 完成检查
python .cataforge/scripts/framework/deploy.py --check

# Phase 5 完成检查
python .cataforge/runtime/deploy.py --conformance --platform claude-code
```

