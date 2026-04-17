# 配置参考

> `.cataforge/` 目录下的配置文件清单与字段说明。所有文件以 **单一来源** 原则组织：平台相关的内容封装在 `platforms/<id>/profile.yaml`，其余文件平台无关。

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

框架单一配置源。结构示例：

```json
{
  "version": "0.1.1",
  "runtime": {
    "platform": "cursor",
    "mode": "standard",
    "checkpoints": ["pre_dev", "pre_deploy"]
  },
  "constants": {
    "TDD_LIGHT_LOC_THRESHOLD": 50,
    "SPRINT_REVIEW_MICRO_TASK_COUNT": 3,
    "DOC_REVIEW_L2_SKIP_THRESHOLD_LINES": 200,
    "RETRO_TRIGGER_SELF_CAUSED": 5,
    "MAX_QUESTIONS_PER_BATCH": 3
  },
  "features": {
    "design_tool": "penpot"
  },
  "migration_checks": [
    { "id": "mc-0.7.0-detect-correction-registered", "severity": "error" }
  ],
  "upgrade": {
    "source": "pip",
    "state": "up-to-date"
  }
}
```

### 字段说明

| 字段 | 用户可编辑 | 作用 |
|------|:---------:|------|
| `version` | ❌ | 由 `cataforge.__version__` 实时戳入 |
| `runtime.platform` | ✅ | 目标 IDE：`claude-code` / `cursor` / `codex` / `opencode` |
| `runtime.mode` | ✅ | 执行模式：`standard` / `agile-lite` / `agile-prototype` |
| `runtime.checkpoints` | ✅ | 手动审查检查点 |
| `constants.*` | ❌ | 框架常量（由 scaffold 管理） |
| `features.*` | ❌ | 功能开关（由 scaffold 管理） |
| `migration_checks` | ❌ | 迁移检查项（由 scaffold 管理） |
| `upgrade.state` | ✅ | 用户可标记升级状态 |
| `upgrade.source` | ❌ | 升级来源（`pip` / `uv-tool`） |

> ❌ 字段每次 `upgrade apply` 都会被最新 scaffold 覆盖。

---

## platforms/\<id\>/profile.yaml

各平台能力映射、工具翻译、降级策略。骨架：

```yaml
platform: cursor
capabilities:
  agent: native
  hook: native
  mcp: native
  ask_user_question: degraded
paths:
  agents: .cursor/agents
  hooks: .cursor/hooks.json
  rules: .cursor/rules
  mcp: .cursor/mcp.json
rules:
  cross_platform_mirror: false   # 若为 true 会镜像到 .claude/rules
degradation:
  ask_user_question: prompt_check
  notification: skip
context_injection:               # 见 §context_injection 字段
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
```

完整矩阵：[`../architecture/platform-adaptation.md`](../architecture/platform-adaptation.md) §平台能力矩阵。

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
| opencode | `opencode_instructions` | `请先 read {path}` | `opencode.json` | `opencode_instructions` |

> 向后兼容：未声明 `context_injection` 的 profile 继续走默认路径。OpenCodeAdapter 在缺字段时回退到字面 `["AGENTS.md", ".cataforge/rules/*.md"]`。

---

## hooks.yaml

平台无关 hook 规范。示例：

```yaml
version: 1
hooks:
  - id: enforce-format
    event: PreToolUse
    matcher: Edit
    script: .cataforge/hooks/scripts/enforce-format.sh
  - id: detect-correction
    event: PostToolUse
    matcher: AskUserQuestion
    script: .cataforge/hooks/scripts/detect-correction.py
```

- `event`：`PreToolUse` / `PostToolUse` / `Stop` / `Notification` / `SessionStart`
- `matcher`：平台原生工具名（按 profile 自动翻译）
- 平台无降级路径时自动 `skip`，保留日志

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
