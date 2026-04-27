# 配置参考

> `.cataforge/` 目录下的配置文件清单与字段说明。所有文件以 **单一来源** 原则组织：平台相关的内容封装在 `platforms/<id>/profile.yaml`，其余文件平台无关。
>
> **适用版本**：v0.1.15。Schema 字段以 [`src/cataforge/core/`](../../src/cataforge/core/) 实际实现为权威。

## 目录

- [文件总览](#文件总览)
- [framework.json](#frameworkjson)
- [platforms/\<id\>/profile.yaml](#platformsidprofileyaml)
  - [context_injection 字段](#context_injection-字段)
- [hooks.yaml](#hooksyaml)
- [Agent 定义（AGENT.md）](#agent-定义agentmd)
- [Skill 定义（SKILL.md）](#skill-定义skillmd)
- [MCP 声明](#mcp-声明)

## 文件总览

| 文件 | 位置 | 作用 |
|------|------|------|
| `framework.json` | `.cataforge/framework.json` | 框架单一配置源 |
| `PROJECT-STATE.md` | `.cataforge/PROJECT-STATE.md` | 项目状态模板（用户可编辑） |
| `COMMON-RULES.md` | `.cataforge/rules/COMMON-RULES.md` | 通用行为规则 |
| `SUB-AGENT-PROTOCOLS.md` | `.cataforge/rules/SUB-AGENT-PROTOCOLS.md` | 子代理执行协议 |
| `ORCHESTRATOR-PROTOCOLS.md` | `.cataforge/agents/orchestrator/ORCHESTRATOR-PROTOCOLS.md` | 编排器核心协议 |
| `hooks.yaml` | `.cataforge/hooks/hooks.yaml` | 平台无关 hook 规范 |
| `profile.yaml` | `.cataforge/platforms/<id>/profile.yaml` | 各平台能力映射 |
| `AGENT.md` | `.cataforge/agents/<id>/AGENT.md` | Agent 定义（frontmatter + Markdown） |
| `SKILL.md` | `.cataforge/skills/<id>/SKILL.md` | Skill 定义 |
| `<id>.yaml` | `.cataforge/mcp/<id>.yaml` | MCP 服务声明 |

---

## framework.json

框架单一配置源。Schema 由 [`cataforge.schema.framework.FrameworkFile`](../../src/cataforge/schema/framework.py) 校验；upgrade 时的 preserve / overwrite 策略由 [`cataforge.core.scaffold._merge_framework_json`](../../src/cataforge/core/scaffold.py) 实现 —— 修改本节字段说明前请先核对那两处代码。

### 结构示例（与 `.cataforge/framework.json` 实际形态一致）

```json
{
  "version": "0.0.0-template",
  "runtime_api_version": "1.0",
  "runtime": {
    "platform": "claude-code"
  },
  "description": "CataForge 统一框架配置。upgrade.state 为本地升级状态（始终保留）；version、runtime_api_version、constants、features、migration_checks、upgrade.source 与 description 等其余字段均由 scaffold 管理，每次 upgrade apply 会被覆盖。runtime.platform 由用户在 setup 时选择，upgrade 期间保留。",
  "upgrade": {
    "source": {
      "type": "github",
      "repo": "lync-cyber/CataForge",
      "branch": "main",
      "token_env": "GITHUB_TOKEN"
    },
    "state": {
      "last_commit": "",
      "last_version": "",
      "last_upgrade_date": ""
    }
  },
  "constants": {
    "MAX_QUESTIONS_PER_BATCH": 3,
    "MANUAL_REVIEW_CHECKPOINTS": ["pre_dev", "pre_deploy"],
    "EVENT_LOG_PATH": "docs/EVENT-LOG.jsonl",
    "EVENT_LOG_SCHEMA": ".cataforge/schemas/event-log.schema.json",
    "DOC_SPLIT_THRESHOLD_LINES": 300,
    "DOC_REVIEW_L2_SKIP_THRESHOLD_LINES": 200,
    "DOC_REVIEW_L2_SKIP_DOC_TYPES": ["brief", "prd-lite", "arch-lite", "dev-plan-lite", "changelog"],
    "TDD_LIGHT_LOC_THRESHOLD": 50,
    "SPRINT_REVIEW_MICRO_TASK_COUNT": 2,
    "RETRO_TRIGGER_SELF_CAUSED": 5
  },
  "features": {
    "tdd-engine": {
      "min_version": "0.1.0",
      "auto_enable": true,
      "phase_guard": "development",
      "description": "TDD三阶段开发引擎 (RED→GREEN→REFACTOR)"
    },
    "doc-review": {
      "min_version": "0.1.0",
      "auto_enable": true,
      "phase_guard": null,
      "description": "文档双层审计 (Layer 1脚本 + Layer 2 AI)"
    }
    // ...其余 feature 同形结构，省略
  },
  "migration_checks": [
    {
      "id": "mc-0.1.0-constants",
      "release_version": "0.1.0",
      "description": "COMMON-RULES.md 必须定义执行模式矩阵引用的配置常量",
      "type": "file_must_contain",
      "path": ".cataforge/rules/COMMON-RULES.md",
      "patterns": ["DOC_SPLIT_THRESHOLD_LINES", "RETRO_TRIGGER_SELF_CAUSED"]
    }
    // ...其余 check 同形结构
  ]
}
```

> 用户安装时 `cataforge setup` / `cataforge upgrade apply` 写盘的 `version` 字段由 [`scaffold._stamp_framework_version`](../../src/cataforge/core/scaffold.py) 戳入实际包版本（`cataforge.__version__`）；用户侧不会看到 `0.0.0-template` 字面值。源仓库 `.cataforge/framework.json:version` 留 `0.0.0-template` 占位，[`Config.version`](../../src/cataforge/core/config.py) 在读取时检测此前缀并解析为运行包版本（这样 dogfood 开发者在 `cataforge bootstrap` / `cataforge doctor` 看到的是真实版本号），同时 [`bootstrap_cmd._semver_newer`](../../src/cataforge/cli/bootstrap_cmd.py) 也对 `0.0.0-` 前缀短路返回 False，避免触发"installed > scaffold"伪升级。

### 字段说明

`upgrade apply` 行为分两类（与 `_merge_framework_json` 保持一致）：

- **preserve**：用户已写入的值在升级时保留
- **overwrite**：每次升级被最新 scaffold 全量覆盖（设计如此 —— 框架元数据不应允许用户偏移）

| 字段 | 用户可编辑 | upgrade 行为 | 作用 |
|------|:---------:|:------------:|------|
| `version` | ❌ | overwrite（戳入 `cataforge.__version__`） | 实际包版本，用于 doctor / migration_check 比对 |
| `runtime_api_version` | ❌ | overwrite | scaffold ↔ runtime 接口版本号，BREAKING 时递增 |
| `runtime.platform` | ✅ | **preserve** | 目标 IDE：`claude-code` / `cursor` / `codex` / `opencode`；由 `cataforge setup --platform` 写入，`set_runtime_platform()` 也会更新此字段 |
| `runtime.*`（其它） | ✅ | overwrite | `extra='allow'`，但目前无其它 scaffold 已知字段 |
| `description` | ❌ | overwrite | 框架自述文案 |
| `constants.MANUAL_REVIEW_CHECKPOINTS` | ❌ | overwrite | 手动审查检查点列表（如 `["pre_dev", "pre_deploy"]`） |
| `constants.MAX_QUESTIONS_PER_BATCH` | ❌ | overwrite | `AskUserQuestion` 单批最大问题数 |
| `constants.EVENT_LOG_PATH` / `EVENT_LOG_SCHEMA` | ❌ | overwrite | 事件日志路径与 JSON Schema 位置 |
| `constants.DOC_SPLIT_THRESHOLD_LINES` | ❌ | overwrite | `doc-gen` 自动分卷阈值 |
| `constants.DOC_REVIEW_L2_SKIP_THRESHOLD_LINES` | ❌ | overwrite | `doc-review` Layer 2 跳过阈值 |
| `constants.DOC_REVIEW_L2_SKIP_DOC_TYPES` | ❌ | overwrite | Layer 2 跳过的文档类型 |
| `constants.TDD_LIGHT_LOC_THRESHOLD` | ❌ | overwrite | TDD 轻量模式 LOC 阈值 |
| `constants.SPRINT_REVIEW_MICRO_TASK_COUNT` | ❌ | overwrite | sprint-review 跳过的 micro sprint 任务数阈值 |
| `constants.RETRO_TRIGGER_SELF_CAUSED` | ❌ | overwrite | reflector 触发的累积自致问题数 |
| `features.<id>.min_version` | ❌ | overwrite | feature 引入的版本号（语义版本） |
| `features.<id>.auto_enable` | ❌ | overwrite | 是否在符合 `phase_guard` 时自动启用 |
| `features.<id>.phase_guard` | ❌ | overwrite | 限定阶段（`null` 表示全局可用） |
| `features.<id>.description` | ❌ | overwrite | feature 简述 |
| `migration_checks[].id` | ❌ | overwrite | 检查唯一标识（命名约定 `mc-<release_version>-<slug>`，与项目主线版本号一致；`mc-0.6.0-*` 等历史前缀已在 v0.1.13 统一为 `mc-0.1.x-*`） |
| `migration_checks[].release_version` | ❌ | overwrite | 检查引入的版本号；用于排序与弃用判定 |
| `migration_checks[].deprecate_after` | ❌ | overwrite | （可选）一旦运行包版本 ≥ 此 semver，doctor 自动 SKIP 该检查并打印来源版本。用法：当某条检查覆盖的旧状态已不可能在任何"近期安装"中存在时，标注此字段以避免 migration_checks 列表无限膨胀 |
| `migration_checks[].type` | ❌ | overwrite | 检查类型：`file_must_contain` / `file_must_not_contain` / `dir_must_contain_files` / `file_must_exist` |
| `migration_checks[].path` | ❌ | overwrite | 被检查文件 / 目录的相对路径 |
| `migration_checks[].patterns` | ❌ | overwrite | 待匹配子串 / 文件名列表 |
| `migration_checks[].requires_deploy` | ❌ | overwrite | true 时该检查作用于 `cataforge deploy` 写出的产物（如 `.claude/settings.json`），doctor 在未 deploy 的 workspace 上跳过 |
| `migration_checks[].allow_missing` | ❌ | overwrite | （仅 `file_must_not_contain` 类型）默认 false 时，路径不存在 → FAIL（防止 vacuous PASS）。设 true 表示"路径在某些安装下不存在是合法情况"（典型场景：检查源码而非用户项目文件，end-user 安装走 site-packages 时 path 缺失） |
| `upgrade.source.type` | ❌ | overwrite | 当前固定 `"github"`；这是**框架资产**的远程拉取协议（区别于 `cataforge` Python 包的安装机制——后者由 pip / uv 处理，由 `self-update` skill 编排） |
| `upgrade.source.repo` | ❌ | overwrite | scaffold 远程仓库（`<owner>/<repo>` 形态） |
| `upgrade.source.branch` | ❌ | overwrite | scaffold 拉取分支（默认 `main`） |
| `upgrade.source.token_env` | ❌ | overwrite | 私有仓库使用的环境变量名（默认 `GITHUB_TOKEN`） |
| `upgrade.state.last_commit` | ✅ | **preserve** | 上次 apply 拉取的 commit SHA |
| `upgrade.state.last_version` | ✅ | **preserve** | 上次 apply 时的包版本 |
| `upgrade.state.last_upgrade_date` | ✅ | **preserve** | 上次 apply 时间戳（ISO 8601） |

> **常见误解**：示例中的 `upgrade.source` 子树**不是 preserve 字段**。如果你 fork 了 CataForge 并希望从私有镜像拉 scaffold，目前只能在每次 `upgrade apply` 后重新写入这些字段；持久化用户自定义 source 的能力跟踪在 `upgrade.source preserve mode` issue。

> 历史记录：framework.json `description` 字段一度写"upgrade.source 升级时保留用户已配置值，补充新字段"，与代码（overwrite）矛盾；该描述已在 v0.1.13 修正以代码为准。

---

## platforms/\<id\>/profile.yaml

各平台能力声明、工具翻译、Hook/MCP 配置、降级策略。**权威 schema 是 [`.cataforge/platforms/_schema.yaml`](../../.cataforge/platforms/_schema.yaml)**；本文以 [`.cataforge/platforms/cursor/profile.yaml`](../../.cataforge/platforms/cursor/profile.yaml) 为骨架示例。完整能力矩阵见 [`../architecture/platform-adaptation.md`](../architecture/platform-adaptation.md) §平台能力矩阵。

### 结构示例

```yaml
platform_id: cursor                  # 唯一标识：claude-code | cursor | codex | opencode
display_name: Cursor
version_tested: "3.1"

# 核心 10 能力的工具名翻译；adapter 通过此 map 把 capability id 翻译为平台原生工具
tool_map:
  file_read: Read
  file_write: Write
  file_edit: Write                   # null 表示该平台无原生支持，走 degradation
  file_glob: Glob
  file_grep: Grep
  shell_exec: Shell
  web_search: WebSearch
  web_fetch: null
  user_question: null
  agent_dispatch: Task

extended_capabilities:               # 可选 — 核心 10 项之外的扩展能力
  notebook_edit: null
  browser_preview: computer
  image_input: null
  code_review: null

agent_definition:
  format: yaml-frontmatter           # yaml-frontmatter | toml
  scan_dirs: [.cursor/agents]        # 平台原生扫描的 Agent 目录
  needs_deploy: true                 # false 时 deploy 不写 agent 产物

skill_definition:
  target_dir: .claude/skills         # 平台读取 skill 的目录
  needs_deploy: true

command_definition:
  target_dir: .cursor/commands       # 平台 slash command 目录（缺省时该平台无原生 slash 支持）
  needs_deploy: true

agent_config:                        # Agent frontmatter 字段约束
  supported_fields: [name, description, tools, ...]
  memory_scopes: []                  # 支持的 memory scope（user/project/local）
  isolation_modes: [worktree]        # 支持的隔离模式

instruction_file:                    # PROJECT-STATE.md → 平台指令文件的部署规则
  reads_claude_md: false             # 平台是否原生读 CLAUDE.md
  targets:
    - type: project_state_copy
      path: AGENTS.md
      update_strategy: section-merge # overwrite | section-merge
      section_policy:                # 仅 section-merge 时生效（详见 §instruction_file 段）
        framework: [文档导航, 框架机制]   # 框架拥有，每次覆盖
        schema:    [项目信息, 全局约定]   # 框架定义结构，用户填值，字段级合并
        runtime:   [项目状态, 执行环境]   # 运行时填充，deploy 不触碰
        user_extensible: true             # 保留模板没有的用户章节
        always_overwrite_fields:
          项目信息: [运行时]            # 即便在 schema 类，这些字段也强制用模板值
  additional_outputs:                # deploy 额外生成的指令文件
    - target: .cursor/rules/
      format: mdc
      source: rules + platform overrides

dispatch:
  tool_name: Task                    # 调度工具名
  is_async: false                    # true = 两步异步调度（如 OpenCode）
  params: [subagent_type, prompt, description, model]

hooks:
  config_format: json                # json | yaml | plugin | null
  config_path: .cursor/hooks.json
  entry_type: command                # 平台 hook 条目的 type 字段值
  event_map:                         # CataForge 事件 → 平台事件
    PreToolUse: preToolUse
    PostToolUse: postToolUse
    Stop: stop
    SessionStart: sessionStart
    Notification: null               # null = 该平台无对应事件
  matcher_map:                       # CataForge matcher → 平台 matcher
    Bash: Shell
    Agent: Task
    "Edit|Write": Write
  tool_overrides: {}                 # 当 hook 矩阵与 tool_map 不同时的覆盖
  degradation:                       # 各 hook script 在该平台的支持级别
    guard_dangerous: native          # native | degraded | unsupported
    detect_correction: degraded
    notify_done: native

features:                            # 平台级 boolean flags（用于能力矩阵）
  cloud_agents: true
  parallel_agents: true
  plan_mode: false
  computer_use: true
  # ... 完整列表见 _schema.yaml §features

permissions:
  modes: [default, auto]             # 平台支持的审批模式

model_routing:
  available_models: [opus, sonnet, gpt-5.4, ...]
  per_agent_model: true              # 是否支持 per-agent 模型选择

context_injection:                   # 规则 / 指令注入策略（详见下方 §context_injection 字段）
  auto_injection:
    mechanism: cursor_rules
    eager: true
    preamble_files: []
  inline_file_syntax:
    kind: at_mention
    template: "@{path}"
  rules_distribution:
    target: .cursor/rules
    format: mdc
    activation: always

rules:                               # 可选：跨平台镜像
  cross_platform_mirror: false       # true 时把 .cataforge/rules 同步到 .claude/rules
```

### 顶层字段速查

| 字段 | 必需 | 作用 |
|------|:----:|------|
| `platform_id` | ✅ | 唯一 id，必须等于目录名 |
| `display_name` | ✅ | 用户可读名（doctor / 错误消息使用） |
| `version_tested` | ✅ | 最后一次回归验证的平台版本号 |
| `tool_map` | ✅ | 核心 10 capability 的工具翻译；缺失值 `null` 触发降级 |
| `extended_capabilities` | ❌ | 核心 10 项之外的扩展能力（如 notebook_edit） |
| `agent_definition` | ✅ | Agent 部署目标与格式 |
| `skill_definition` | ❌ | Skill 部署目标 |
| `command_definition` | ❌ | Slash command 部署目标 |
| `agent_config` | ❌ | Agent frontmatter 字段子集与隔离模式 |
| `instruction_file` | ✅ | PROJECT-STATE.md → 平台指令文件的写入规则 |
| `dispatch` | ✅ | 子代理调度工具的描述 |
| `hooks` | ✅ | hooks.yaml 翻译为平台原生 hook 配置的规则 |
| `features` | ❌ | 平台级 boolean 特性矩阵 |
| `permissions` | ❌ | 审批模式列表 |
| `model_routing` | ❌ | 模型路由能力 |
| `context_injection` | ❌ | 规则 / 指令注入策略（缺失时走默认路径） |
| `rules` | ❌ | 跨平台镜像开关 |

### context_injection 字段

声明平台如何把规则 / 指令加载进 LLM 上下文。`cataforge deploy` 期读取这些字段，把差异烘焙到各平台产物里，运行时 LLM 拿到的是已为当前平台定制过的 markdown。

| 字段 | 类型 | 示例 |
|------|------|------|
| `auto_injection.mechanism` | enum | `claude_md` / `agents_md` / `cursor_rules` / `opencode_instructions` / `none` |
| `auto_injection.eager` | bool | 启动即入上下文 |
| `auto_injection.size_limit_bytes` | int | Codex AGENTS.md 合并上限 `32768` |
| `auto_injection.preamble_files` | list[str] | 需在指令文件顶部内联引用的文件路径（仅 `at_mention` 平台有效） |
| `inline_file_syntax.kind` | enum | `at_mention` / `read_tool` / `xml_preload` |
| `inline_file_syntax.template` | str | 如 `"@{path}"` / `"请先 Read {path}"` |
| `rules_distribution.target` | str | 规则分发目标路径或 `opencode.json` |
| `rules_distribution.format` | enum | `markdown` / `mdc` / `remote_url_list` |
| `rules_distribution.activation` | enum | `always` / `glob` / `description` / `manual_read` / `opencode_instructions` |
| `rules_distribution.files` | list[str] | `opencode_instructions` 激活时写入 `opencode.json.instructions` 的路径模式 |

**四平台实际声明**：

| 平台 | mechanism | inline | rules target | activation |
|------|-----------|--------|---------------|-----------|
| claude-code | `claude_md` | `@{path}` | `.claude/rules` | `manual_read`（preamble 仅放 COMMON-RULES） |
| codex | `agents_md`（≤32 KiB） | `请先 Read {path}` | `.codex/rules` | `manual_read` |
| cursor | `cursor_rules` | `@{path}` | `.cursor/rules`（MDC） | `always` |
| opencode | `opencode_instructions` | `请先 Read {path}` | `opencode.json` | `opencode_instructions` |

> 向后兼容：未声明 `context_injection` 的 profile 继续走默认路径。OpenCodeAdapter 在缺字段时回退到字面 `["AGENTS.md", ".cataforge/rules/*.md"]`。

---

## hooks.yaml

平台无关 hook 规范，由 `cataforge.hook.bridge` 解析后联同各 platform profile 的 `hooks.event_map` / `matcher_map` / `degradation` 生成平台原生 hook 配置（`.claude/settings.json`、`.cursor/hooks.json` 等）。

`schema_version: 2` 是当前形态；schema 演化策略见 hooks.yaml 顶部注释。

### 结构示例（与 `.cataforge/hooks/hooks.yaml` 实际形态一致）

```yaml
schema_version: 2

hooks:
  PreToolUse:
    - matcher_capability: shell_exec       # CataForge capability id（不是平台原生工具名）
      script: guard_dangerous              # 短名 — 解析为 cataforge.hook.scripts.guard_dangerous
      type: block                          # block | observe
      description: "危险命令拦截"
      safety_critical: true                # 该 hook 失败应阻断流程，degraded 时也必须有降级方案

  PostToolUse:
    - matcher_capability: agent_dispatch
      script: detect_review_flag
      type: observe
      description: "审查纠正信号捕获"
      matcher_agent_id: [reviewer]         # v2 新增：仅特定 agent 触发

  Stop:
    - script: notify_done                  # 无 matcher_capability → 全事件触发
      type: observe
      description: "会话结束通知"

  # 同样支持 Notification / SessionStart 事件分组

degradation_templates:                     # 平台不支持某 hook 时的降级方案
  guard_dangerous:
    strategy: rules_injection              # rules_injection | prompt_checklist | prompt_instruction | skip
    content: |
      SAFETY RULES (auto-generated — platform lacks PreToolUse hook):
      - NEVER run rm -rf without explicit user confirmation
  detect_correction:
    strategy: skip
    reason: "纠正学习为非关键功能"        # skip 必须提供 reason；其它 strategy 用 content
```

### 字段说明

**顶层**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `schema_version` | int | 当前 `2`。`bridge.py` 校验此值；不匹配会拒绝加载 |
| `hooks` | map[event, list[hook]] | 按事件名（`PreToolUse` / `PostToolUse` / `Stop` / `Notification` / `SessionStart`）分组的 hook 条目 |
| `degradation_templates` | map[script_name, template] | 各 hook script 的降级模板。当目标 platform 在 `profile.yaml.hooks.degradation.<script>` 标 `degraded` / `unsupported` 时，deploy 注入此处的内容 |

**`hooks.<event>[]` 条目字段**：

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `script` | str | ✅ | hook 实现的模块短名；解析为 `cataforge.hook.scripts.<name>` |
| `type` | enum[block, observe] | ✅ | `block` 失败时阻断当前工具调用；`observe` 仅观测，失败不阻断 |
| `description` | str | ⚠️ 推荐 | 一句说明，写入 deploy 产物注释 |
| `matcher_capability` | str | 可选 | CataForge capability id（如 `shell_exec` / `agent_dispatch` / `file_edit` / `user_question`），由 platform 的 `tool_map` / `matcher_map` 翻译为原生工具名。缺省 = 全事件触发（适合 `Stop` / `Notification` / `SessionStart`） |
| `safety_critical` | bool | 可选 | 默认 `false`。`true` 表示该 hook 即便 degraded 也必须给 `degradation_templates` 提供有效降级；CI 可据此校验 |
| `matcher_agent_id` | list[str] | 可选 (v2+) | 仅当 dispatch 到列出的 agent id 时触发，例如 `[reviewer]` |
| `matcher_file_pattern` | str | 可选 (v2+) | 文件路径 glob 过滤（仅 `file_*` capability） |
| `matcher_command_pattern` | str | 可选 (v2+) | shell 命令正则过滤（仅 `shell_exec`） |

**`degradation_templates.<script>` 字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `strategy` | enum | `rules_injection`（注入 .cataforge/rules）/ `prompt_checklist`（注入 prompt 段）/ `prompt_instruction`（注入指令片段）/ `skip`（仅记录） |
| `content` | str | strategy ∈ {rules_injection, prompt_checklist, prompt_instruction} 时必填 — 注入的实际文本 |
| `reason` | str | strategy = `skip` 时必填 — 跳过原因（写入降级日志） |

### 实物 hook 列表（dogfood 项目）

`cataforge doctor` 在 `Hook script importability` 段会校验全部声明 hook 的 `cataforge.hook.scripts.<name>` 都可 `importlib.find_spec`：

| event | matcher_capability | script |
|-------|-------------------|--------|
| PreToolUse | shell_exec | guard_dangerous |
| PreToolUse | agent_dispatch | log_agent_dispatch |
| PostToolUse | agent_dispatch | validate_agent_result |
| PostToolUse | file_edit | lint_format |
| PostToolUse | user_question | detect_correction |
| PostToolUse | agent_dispatch (matcher_agent_id=[reviewer]) | detect_review_flag |
| Stop | — | notify_done |
| Notification | — | notify_permission |
| SessionStart | — | session_context |

---

## Agent 定义（AGENT.md）

路径：`.cataforge/agents/<id>/AGENT.md`

```md
---
id: product-manager
display_name: 产品经理
max_turns: 60
tools:
  allow: [file_read, file_write, file_edit, file_glob, file_grep, web_search, web_fetch, user_question]
  deny: [shell_exec, agent_dispatch]
write_paths:
  - docs/prd/
  - docs/research/
skills:
  - req-analysis
  - doc-gen
  - doc-nav
  - research
---

# 产品经理

（Agent 行为描述 Markdown）
```

完整清单：[`agents-and-skills.md`](./agents-and-skills.md)。

---

## Skill 定义（SKILL.md）

路径：`.cataforge/skills/<id>/SKILL.md`

```md
---
id: doc-review
type: instructional   # 或 script
domain: quality
description: 文档双层审计（脚本 + AI）
---

（Skill 触发条件、输入输出契约、行为步骤）
```

---

## MCP 声明

路径：`.cataforge/mcp/<id>.yaml`

```yaml
id: echo-mcp
name: Echo MCP
description: Test MCP server
transport: stdio
command: python
args:
  - -c
  - "import time; time.sleep(60)"
env:
  LOG_LEVEL: info
```

生命周期：`cataforge mcp start/stop`；状态文件在 `.cataforge/.mcp-state/`。

---

## 参考

- CLI 命令：[`cli.md`](./cli.md)
- 架构：[`../architecture/overview.md`](../architecture/overview.md)
- 平台适配：[`../architecture/platform-adaptation.md`](../architecture/platform-adaptation.md)
