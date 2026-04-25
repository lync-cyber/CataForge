---
name: workflow-framework-generator
description: |
  根据用户指定的工作流类型与目标AI IDE平台，生成一套完整的、可运行的CataForge风格智能体与Skill编程工作流框架。
  支持任意领域（软件开发、内容创作、电商运营、研究分析等），自动适配Claude Code / Cursor / CodeX / OpenCode的能力差异。
  当用户需要为新领域或新平台构建AI工作流时触发。
argument-hint: "<workflow_type: 如'公众号写作'> <target_ide: 如'Claude Code'> [--multi-agent] [--structured-output]"
suggested-tools: file_read, file_write, file_edit, file_glob, file_grep, shell_exec, web_search, user_question
depends: []
disable-model-invocation: false
user-invocable: true
---

# 工作流框架生成器 (workflow-framework-generator)

## 能力边界

- **能做**: 根据工作流类型+目标平台，生成完整的CataForge兼容框架（agents/skills/workflows/configs）
- **不做**: 执行生成的工作流、替代领域专家做业务决策、硬编码特定工作流逻辑

## 执行流程

本 Skill 按三个阶段执行：**解析 → 规划 → 生成**。每个阶段有明确的输入输出契约。

---

### Phase 1: 输入解析与需求澄清

#### 1.1 解析用户输入

从用户消息中提取以下字段：

```yaml
workflow_type: <string>        # 工作流类型 (必填)
target_ide: <string>           # 目标平台 (必填，枚举: claude-code | cursor | codex | opencode)
constraints:
  multi_agent: <bool>          # 是否需要多智能体协作 (默认: true)
  tool_calls: <bool>           # 是否需要工具调用 (默认: true)
  structured_output: <bool>    # 是否需要结构化产出 (默认: true)
  output_format: <string>      # 产出格式 (默认: markdown)
project_name: <string>         # 项目名称 (可选，默认从 workflow_type 派生)
output_dir: <string>           # 输出目录 (可选，默认: ./generated-frameworks/<project_name>)
```

#### 1.2 输入验证

- `target_ide` 必须是已知平台之一。若用户输入模糊（如"vscode"），映射到最接近的平台并确认
- `workflow_type` 为自由文本，但需确认其属于可识别的领域类别

#### 1.3 需求澄清（条件触发）

当以下条件满足时，**必须**向用户提出澄清问题（最多3个，遵循 CataForge MAX_QUESTIONS_PER_BATCH 约束）：

| 条件 | 澄清问题方向 |
|------|-------------|
| workflow_type 含糊（如仅"写作"） | 具体写作类型、目标平台/渠道、产出格式 |
| 领域不熟悉 | 核心业务流程、关键产出物、质量标准 |
| multi_agent 未指定 | 工作流复杂度是否需要多角色协作 |
| 涉及外部系统 | 需要集成的API/服务/数据源 |

澄清问题格式：
```
为了生成最适合的工作流框架，我需要确认以下信息：
1. [具体问题]
2. [具体问题]
3. [具体问题]
```

#### 1.4 领域调研增强（条件触发）

当用户需求涉及你不熟悉的领域知识时：

1. 读取 `references/domain-patterns.md` 查找是否有匹配的领域模式
2. 若无匹配，使用 web_search 检索该领域的标准工作流程和最佳实践
3. 将调研结果结构化为：关键角色、核心流程、产出物清单、质量标准
4. 将结构化结果融入后续的架构设计

---

### Phase 2: 架构规划

#### 2.1 加载平台能力矩阵

读取 `references/platform-capabilities.md`，提取目标平台的：
- 支持的工具映射（tool_map）
- 可用特性（features）
- 代理调度方式（dispatch）
- Hook 支持程度
- 降级策略需求

#### 2.2 设计 Agent 角色体系

基于工作流需求，设计 Agent 角色列表。每个 Agent 必须包含：

