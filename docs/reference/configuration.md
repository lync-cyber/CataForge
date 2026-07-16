# 配置参考

> `.cataforge/` 目录下的配置文件清单与字段说明。所有文件以 **单一来源** 原则组织：平台相关的内容封装在 `platforms/<id>/profile.yaml`，其余文件平台无关。
>
> **适用版本**：以 `cataforge --version` 为准（= `cataforge.__version__`）。Schema 字段以 [`src/cataforge/core/`](../../src/cataforge/core/) 实际实现为权威。

## 目录

- [文件总览](#文件总览)
- [配置解析层级与 `cataforge config`](#配置解析层级与-cataforge-config)
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
| `framework.json` | `.cataforge/framework.json` | 框架单一配置源（声明 + catalog，schema v2） |
| `config.local.json` | `.cataforge/config.local.json` | 本机覆盖层（gitignored，白名单字段） |
| `state/` | `.cataforge/state/` | 运行状态目录（gitignored）：`deploy/<platform>/{state,manifest}.json`、`upgrade.json`、`locks/` |
| `PROJECT-STATE.md` | `.cataforge/PROJECT-STATE.md` | 项目状态模板（用户可编辑） |
| `COMMON-RULES.md` | `.cataforge/rules/COMMON-RULES.md` | 通用行为规则 |
| `SUB-AGENT-PROTOCOLS.md` | `.cataforge/rules/SUB-AGENT-PROTOCOLS.md` | 子代理执行协议 |
| `ORCHESTRATOR-PROTOCOLS.md` | `.cataforge/agents/orchestrator/ORCHESTRATOR-PROTOCOLS.md` | 编排器热路径调度协议 |
| `ORCHESTRATOR-BOOTSTRAP-PROTOCOLS.md` | `.cataforge/agents/orchestrator/ORCHESTRATOR-BOOTSTRAP-PROTOCOLS.md` | 编排器项目初始化协议（冷路径） |
| `ORCHESTRATOR-RECOVERY-PROTOCOLS.md` | `.cataforge/agents/orchestrator/ORCHESTRATOR-RECOVERY-PROTOCOLS.md` | 编排器异常恢复协议族（冷路径） |
| `ORCHESTRATOR-META-PROTOCOLS.md` | `.cataforge/agents/orchestrator/ORCHESTRATOR-META-PROTOCOLS.md` | 编排器元运维与学习协议（冷路径） |
| `hooks.yaml` | `.cataforge/hooks/hooks.yaml` | 平台无关 hook 规范 |
| `profile.yaml` | `.cataforge/platforms/<id>/profile.yaml` | 各平台能力映射 |
| `AGENT.md` | `.cataforge/agents/<id>/AGENT.md` | Agent 定义（frontmatter + Markdown） |
| `SKILL.md` | `.cataforge/skills/<id>/SKILL.md` | Skill 定义 |
| `<id>.yaml` | `.cataforge/mcp/<id>.yaml` | MCP 服务声明 |

---

## 配置解析层级与 `cataforge config`

配置值按以下优先级解析（[`ConfigManager.explain`](../../src/cataforge/core/config.py)）：

```text
CLI 参数（如 deploy --platform）
  > CATAFORGE_PLATFORM 环境变量（仅平台路径 deployment.default_platform）
  > .cataforge/config.local.json（本机覆盖层，gitignored，白名单字段）
  > .cataforge/framework.json（schema v2；v1 的 runtime.platform 兼容读取 = legacy 层）
  > 代码内默认值（deployment.default_platform=claude-code、context.mode=graph、project.design_tool=none）
```

`cataforge config` 子命令：

| 子命令 | 语义 |
|--------|------|
| `config validate` | schema 形状（Pydantic `FrameworkFile`）+ `schema_version` 不高于运行包支持值 + 平台 id 合法 + `default_platform ∈ targets`；检测到 v1 布局时 WARN 并提示 `config migrate` |
| `config get <path>` | 打印按层级解析后的值（未设置时 exit 1） |
| `config explain <path>` | 打印值与来源层：`env` / `local` / `framework` / `legacy` / `default` |
| `config set <path> <value>` | 仅白名单路径可写：`deployment.default_platform`、`deployment.targets`（逗号分隔列表）、`context.mode`、`project.design_tool`；平台值经合法 id 校验；同值不落盘；支持 `--dry-run` |
| `config migrate` | v1 → v2 布局迁移（幂等、先备份）；支持 `--dry-run`。详见 [`../guide/multi-platform.md`](../guide/multi-platform.md) §旧单平台项目迁移 |

所有 framework.json 写路径（`config set`、`setup --platform`、`set_languages` 等）持 `.cataforge/state/locks/config.lock`（TTL 60 秒，过期自动回收），防止并发写丢失更新。

---

## framework.json

框架单一配置源（schema v2，`schema_version: 2` = [`CONFIG_SCHEMA_VERSION`](../../src/cataforge/core/config_migrate.py)）。Schema 由 [`cataforge.core.schema.framework.FrameworkFile`](../../src/cataforge/core/schema/framework.py) 校验；upgrade 时的字段级所有权合并由 [`cataforge.core.scaffold._merge_framework_json`](../../src/cataforge/core/scaffold.py)（`_FRAMEWORK_OWNED_TOP` / `_USER_OWNED_DICT_BLOCKS`）实现 —— 修改本节字段说明前请先核对那两处代码。

### 结构示例（与 `.cataforge/framework.json` v2 实际形态一致）

```json
{
  "schema_version": 2,
  "version": "0.0.0-template",
  "runtime_api_version": "1.0",
  "deployment": {
    "default_platform": "claude-code",
    "targets": ["claude-code"]
  },
  "description": "CataForge 统一框架配置（schema v2）……",
  "upgrade": {
    "source": {
      "type": "github",
      "repo": "lync-cyber/CataForge",
      "branch": "main",
      "token_env": "GITHUB_TOKEN"
    }
  },
  "feedback": {
    "gh": {
      "labels": {
        "bug": ["bug"],
        "suggest": ["enhancement"],
        "correction-export": ["enhancement"]
      },
      "fallback_on_missing_label": true
    }
  },
  "kg": {
    "store_backend": "oxigraph",
    "db_path": ".cataforge/kg/store",
    "ontology_namespace": "https://cataforge.dev/ontology/",
    "base_namespace": "https://cataforge.dev/instance/"
  },
  "context": {
    "mode": "graph",
    "kg_active_doc_types": ["prd", "arch", "ui-spec", "dev-plan", "test-report", "deploy-spec"]
  },
  "project": {
    "languages": [],
    "design_tool": "none"
  },
  "claude_md_limits": {
    "max_bytes": 30000,
    "max_state_section_lines": 80,
    "learnings_registry_max_entries": 10,
    "max_state_bullet_chars": 250
  },
  "constants": {
    "MAX_QUESTIONS_PER_BATCH": 3,
    "MANUAL_REVIEW_CHECKPOINTS": ["pre_dev", "post_sprint", "pre_deploy"],
    "EVENT_LOG_PATH": "docs/EVENT-LOG.jsonl",
    "EVENT_LOG_SCHEMA": ".cataforge/schemas/event-log.schema.json",
    "DOC_SPLIT_THRESHOLD_LINES": 300,
    "TDD_LIGHT_LOC_THRESHOLD": 150,
    "TDD_DEFAULT_MODE": "light",
    "AGENT_MODEL_DEFAULTS": { "orchestrator": "inherit", "architect": "heavy" },
    "AGENT_MODEL_TIER_HEAVY_WHITELIST": ["architect", "debugger"],
    "SKILL_RUNNER_TIMEOUT_DEFAULT_SECS": 300,
    "UNATTENDED_LOOP_MAX_ITERATIONS": 30
    // ...完整常量集见 .cataforge/framework.json 与 COMMON-RULES §框架配置常量
  },
  "dispatcher_skills": ["tdd-engine", "agent-dispatch", "start-orchestrator"],
  "workflow": {
    "description": "阶段路由骨架的单一事实源……",
    "modes": {
      "standard": { "phases": [ /* requirements → deployment 七阶段 */ ] },
      "agile-lite": { "phases": [ /* planning / dev_planning / development */ ] },
      "agile-prototype": { "phases": [ /* brief / development */ ] }
    }
  },
  "features": {
    "tdd-engine": {
      "min_version": "0.1.0",
      "auto_enable": true,
      "phase_guard": "development",
      "description": "TDD三阶段开发引擎 (RED→GREEN→REFACTOR)"
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

> 用户安装时 `cataforge setup` / `cataforge upgrade apply` 写盘的 `version` 字段由 [`scaffold._stamp_framework_version`](../../src/cataforge/core/scaffold.py) 戳入实际包版本（`cataforge.__version__`）；用户侧不会看到 `0.0.0-template` 字面值。源仓库 `.cataforge/framework.json:version` 留 `0.0.0-template` 占位，[`Config.version`](../../src/cataforge/core/config.py) 在读取时检测此前缀并解析为运行包版本（这样 dogfood 开发者在 `cataforge bootstrap` / `cataforge doctor` 看到的是真实版本号），同时 [`bootstrap._semver_newer`](../../src/cataforge/application/services/bootstrap.py) 也对 `0.0.0-` 前缀短路返回 False，避免触发"installed > scaffold"伪升级。

### 字段说明

`upgrade apply`（`cataforge setup --force-scaffold` 同路径）按**字段级所有权表**合并，行为分三类（与 `_merge_framework_json` 保持一致）：

- **preserve（用户块）**：`_USER_OWNED_DICT_BLOCKS` = `deployment` / `context` / `project` / `kg` / `feedback` / `git` / `claude_md_limits`，外加 `upgrade.source` 浅合并 —— existing key 保留，新 scaffold 默认键补充
- **overwrite（框架块）**：`_FRAMEWORK_OWNED_TOP` = `schema_version` / `version` / `runtime_api_version` / `description` / `constants` / `features` / `workflow` / `dispatcher_skills` / `migration_checks` —— 每次升级被最新 scaffold 全量覆盖（框架元数据不允许用户偏移）
- **未知顶层键一律保留**：scaffold 不认识的顶层键（用户 / 插件自定义命名空间）升级时原样随行

| 字段 | 用户可编辑 | upgrade 行为 | 作用 |
|------|:---------:|:------------:|------|
| `schema_version` | ❌ | overwrite | 配置布局版本（当前 `2`）。高于运行包支持值时所有读写命令显式 FAIL（先升级 `cataforge` 包）；低于当前值时 `config validate` WARN 并提示 `config migrate` |
| `version` | ❌ | overwrite（戳入 `cataforge.__version__`） | 实际包版本，用于 doctor / migration_check 比对 |
| `runtime_api_version` | ❌ | overwrite | scaffold ↔ runtime 接口版本号，BREAKING 时递增 |
| `deployment.default_platform` | ✅ | **preserve** | 缺省平台：`claude-code` / `cursor` / `codex` / `opencode`。由 `cataforge setup --platform` 或 `config set` 写入；该平台的指令文件是 §项目状态 的 SSOT |
| `deployment.targets` | ✅ | **preserve** | 项目声明的启用平台集合。`setup --platform` 把新 default **并入** targets（不删除已有成员）；无参 `cataforge deploy` 部署全部 targets |
| `runtime.platform` | —（legacy） | 迁移 | v1 字段。读取层兼容：`deployment.default_platform` 缺失时回落此值（`config explain` 显示 `legacy`）；`config migrate` / `upgrade apply` / `bootstrap` 自动迁移为 `deployment.default_platform` 并移除本键，`setup --platform` 写盘时也会弹出它 |
| `description` | ❌ | overwrite | 框架自述文案 |
| `constants.MANUAL_REVIEW_CHECKPOINTS` | ❌ | overwrite | 手动审查检查点列表（默认 `["pre_dev", "post_sprint", "pre_deploy"]`） |
| `constants.MAX_QUESTIONS_PER_BATCH` | ❌ | overwrite | `AskUserQuestion` 单批最大问题数 |
| `constants.EVENT_LOG_PATH` / `EVENT_LOG_SCHEMA` | ❌ | overwrite | 事件日志路径与 JSON Schema 位置 |
| `constants.DOC_SPLIT_THRESHOLD_LINES` | ❌ | overwrite | 单文档超长建议阈值（doc-review 超过则建议精简或拆为多个逻辑文档，默认 300） |
| `constants.META_DOC_SPLIT_THRESHOLD_LINES` | ❌ | overwrite | SKILL.md / AGENT.md / 协议文档超长建议阈值（默认 500） |
| `constants.DOC_REVIEW_L2_SKIP_THRESHOLD_LINES` | ❌ | overwrite | `context` review 分支 Layer 2 跳过阈值（默认 200） |
| `constants.DOC_REVIEW_L2_SKIP_DOC_TYPES` | ❌ | overwrite | Layer 2 跳过的文档类型 |
| `constants.TDD_LIGHT_LOC_THRESHOLD` | ❌ | overwrite | tdd_mode 升 standard 的 LOC 上限阈值（默认 150；≤ 阈值 → light） |
| `constants.TASK_SPLIT_LOC` | ❌ | overwrite | 单任务预估 LOC 超此值时 tech-lead 拆分任务（默认 250） |
| `constants.MID_PROGRESS_LOC` | ❌ | overwrite | 实现过程中达此 LOC 触发中途进度检查点（默认 200） |
| `constants.TDD_DEFAULT_MODE` | ❌ | overwrite | 任务卡 `tdd_mode` 缺省值（默认 light） |
| `constants.TDD_REFACTOR_TRIGGER` | ❌ | overwrite | REFACTOR 阶段条件触发的 category 清单（默认 `[complexity, duplication, coupling]`） |
| `constants.TDD_INLINE_ELIGIBLE_MODES` | ❌ | overwrite | TDD inline 执行（无 RED/GREEN 子代理）的执行模式集（默认 `[agile-lite, agile-prototype]`） |
| `constants.SPRINT_REVIEW_MICRO_TASK_COUNT` | ❌ | overwrite | sprint-review 跳过的 micro sprint 任务数阈值（默认 3） |
| `constants.CODE_REVIEW_L2_SKIP_TASK_KINDS` | ❌ | overwrite | 短路 code-review Layer 2 的 task_kind 清单（默认 `[chore, config, docs]`） |
| `constants.CODE_REVIEW_L2_SKIP_LIGHT_MAX_AC` | ❌ | overwrite | light 模式短路 Layer 2 的 AC 数上限（默认 2） |
| `constants.ADAPTIVE_REVIEW_DOWNGRADE_CLEAN_TASKS` | ❌ | overwrite | Adaptive Review 反向降级所需的连续 clean 任务数（默认 10） |
| `constants.RETRO_TRIGGER_SELF_CAUSED` | ❌ | overwrite | reflector 触发的累积自致问题数（默认 5） |
| `constants.RETRO_TRIGGER_UPSTREAM_GAP_DEFAULT` | ❌ | overwrite | `upstream-gap` 纠偏触发 framework-feedback 打包的累积阈值（默认 3） |
| `constants.EVENT_LOG_DRIFT_MIN_EVENTS` | ❌ | overwrite | framework-review EVENT-LOG 漂移检测要求的最小事件数（默认 10） |
| `constants.ANTI_PATTERN_MIN_COUNT_SKILL` | ❌ | overwrite | SKILL.md Anti-Patterns 段最小条目数（默认 3） |
| `constants.ANTI_PATTERN_MIN_COUNT_AGENT` | ❌ | overwrite | AGENT.md Anti-Patterns 段最小条目数（默认 4） |
| `constants.AGENT_MODEL_DEFAULTS` | ❌ | overwrite | 各 agent 缺省 model tier 映射（heavy: architect/debugger；inherit: orchestrator；余 standard） |
| `constants.AGENT_MODEL_TIER_HEAVY_WHITELIST` | ❌ | overwrite | 允许 heavy tier 的 agent 白名单（默认 `[architect, debugger]`） |
| `constants.SKILL_RUNNER_TIMEOUT_DEFAULT_SECS` | ❌ | overwrite | `SkillRunner` 默认 subprocess 超时秒数（默认 300） |
| `constants.UNATTENDED_*` | ❌ | overwrite | 无人值守构建循环参数组（`LOOP_MAX_ITERATIONS` / `STAGNATION_THRESHOLD` / `CARD_REVISION_CEILING` / `LOOP_ITER_TIMEOUT_SEC` / `RATELIMIT_WAIT_SEC`），语义见 COMMON-RULES §框架配置常量 |
| `dispatcher_skills` | ❌ | overwrite | dispatcher skill 清单（`tdd-engine` / `agent-dispatch` / `start-orchestrator`）；framework-review B5-α 据此区分 skill-as-router 与未定义 agent |
| `workflow` | ❌ | overwrite | 阶段路由骨架的单一事实源：`modes.{standard,agile-lite,agile-prototype}.phases[]`（phase / role / output_doc_type / execution_host / interactive / skippable）；orchestrator Phase Routing 与 framework-review B5 以此为准 |
| `features.<id>.min_version` | ❌ | overwrite | feature 引入的版本号（语义版本） |
| `features.<id>.auto_enable` | ❌ | overwrite | 是否在符合 `phase_guard` 时自动启用 |
| `features.<id>.phase_guard` | ❌ | overwrite | 限定阶段（`null` 表示全局可用） |
| `features.<id>.description` | ❌ | overwrite | feature 简述 |
| `migration_checks[].id` | ❌ | overwrite | 检查唯一标识（命名约定 `mc-<release_version>-<slug>`，与项目主线版本号一致） |
| `migration_checks[].release_version` | ❌ | overwrite | 检查引入的版本号；用于排序与弃用判定 |
| `migration_checks[].deprecate_after` | ❌ | overwrite | （可选）一旦运行包版本 ≥ 此 semver，doctor 自动 SKIP 该检查并打印来源版本。用法：当某条检查覆盖的旧状态已不可能在任何"近期安装"中存在时，标注此字段以避免 migration_checks 列表无限膨胀 |
| `migration_checks[].type` | ❌ | overwrite | 检查类型：`file_must_contain` / `file_must_not_contain` / `dir_must_contain_files` / `file_must_exist` |
| `migration_checks[].path` | ❌ | overwrite | 被检查文件 / 目录的相对路径 |
| `migration_checks[].patterns` | ❌ | overwrite | 待匹配子串 / 文件名列表 |
| `migration_checks[].requires_deploy` | ❌ | overwrite | true 时该检查作用于 `cataforge deploy` 写出的产物（如 `.claude/settings.json`），doctor 在未 deploy 的 workspace 上跳过 |
| `migration_checks[].platforms` | ❌ | overwrite | （可选）检查适用的平台 id 列表；所列平台在 doctor 的平台范围内均无部署记录时 SKIP —— 针对 `.claude/settings.json` 的检查不会 FAIL 一个 codex-only 项目 |
| `migration_checks[].allow_missing` | ❌ | overwrite | （仅 `file_must_not_contain` 类型）默认 false 时，路径不存在 → FAIL（防止 vacuous PASS）。设 true 表示"路径在某些安装下不存在是合法情况"（典型场景：检查源码而非用户项目文件，end-user 安装走 site-packages 时 path 缺失） |
| `upgrade.source.type` | ✅ | **preserve（浅合并）** | 当前固定 `"github"`；这是**框架资产**的远程拉取协议（区别于 `cataforge` Python 包的安装机制——后者由 pip / uv 处理，由 `framework-update` skill 编排）。fork 私有镜像场景直接改本块，升级保留已配置值、仅补充新字段 |
| `upgrade.source.repo` | ✅ | **preserve（浅合并）** | scaffold 远程仓库（`<owner>/<repo>` 形态） |
| `upgrade.source.branch` | ✅ | **preserve（浅合并）** | scaffold 拉取分支（默认 `main`） |
| `upgrade.source.token_env` | ✅ | **preserve（浅合并）** | 私有仓库 token 的**环境变量名**（默认 `GITHUB_TOKEN`）—— 配置文件只存变量名，token 本体只放环境变量 |
| `upgrade.state` | —（legacy） | 迁移 | 运行状态（`last_commit` / `last_version` / `event_log_validate_since` 等），权威位置是 `.cataforge/state/upgrade.json`（gitignored）。读取层对旧位置保持兼容；`config migrate` 把残留的 `upgrade.state` 迁出配置文件，迁移前 upgrade 合并让它原样随行 |
| `context.mode` | ✅ | **preserve** | 上下文事实源模式：`graph`（图为源，`context finalize` 导出 markdown）/ `markdown`（markdown 为源，无图后端） |
| `context.kg_active_doc_types` | ✅ | **preserve** | 走 KG 路径的 doc_type 集合（per-doc_type rolling cutover）。空数组 = 全部走 legacy file-loader；scaffold 默认 `["prd","arch","ui-spec","dev-plan","test-report","deploy-spec"]` |
| `project.languages` | ✅ | **preserve** | 项目语言声明（canonical id，见 [`languages.md`](./languages.md)）；由 `cataforge setup --language <id>` 写入，`set_languages()` 也更新此字段。空数组 = 读取时按 marker 文件自动探测 |
| `project.design_tool` | ✅ | **preserve** | 设计集成开关（`none` / `penpot`）。framework.json 是该字段的单一事实源 —— 由 `cataforge setup --with-penpot` 写入；deploy 据此渲染并强制盖入项目指令文件 §全局约定 「设计工具」字段（`always_overwrite_fields: 全局约定:[设计工具]`） |
| `kg.store_backend` | ✅ | **preserve** | KG 存储后端：`oxigraph`（默认，RocksDB 持久化）/ `memory`（仅测试） |
| `kg.db_path` | ✅ | **preserve** | KG store 路径（默认 `.cataforge/kg/store`） |
| `kg.ontology_namespace` / `kg.base_namespace` | ✅ | **preserve** | 本体 / 实例 IRI 命名空间（默认 `https://cataforge.dev/ontology/` 与 `…/instance/`） |
| `kg.custom_entity_prefixes` 等扩展键 | ✅ | **preserve** | `kg` 为用户块（`extra='allow'`），per-project 键（project_id / title / process_model / 自定义实体前缀注册）升级保留 |
| `feedback.gh.labels.<kind>` | ✅ | **preserve** | `cataforge feedback --gh` 建 issue 时的 `--label` 列表，`kind` ∈ `bug` / `suggest` / `correction-export`；空列表 = 不传 `--label` |
| `feedback.gh.fallback_on_missing_label` | ✅ | **preserve** | 上游仓库缺 label 被 `gh` 拒绝时自动去 `--label` 重试（默认 `true`） |
| `claude_md_limits.max_bytes` | ✅ | **preserve** | 指令文件体积上限（默认 30000），doctor「Instruction file hygiene」段按平台 profile 选定的指令文件（CLAUDE.md / AGENTS.md）执行 |
| `claude_md_limits.max_state_section_lines` | ✅ | **preserve** | §项目状态 行数上限（默认 80） |
| `claude_md_limits.learnings_registry_max_entries` | ✅ | **preserve** | Learnings Registry 条目上限（默认 10），超限提示 `cataforge claude-md compact` |
| `claude_md_limits.max_state_bullet_chars` | ✅ | **preserve** | §项目状态 单条 bullet 字符上限（默认 250） |
| `git.session_sync.enabled` | ✅ | **preserve** | SessionStart `git_sync` hook 总开关（默认 `true`）。关闭后会话启动不再自动同步/清理 |
| `git.session_sync.fast_forward_clean` | ✅ | **preserve** | 仅当会话在干净的默认分支上启动时快进（默认 `true`）。永不切分支 |
| `git.session_sync.prune_gone` | ✅ | **preserve** | 清理 upstream 已消失的本地分支（默认 `true`） |
| `git.session_sync.confirm_via_gh` | ✅ | **preserve** | 删除 `[gone]` 分支前经 gh 确认 PR 已合并（默认 `true`）；gh 不可用时降级为信任 `[gone]` |
| `git.session_sync.debounce_seconds` | ✅ | **preserve** | 两次自动同步的最小间隔秒数，抑制频繁重启刷屏（默认 `60`） |
| `git.session_sync.fetch_timeout_seconds` | ✅ | **preserve** | 自动 fetch 的超时秒数，慢网/离线时快速降级（默认 `10`） |
| `git.remote_policy.delete_branch_on_merge` | ✅ | **preserve** | `cataforge git ensure-policy` / bootstrap 设置的 GitHub「合并后删除 head 分支」（默认 `true`） |
| `git.remote_policy.squash_only` | ✅ | **preserve** | 同上，仅允许 squash 合并、禁用 merge-commit / rebase（默认 `true`） |
| （未知顶层键） | ✅ | **preserve** | scaffold 未声明的任何顶层键升级原样保留，供用户 / 插件扩展命名空间使用 |

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
          项目信息: [运行时, 框架版本]   # 即便在 schema 类，这些字段也强制用模板值
          全局约定: [设计工具]
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
  tool_overrides: {}                 # hook matcher/payload 名与 tool_map 不同时的覆盖
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
| `settings_defaults` | ❌ | deploy 时 set-if-absent 注入平台设置文件的框架默认键（用户已设的值不被覆盖）。claude-code 用它把 `env.CLAUDE_CODE_USE_POWERSHELL_TOOL=0` + `defaultShell=bash` + `env.CATAFORGE_PLATFORM=claude-code`（hook 显式平台身份）落进 `.claude/settings.json`；Windows 上保持 Bash 工具走 Git Bash，要求下游装 Git for Windows（缺失时 `cataforge doctor` 的「Shell preference」段 WARN） |
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
| `auto_injection.preamble_files` | list[str] | 需在指令文件顶部内联引用的文件路径（仅 `at_mention` 平台有效；四平台 profile 当前均声明 `[]`） |
| `inline_file_syntax.kind` | enum | `at_mention` / `read_tool` / `xml_preload` |
| `inline_file_syntax.template` | str | 如 `"@{path}"` / `"请先 Read {path}"` |
| `rules_distribution.target` | str | 规则分发目标路径或 `opencode.json` |
| `rules_distribution.format` | enum | `markdown` / `mdc` / `remote_url_list` |
| `rules_distribution.activation` | enum | `always` / `glob` / `description` / `manual_read` / `opencode_instructions` |
| `rules_distribution.files` | list[str] | `opencode_instructions` 激活时写入 `opencode.json.instructions` 的路径模式 |

**四平台实际声明**：

| 平台 | mechanism | inline | rules target | activation |
|------|-----------|--------|---------------|-----------|
| claude-code | `claude_md` | `@{path}` | `.claude/rules` | `manual_read`（`preamble_files: []` —— 规则仅经目录镜像单路注入，CLAUDE.md 顶部无 @import 前缀） |
| codex | `agents_md`（≤32 KiB） | `请先 Read {path}` | `.codex/rules` | `manual_read` |
| cursor | `cursor_rules` | `@{path}` | `.cursor/rules`（MDC） | `always` |
| opencode | `opencode_instructions` | `请先 Read {path}` | `opencode.json` | `opencode_instructions` |

> 向后兼容：未声明 `context_injection` 的 profile 继续走默认路径。OpenCodeAdapter 在缺字段时回退到字面 `["AGENTS.md", ".cataforge/rules/*.md"]`。

---

## hooks.yaml

平台无关 hook 规范，由 `cataforge.runtime.hook.bridge` 解析后联同各 platform profile 的 `hooks.event_map` / `tool_overrides` / `degradation` 生成平台原生 hook 配置（`.claude/settings.json`、`.cursor/hooks.json` 等）。

`schema_version: 2` 是当前形态；schema 演化策略见 hooks.yaml 顶部注释。

### 结构示例（与 `.cataforge/hooks/hooks.yaml` 实际形态一致）

```yaml
schema_version: 2

hooks:
  PreToolUse:
    - matcher_capability: shell_exec       # CataForge capability id（不是平台原生工具名）
      script: guard_dangerous              # 短名 — 解析为 cataforge.runtime.hook.scripts.guard_dangerous
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
| `script` | str | ✅ | hook 实现的模块短名；解析为 `cataforge.runtime.hook.scripts.<name>` |
| `type` | enum[block, observe] | ✅ | `block` 失败时阻断当前工具调用；`observe` 仅观测，失败不阻断 |
| `description` | str | ⚠️ 推荐 | 一句说明，写入 deploy 产物注释 |
| `matcher_capability` | str | 可选 | CataForge capability id（如 `shell_exec` / `agent_dispatch` / `file_edit` / `user_question`），由 platform 的 `tool_map` / `tool_overrides` 翻译为原生工具名。缺省 = 全事件触发（适合 `Stop` / `Notification` / `SessionStart`） |
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

`cataforge doctor` 在 `Hook script importability` 段会校验全部声明 hook 的 `cataforge.runtime.hook.scripts.<name>` 都可 `importlib.find_spec`：

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
  - context
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
id: context
type: instructional   # 或 script
domain: context
description: 统一上下文 I/O（navigate / generate / review / consistency / query 分支）
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