```yaml
agent_id: <kebab-case>
name: <display_name>
role: <一句话角色定义>
responsibilities:
  - <职责1>
  - <职责2>
capabilities_needed:    # 使用 CataForge 能力标识符
  - file_read
  - file_write
  - shell_exec
interaction_pattern: <orchestrated | autonomous | reactive>
upstream_agents: [<agent_id>]     # 上游依赖
downstream_agents: [<agent_id>]   # 下游消费
```

**设计原则**：
- 每个 Agent 有且仅有一个核心职责（单一职责原则）
- Agent 之间通过文件系统传递状态，不依赖共享内存
- 至少包含一个 orchestrator 角色（当 multi_agent=true 时）
- 总 Agent 数量控制在 3-10 个（避免过度设计）

**单代理降级**：当 `multi_agent=false` 或目标平台不支持 agent_dispatch 时：
- 将所有角色合并为单一 Agent
- 使用 Skill 模块化拆分不同职责
- 工作流编排退化为 prompt 级顺序执行

#### 2.3 设计 Skill 模块

从 Agent 职责中提取可复用的能力单元：

```yaml
skill_id: <kebab-case>
name: <display_name>
type: instructional | executable | hybrid
description: <一句话描述>
input: <输入描述>
output: <输出描述>
used_by: [<agent_id>]
depends: [<skill_id>]
suggested-tools: [<capability_id>]   # 注意短横线，非下划线 — SkillLoader (loader.py:231) 仅识别带短横线的键名
```

**提取规则**：
- 跨 Agent 复用的逻辑 → 独立 Skill
- 可独立测试的处理逻辑 → 独立 Skill
- 特定于单一 Agent 且不复用 → 保留在 Agent 指令中
- 不创建仅被一个 Agent 使用且逻辑简单的 Skill

#### 2.4 设计 Workflow 编排

定义工作流的阶段、依赖和状态流转：

```yaml
workflow_id: <kebab-case>
phases:
  - id: <phase_id>
    name: <phase_name>
    agent: <agent_id>
    skills: [<skill_id>]
    inputs: [<doc_path or previous_phase_output>]
    outputs: [<doc_path>]
    gate: <quality_gate_description>  # 可选
    next: <phase_id> | [<phase_id>]   # 支持分支
```

**编排原则**：
- 阶段间通过文件产出物传递状态
- 每个阶段有明确的输入/输出契约
- 关键阶段设置质量门禁（gate）
- 支持线性、分支、并行三种流转模式

#### 2.5 平台适配决策

根据平台能力矩阵，做出以下适配决策并记录理由：

| 决策点 | Claude Code | Cursor | CodeX | OpenCode |
|--------|------------|--------|-------|----------|
| 多代理调度 | Agent 原生 | Task 原生 | spawn_agent 异步 | task 同步 |
| Hook 机制 | JSON settings | hooks.json | hooks.json (受限) | JS/TS 插件 |
| 缺失工具降级 | — | web_fetch→shell curl | user_question→注释提示 | 按 profile 降级 |
| 代理配置格式 | YAML frontmatter | YAML frontmatter | TOML | YAML frontmatter |

对每个不支持的能力，选择降级策略：
- **替代实现**: 用可用工具组合实现等效功能
- **规则注入**: 将逻辑嵌入 Agent 指令中
- **跳过**: 标记为不可用并说明影响

---

### Phase 3: 框架生成

#### 3.1 生成目录结构

根据规划结果，生成以下目录结构：

```text
<output_dir>/
├── .cataforge/
│   ├── framework.json              # 框架主配置
│   ├── PROJECT-STATE.md            # 项目状态文档
│   ├── agents/                     # Agent 定义
│   │   ├── <agent-id>/
│   │   │   └── AGENT.md
│   │   └── ...
│   ├── skills/                     # Skill 模块
│   │   ├── <skill-id>/
│   │   │   └── SKILL.md
│   │   └── ...
│   ├── workflows/                  # 工作流定义
│   │   └── <workflow-id>.yaml
│   ├── hooks/                      # Hook 规范
│   │   └── hooks.yaml
│   ├── rules/                      # 通用规则
│   │   ├── COMMON-RULES.md
│   │   └── SUB-AGENT-PROTOCOLS.md
│   ├── platforms/                   # 平台适配
│   │   └── <target_ide>/
│   │       └── profile.yaml
│   └── schemas/                    # 数据模型
│       └── agent-result.schema.json
├── docs/                           # 工作产出目录（空，由 doc-gen 在生成首份文档时调用 `cataforge docs index` 创建 .doc-index.json）
└── README.md                       # 框架说明
```

#### 3.2 生成 Agent 定义

读取 `templates/agent.md.tmpl`，为每个 Agent 生成 AGENT.md。

**关键规则**：
- `tools` 字段使用 CataForge 能力标识符（如 `file_read`），不使用平台原生名称
- `skills` 字段引用 Phase 2.3 中设计的 Skill ID
- `allowed_paths` 根据 Agent 职责设置写入范围限制
- `maxTurns` 根据任务复杂度设置（简单任务: 30, 中等: 80, 复杂: 150）
- Agent 指令部分使用中文（与 CataForge 惯例一致），技术标识符使用英文

每个 AGENT.md 必须包含以下章节：
1. **Role** — 角色定义与身份说明
2. **Responsibilities** — 具体职责清单
3. **Input/Output Contract** — 输入输出契约
4. **Execution Protocol** — 执行协议（步骤、检查点）
5. **Anti-Patterns** — 禁止行为

#### 3.3 生成 Skill 定义

读取 `templates/skill.md.tmpl`，为每个 Skill 生成 SKILL.md。

每个 SKILL.md 必须包含：
1. YAML frontmatter（name, description, type, suggested-tools, depends）
2. 能力边界说明
3. 输入输出规范
4. 执行步骤
5. 质量检查点

#### 3.4 生成 Workflow 定义

读取 `templates/workflow.yaml.tmpl`，生成工作流编排文件。

workflow YAML 结构：
```yaml
id: <workflow_id>
name: <display_name>
description: <purpose>
version: "1.0"
phases:
  - id: <phase_id>
    agent: <agent_id>
    skills: [<skill_ids>]
    inputs:
      - type: user_input | file | previous_phase
        source: <path_or_phase_id>
    outputs:
      - type: file
        path: <output_path>
        format: <markdown | json | yaml>
    gate:
      type: review | automated | manual
      criteria: <description>
    transitions:
      on_success: <next_phase_id>
      on_revision: <current_phase_id>  # 自循环修订
      on_blocked: halt
```

#### 3.5 生成框架配置

**framework.json** — 读取 `templates/framework.json.tmpl`，填充：
- version: "1.0.0"
- runtime.platform: target_ide 的 platform_id
- constants: 根据工作流特性设置
- features: 根据 Skill 依赖启用

**hooks.yaml** — 读取 `templates/hooks.yaml.tmpl`，生成适用的 Hook 规范。仅生成目标平台支持的 Hook，不支持的标记降级策略。

**profile.yaml** — 读取 `templates/platform-profiles/<target_ide>.yaml.tmpl`，生成目标平台的能力映射。

**COMMON-RULES.md** — 生成工作流通用规则，包括：
- 文件命名规范
- Agent 间通信协议
- 质量标准
- 产出物格式要求

**SUB-AGENT-PROTOCOLS.md** — 生成子代理协议，包括：
- 返回值格式（agent-result XML 标签）
- 状态码定义
- 错误恢复流程

#### 3.6 生成 README.md

生成项目级 README，包含：
- 框架概述与设计目标
- 目录结构说明
- 快速开始指南（针对目标平台）
- Agent 与 Skill 清单
- 工作流阶段说明
- 平台限制与降级说明
- 扩展指南

---

### Phase 4: 输出验证

生成完成后，执行以下验证：

#### 4.1 结构完整性检查

运行 `scripts/validate_framework.py`，检查：

- [ ] 所有 Agent 的 AGENT.md 存在且 frontmatter 合法
- [ ] 所有 Skill 的 SKILL.md 存在且 frontmatter 合法
- [ ] Workflow 引用的 agent_id 和 skill_id 全部存在
- [ ] framework.json 结构合法
- [ ] profile.yaml 的 tool_map 覆盖所有使用到的能力标识符
- [ ] hooks.yaml 的 matcher_capability 在目标平台有映射或有降级策略
- [ ] 无未实现占位符（禁止出现待办标记或空壳逻辑）

#### 4.2 平台兼容性检查

- [ ] Agent tools 字段仅使用 CataForge 能力标识符（不含平台原生名称）
- [ ] 不使用目标平台不支持的特性（如 OpenCode 无 parallel_agents）
- [ ] 降级策略覆盖所有不支持的能力

#### 4.3 架构质量检查

- [ ] 无循环依赖（Agent 依赖图为 DAG）
- [ ] 无孤立 Skill（每个 Skill 至少被一个 Agent 引用）
- [ ] 无冗余 Agent（每个 Agent 的职责不与其他 Agent 重叠超过30%）
- [ ] Workflow 有且仅有一个入口阶段和至少一个终止阶段

---

## 设计决策输出

生成完成后，输出以下设计决策说明：

```markdown
## 设计决策记录

### 1. Agent 角色划分
- 为什么选择 N 个 Agent: [理由]
- 为什么 [agent_id] 独立而不合并: [理由]

### 2. Skill 提取策略
- 哪些逻辑提取为 Skill: [清单及理由]
- 哪些逻辑保留在 Agent 中: [清单及理由]

### 3. 工作流编排模式
- 选择 [线性/分支/并行] 的理由: [理由]
- 质量门禁设置在 [阶段] 的理由: [理由]

### 4. 平台适配
- 目标平台: [platform_id]
- 降级处理: [具体降级项及策略]
- 不可用能力: [清单及影响评估]
```

---

## 多平台同时生成

当用户请求为多个平台生成框架时：

1. 先生成平台无关的核心结构（agents/, skills/, workflows/）
2. 为每个目标平台生成独立的 `platforms/<platform_id>/profile.yaml`
3. 共享 framework.json 但 runtime.platform 设为首选平台
4. 在 README.md 中说明多平台切换方式

---

## 领域模式快速参考

以下是常见领域的Agent/Skill/Workflow模式，详见 `references/domain-patterns.md`：

| 领域 | 典型 Agent 角色 | 核心 Skill | 工作流模式 |
|------|----------------|-----------|-----------|
| 软件开发 | orchestrator, architect, implementer, reviewer, tester | tdd-engine, code-review, doc-gen | 线性+门禁 |
| 内容创作 | planner, writer, editor, publisher | content-gen, seo-optimize, format-convert | 线性+修订循环 |
| 电商运营 | analyst, copywriter, campaign-manager, data-analyst | market-research, copy-gen, data-viz | 并行+汇总 |
| 研究分析 | researcher, analyst, synthesizer, reporter | literature-search, data-analysis, report-gen | 迭代深化 |

---

## 扩展机制

生成的框架支持以下扩展方式：

1. **新增 Agent**: 在 `agents/` 下创建新目录和 AGENT.md
2. **新增 Skill**: 在 `skills/` 下创建新目录和 SKILL.md
3. **新增 Workflow**: 在 `workflows/` 下创建新 YAML 文件
4. **新增平台**: 在 `platforms/` 下创建新目录和 profile.yaml
5. **自定义 Hook**: 在 `hooks/hooks.yaml` 中添加新规则

每种扩展均不需要修改已有文件（开闭原则）。

---

## 注意事项

- 生成的框架使用 CataForge 能力标识符，部署时由 deployer 自动翻译为平台原生名称
- Agent 指令内容使用中文（与 CataForge 项目惯例一致），技术标识符和配置键使用英文
- 生成的文件不包含任何未实现占位符，每个文件都是完整可用的
- 每个生成的文件都是完整可用的，不依赖后续手动补全
