# CLI 参考

> `cataforge` 命令的全部子命令与关键参数。完整帮助请用 `cataforge <cmd> --help`。
>
> **适用版本**：以 `cataforge --version` 为准（= `cataforge.__version__`，与 [`pyproject.toml`](../../pyproject.toml) 同步）。

## 命令总览

| 命令 | 说明 |
| ------ | ------ |
| [`cataforge bootstrap`](#bootstrap) | 一键 setup → upgrade → deploy → doctor（幂等） |
| [`cataforge doctor`](#doctor) | 健康诊断，可作 CI gate |
| [`cataforge setup`](#setup) | 初始化项目、设定运行时平台 |
| [`cataforge deploy`](#deploy) | 投放资产到目标平台 |
| [`cataforge agent`](#agent) | Agent 发现、校验、on-demand 调起 |
| [`cataforge skill`](#skill) | Skill 发现与执行 |
| [`cataforge hook`](#hook) | Hook 列表与测试 |
| [`cataforge mcp`](#mcp) | MCP 服务注册与生命周期 |
| [`cataforge plugin`](#plugin) | 插件发现 / 安装 / 卸载 |
| [`cataforge override`](#override) | 覆盖层定制 agent/skill |
| [`cataforge upgrade`](#upgrade) | 脚手架升级与校验 |
| [`cataforge context`](#context) | 文档与上下文 I/O：段落加载、索引、校验、写入生命周期 |
| [`cataforge docs`](#docs) | 文档列举与迁移；`load`/`index`/`validate` 为 context 的废弃别名 |
| [`cataforge kg`](#kg) | 知识图谱 store 生命周期、导入/导出、SPARQL 查询、追溯 |
| [`cataforge event`](#event) | 写事件日志 |
| [`cataforge correction`](#correction) | 写 On-Correction Learning 日志 |
| [`cataforge feedback`](#feedback) | 把下游信号打包为上游可消费的 markdown 反馈 |
| [`cataforge issue`](#issue) | 上游 GitHub issue 全闭环：triage 拉取分诊 / close 模板化关闭 |
| [`cataforge penpot`](#penpot) | Penpot 设计工具集成：Docker 栈 + MCP 服务部署与生命周期 |
| [`cataforge phase`](#phase) | 只读巡检当前 SDLC 工作流阶段及预期产物 |
| [`cataforge claude-md`](#claude-md) | 项目指令文件卫生：体积诊断 + Learnings Registry 压缩 |
| [`cataforge viz`](#viz) | 框架 / 项目结构图渲染（Mermaid / DOT / JSON 文本） |
| [`cataforge git`](#git) | 本地分支卫生：同步默认分支、清理 squash 合并分支、设置仓库 merge 策略 |

---

## bootstrap

**何时用它**：0→1 拉起项目或机器重装后，一条命令把 setup → upgrade → deploy → doctor 串起来；幂等，可反复跑。

```bash
cataforge bootstrap --platform <id> [--dry-run] [--yes] [--skip-doctor]
```

按依赖顺序逐步执行，遇首个失败即停。

| 参数 | 作用 |
| ------ | ------ |
| `--platform <id>` | 目标平台（首次安装必填）：`claude-code` / `cursor` / `codex` / `opencode` |
| `--dry-run` | 仅打印计划，逐步显示 skip / run 决策，不写盘 |
| `--yes` | 跳过写盘前的交互确认 |
| `--skip-doctor` | 跳过末尾 `doctor` 门禁（不推荐 —— doctor 是完整性兜底） |

---

## doctor

**何时用它**：新机器配置后 / 每次升级后 / 出错时作为排查起点；可作 CI gate。

```bash
cataforge doctor
```

健康诊断：

- 检查 `.cataforge/` 目录完整性
- 校验 `framework.json` / `hooks.yaml`
- 验证 4 个平台 `profile.yaml`
- 执行 `migration_checks` 段落
- 任一 FAIL 返回码 1（可作 CI gate）

**预期输出**：`Diagnostics complete.`

---

## setup

**何时用它**：新项目首次初始化 `.cataforge/`；或切换目标 IDE 平台。

```bash
cataforge setup --platform <id> [--force-scaffold] [--deploy]
```

初始化项目脚手架、设定目标平台。

| 参数 | 作用 |
| ------ | ------ |
| `--platform <id>` | 目标平台：`claude-code` / `cursor` / `codex` / `opencode` |
| `--force-scaffold` | 强制刷新 scaffold（保留用户字段），等价于 `upgrade apply` |
| `--deploy` | 初始化后立即部署（默认不部署） |
| `--dry-run` | 预演将要做的变更，不写盘 |
| `--check-prereqs` / `--check-only` | 仅检查前置条件，不安装（互为别名） |
| `--show-diff` | 打印 framework.json 将变更的字段 |

> `setup` 默认**只** 初始化 `.cataforge/` 脚手架与记录目标平台，**不**自动写入 IDE 产物（产物投放走 `cataforge deploy`，或在 `setup` 上加 `--deploy` 链式触发）。

---

## deploy

**何时用它**：`setup` 后写入 IDE 产物；或 `.cataforge/` 内容改动后重新投放。

```bash
cataforge deploy [--dry-run] [--platform <id>] [--include-maintainer-only]
```

投放资产到目标平台（Agent / 规则 / Hook / MCP）。

| 参数 | 作用 |
| ------ | ------ |
| `--dry-run` | 预演，输出预期动作但不实际写盘 |
| `--platform <id>` | 临时覆盖 `framework.json` 中的平台设置（可选 `all` 部署到所有平台） |
| `--conformance` | 仅执行平台 conformance 检查 |
| `--include-maintainer-only` | 一并部署 SKILL.md 标注 `maintainer-only: true` 的 skill（默认跳过；上游 CataForge 仓库 dogfood 才打开） |

多次 `deploy` 幂等；会自动清理孤儿产物。

**maintainer-only skill**：少量 skill（如 `framework-issue-resolve`）只在 CataForge 仓库自身开发时用，下游业务项目不需要。这类 skill 在 SKILL.md frontmatter 声明 `maintainer-only: true`，默认 `deploy` 会跳过、不下发到 `.claude/skills/`，避免无谓占用 prompt 上下文。在 CataForge 仓库自身工作的开发者跑 `cataforge deploy --include-maintainer-only` 把它们也链入本地 `.claude/skills/`，从而能在 Claude Code 用 `/framework-issue-resolve` 等 slash command 调用。

---

## agent

```bash
cataforge agent list                                    # 列出已发现的 Agent
cataforge agent list --skills                           # 附带每个 Agent 声明的 skills（AGENT.md frontmatter）
cataforge agent validate                                # 校验 Agent 定义合法性
cataforge agent run <id> [--task-type <t>] [task...]    # On-demand 调起：渲染 AGENT.md + 任务框架并自动复制到剪贴板
```

### `agent run` — on-demand 调起

**何时用它**：用户想绕过 orchestrator 自动判定，手动激活通常只走调度路由的 agent（如 `reflector` 跑阶段性 retro、`debugger` 调框架脚本）。

**做什么**：渲染标准 prompt payload（AGENT.md 正文 + `task_type` 框架 + 用户任务），打到 stdout 并自动复制到剪贴板（Windows `clip` / macOS `pbcopy` / Linux `xclip`/`xsel`）；粘贴到 IDE 聊天即可激活该 agent。

**不做什么**：**不发起远程调度** — sub-agent 派发是 IDE runtime 的职责（Claude Code 的 Task 工具、Cursor 的 agent mode 等）。本命令只生成 prompt，不替代 IDE 的派发链路。

**`--task-type`**：默认 `new_creation`；可选 `revision` / `continuation` / `retrospective` / `skill-improvement` / `apply-learnings` / `amendment` / `on_demand`。

**`--print-only`**：跳过剪贴板复制（CI 或缺剪贴板后端时用）。非 TTY 自动启用。

例：

```bash
cataforge agent run reflector --task-type retrospective "本周 framework-review 报告积累后的二次提炼"
cataforge agent run debugger "no-dogfood-leak.yml 总在 windows-latest red，本地复现不出"
```

---

## skill

```bash
cataforge skill list                          # 列出已发现的 Skill
cataforge skill run <id> [--agent <name>] -- ...  # 执行指定 Skill 并转发参数
```

`--agent` 标识本次调用方，会作为 `agent` 字段写入 EVENT-LOG（仅当 skill 为 review-class、即 `record_to_event_log: true` 时；目前是 `code-review` / `doc-review` / `sprint-review` 三个内置 + 任何 `record-to-event-log: true` 的项目自定义 skill）。也可以一次性 `export CATAFORGE_INVOKING_AGENT=<name>` 让多次调用统一归因。两者都缺省时回退为 `reviewer`（保持历史行为）。

`--` 之后的参数原样转发给 skill 脚本。code-review 的 Layer 1 是显式双子命令：

```bash
cataforge skill run code-review -- review <path> [--fix] [--focus <category[,...]>] [--format text|json]
cataforge skill run code-review -- scan <path> [--focus <category[,...]>] [--format text|json]
```

退出码 0=PASS / 1=有 gating finding / 2=用法错误（未知参数与非法 `--focus` 值不静默忽略）。项目 override 脚本须实现同一契约，见 [`overrides.md`](./overrides.md#项目-override-脚本的-cli-契约)。

---

## hook

```bash
cataforge hook list         # 列出 hooks.yaml 中定义的 hook
cataforge hook test <name>  # 测试指定 hook（接受 --fixture 文件或 --inline JSON）
```

Hook 按事件分组：`PreToolUse` / `PostToolUse` / `Stop` / `Notification` / `SessionStart`。

例：

```bash
# 用 inline JSON 喂一个 PostToolUse 事件
cataforge hook test PostToolUse --inline '{"tool_name":"Edit","file_path":"src/cataforge/interface/cli/__init__.py"}'

# 或用 fixture 文件
cataforge hook test PreToolUse --fixture tests/fixtures/pretool-edit.json
```

**自定义 hook 命令的 `shell=True` 边界**：内置 `python -m ...` hook 命令走 argv 列表（`shell=False`），不受 shell 元字符影响。但 `hooks.yaml` 里**自定义命令字符串**（不以 `python` 开头的那种）会走 `shell=True`，以保留管道 / 重定向 / 环境变量展开等常见用法。威胁模型：hook 命令字符串由仓库维护者直接写入 `hooks.yaml`，**不接收任何来自工具调用结果的外部输入**——payload 通过 stdin 传给子进程，而非拼到命令行——所以 `shell=True` 在这条调用面上不构成命令注入风险。如果你的自定义命令需要消费 payload，请让子进程从 stdin 读取，**不要**把 payload 字段拼进 `hooks.yaml` 的命令字符串。

---

## mcp

```bash
cataforge mcp list                       # 列出已注册的 MCP 服务
cataforge mcp register <spec.yaml>       # 注册（拷贝到 .cataforge/mcp/<id>.yaml；--force 覆盖）
cataforge mcp start <id>                 # 启动 MCP 服务（含 readiness 探测）
cataforge mcp stop <id>                  # 停止 MCP 服务（SIGTERM → wait → SIGKILL）
cataforge mcp health <id>                # 主动探测健康，写回 last_health_check
```

声明位置：`.cataforge/mcp/*.yaml`；状态持久化到 `.cataforge/.mcp-state/`。

**生命周期保证**：

- `register` 把 spec 标准化复制到 `.cataforge/mcp/<id>.yaml`，新进程通过目录扫描自动可见
- `start` 先读持久化 state + 校验 pid 存活（POSIX `kill 0` / Windows `OpenProcess`）：活的复用、死的清理重启；spawn 后跑一次 readiness 探测把结果写回 `last_health_check`
- `stop` SIGTERM 后等 pid 真消失才标 stopped，超时升级 SIGKILL（POSIX），仍存活写 `error`
- `health` 按 `spec.health_check.type` 分派：`http` → `GET` 目标 URL（2xx 即健康）；`tcp` → `socket.connect("host:port")`；`command` → shell 执行（exit 0 即健康）；缺省 → pid alive 兜底。Unhealthy 时 CLI exit 1

例：

```bash
cataforge mcp list
# echo-mcp     stopped
# cataforge-files  stopped

cataforge mcp start echo-mcp
# Started: echo-mcp (pid=12345)

cataforge mcp health echo-mcp
# Server : echo-mcp
# Status : running
# Health : 2026-05-24T03:21:00+00:00|healthy|pid_alive=True (pid=12345)

cataforge mcp stop echo-mcp
# Stopped: echo-mcp
```

---

## plugin

```bash
cataforge plugin list                      # 列出已发现的插件
cataforge plugin install ./path/to/plugin  # 本地目录拷入 .cataforge/plugins/<id>/
cataforge plugin install some-pip-package  # pip 包安装（需声明 cataforge.plugins entry point）
cataforge plugin remove <id-or-package>    # 本地删目录 / pip 卸载
```

发现来源：Python entry points (`cataforge.plugins`) + 本地目录 `.cataforge/plugins/*/cataforge-plugin.yaml`。`install` 对带 `cataforge-plugin.yaml` 的本地目录做拷贝（已存在加 `--force`），否则按 pip 包安装；装/删后跑 `cataforge deploy` 落地或清除资产。完整布局与 `provides_*` 见 [`plugins.md`](./plugins.md)。

---

## override

在升级免疫的覆盖层定制框架 agent / skill，支持整文件覆盖与 section 补丁（覆盖已有 section + 新增 section）。

```bash
cataforge override list                                   # 每个 asset 由哪些层定义
cataforge override eject agents architect                 # 从发货层导出起点（project 层、整文件）
cataforge override eject agents architect --layer user --patch --section "Execution Rules"
```

| 参数 | 作用 |
| ------ | ------ |
| `--layer project\|user` | 写入哪一层（默认 `project`；`user` 优先级更高） |
| `--patch` | 生成 `<name>.patch.md` section 补丁骨架，而非整文件拷贝 |
| `--section <标题>` | 配合 `--patch`，把该 section 的当前正文塞进骨架 |
| `--force` | 覆写已存在的覆盖文件 |

优先级 `user > project > 发货层 > builtin`。完整语义见 [`overrides.md`](./overrides.md)。

---

## upgrade

```bash
cataforge upgrade check      # 对比已装包版本与项目 scaffold 版本
cataforge upgrade apply      # 刷新 scaffold（保留用户字段）
cataforge upgrade verify     # 别名：cataforge doctor
cataforge upgrade rollback   # 回滚到上一次 apply 前的快照
```

### upgrade check

对比安装的 `cataforge` 包版本与项目 `.cataforge/framework.json` 的 `version`，不一致时提示刷新命令；若 `CHANGELOG.md` 中落在升级区间内的版本含 `### BREAKING` 段，会以黄字警告版本号与第一条要点。

### upgrade apply

刷新 `.cataforge/` 脚手架。**执行前**自动把当前 `.cataforge/`（不含 `.backups/` 自身）快照到 `.cataforge/.backups/<YYYYMMDD-HHMMSS>/`。

| 参数 | 作用 |
|------|------|
| `--dry-run` | 逐文件列出 `[new]` / `[unchanged]` / `[update]` / `[user-modified]` / `[preserved]` 分类，不写盘 |

> 保留字段：`framework.json` 的 `runtime.platform` / `upgrade.state`、整个 `PROJECT-STATE.md`。其它文件按 manifest 哈希分类：未改动的整体刷新，手改过的保留并把新版写成 `<文件名>.cataforge-new` — 详见 [`../guide/upgrade.md`](../guide/upgrade.md)。

### upgrade rollback

从 `.backups/` 下的快照恢复 `.cataforge/`。回滚前会把当前状态再次快照到 `.backups/pre-rollback-<ts>/`，所以 rollback 本身也可再 rollback。

| 参数 | 作用 |
| ------ | ------ |
| `--list` | 列出所有快照，最新在前，然后退出 |
| `--from <TS_OR_PATH>` | 指定快照：时间戳目录名（如 `20260424-150030`）或绝对路径；默认恢复最新 |
| `--yes` / `-y` | 跳过交互式确认 |

```bash
cataforge upgrade rollback --list
cataforge upgrade rollback --from 20260424-150030 --yes
```

### upgrade verify

`cataforge doctor` 的别名，执行 `migration_checks` 段落声明的全部检查项。任一 FAIL 返回码 1，可作 CI gate。

详见 [`../guide/upgrade.md`](../guide/upgrade.md)。

---

## context

文档与上下文 I/O 的统一入口，后端（知识图谱 / 文件）由 `context.strategy` 透明路由。

```bash
cataforge context read <ref>   # 按 {doc_id}#§{section} 精准加载段落/条目
cataforge context index        # 构建 / 刷新 docs/.doc-index.json
cataforge context validate     # 只读校验索引完整性（CI gate；exit 0=干净，3=有问题）
```

文档引用格式详见 [`status-codes.md`](./status-codes.md) §文档引用格式。

例：

```bash
cataforge context read 'arch#§3.M-auth'        # 加载架构文档第 3 节 Module auth
cataforge context read 'prd#§2.F-003'          # 加载 PRD 第 2 节 Feature F-003
cataforge context read 'dev-plan#§1.T-005'     # 加载开发计划第 1 节 Task T-005
```

写入生命周期（`write` / `write-narrative` / `transact` / `update` / `delete` / `finalize` / `ingest` / `reconcile`）见 `cataforge context --help`。`update` 就地合并实体 slot（保 part_of / source_doc），`delete` 删除实体（可级联入向边）；二者仅 `context.mode = graph` 可用。

## docs

```bash
cataforge docs list             # 列出已发现的文档
cataforge docs migrate-nav      # 迁移 legacy docs/NAV-INDEX.md → docs/.doc-index.json
cataforge docs migrate-reviews  # 回填历史审查报告的 YAML front matter
```

`load` / `index` / `validate` 是 `context read` / `index` / `validate` 的废弃别名（stderr 打印废弃提示，行为不变）。

---

## kg

**何时用它**：管理 RocksDB-backed Oxigraph 知识图谱 — 业务文档（PRD / ARCH / TEST-REPORT）实体与追溯关系的权威存储。`kg_active_doc_types` 中的 doc_type 走图查询路径，未列入的 doc_type 仍走 [`cataforge context read`](#context) legacy 路径。

```bash
cataforge kg init                                # 初始化 store + bootstrap rdfs:subClassOf
cataforge kg import [--doc-type prd ...]         # 底层六阶段管道（业务用 context ingest）
cataforge kg validate [--shacl]                  # 孤儿节点、断裂追溯边、可选 SHACL 校验
cataforge kg export [--output-dir docs]          # 底层 KG → Markdown（业务用 context finalize）
cataforge kg drift-check [--doc-type ...]        # 底层漂移诊断：md ⊕ kg → missing / ghost（业务门禁用 context reconcile）
cataforge kg repair [--dry-run]                  # 自动修复 reconcile 发现的漂移
cataforge kg compare-read [--sample-size 20]     # 抽样审计：KG 渲染 vs 源文件 slice
cataforge kg snapshot [--label ...]              # 写完整 NQuads 快照到 .cataforge/kg/snapshots/
cataforge kg rollback <snapshot_path>            # 从快照恢复 store
cataforge kg query <sparql-or-file>              # 执行 SPARQL（含超时控制）
cataforge kg trace <entity_id> [--coverage]      # 追溯链 + 覆盖矩阵（table / json / mermaid）
cataforge kg add <entity_id> --class ...         # 新增单实体 + 可选 outgoing 边
cataforge kg update <entity_id> [--title ...]    # 更新现有实体的 slot
cataforge kg delete <entity_id> [--cascade]      # 删除实体（可级联入向边）
```

### kg init

初始化空 store 并加载 `rdfs:subClassOf` 闭包三元组 — pyoxigraph 无 RDFS entailment，没有这层三元组 `?s a/rdfs:subClassOf* cf:Screen` 这类子类枚举会返回零行。

| 参数 | 作用 |
| ------ | ------ |
| `--db-path <path>` | RocksDB store 目录（默认 `.cataforge/kg/store`） |
| `--backend oxigraph\|memory` | 后端选择（`memory` 仅测试） |
| `--governance` | 同时 bootstrap 治理子本体的类层级 |
| `--force` | 覆盖已存在的 store |

### kg import

按六阶段管道导入业务文档：scan → parse → entity extraction → relation extraction → write → verify。幂等设计（IRI 由 entity ID 确定性派生，mtime 守卫跳过未变更实体）。

| 参数 | 作用 |
| ------ | ------ |
| `--project-root <path>` | 项目根（含 `docs/` 与 `.cataforge/`，默认 CWD） |
| `--doc-type <id>` | 限定 doc_type（可重复，默认 `prd / arch / test-report`） |
| `--dry-run` | 跑阶段 1–4 + 6，跳过 phase 5 写入 |
| `--json` | 输出 JSON stats blob |

### kg validate

| 参数 | 作用 |
|------|------|
| `--shacl / --no-shacl` | 跑 `_generated/core_shapes.ttl`（需 pyshacl + rdflib，缺则静默跳过） |
| `--json` | 输出 JSON 违例报告 |

### kg export

KG → 每实体一份 Markdown，幂等：两次连续 export 字节相同。

| 参数 | 作用 |
|------|------|
| `--output-dir <path>` | 输出根（默认 `docs/`） |
| `--json` | 输出每文件 sha256 的 JSON |

### kg drift-check

底层 per-doc_type 对称差诊断：Markdown 与 KG 的对称差。任一 `missing` / `ghost` 条目存在则 exit 3（见 §退出码）。这是 store 机械诊断；业务漂移门禁用 [`context reconcile`](#context)，按文档级 triage 判定通过/失败。

| 参数 | 作用 |
| ------ | ------ |
| `--doc-type <id>` | 限定 doc_type（默认 `framework.json.kg.kg_active_doc_types`） |
| `--report-output <path>` | JSON 报告路径（默认 `docs/.kg-reconcile-report.json`） |
| `--json` | 同时把报告打到 stdout |

### kg query

| 参数 | 作用 |
| ------ | ------ |
| `query_or_file` | SPARQL 字符串或 `.sparql` 文件路径 |
| `--output table\|json\|turtle` | 输出格式 |
| `--limit <N>` | SELECT 行上限（默认 100，自动注入） |
| `--timeout <secs>` | 查询超时（默认 30s） |

### kg trace

```bash
cataforge kg trace F-001 --direction both --coverage
cataforge kg trace --coverage                       # 全局 Feature 覆盖矩阵（不带 ENTITY_ID）
cataforge kg trace F-001 --output json > trace.json
```

| 参数 | 作用 |
| ------ | ------ |
| `ENTITY_ID` | 业务实体（缺省时配合 `--coverage` 输出全局矩阵） |
| `--direction downstream\|upstream\|both` | 链方向 |
| `--coverage` | 追加覆盖矩阵（has_impl / has_test） |
| `--output table\|json` | 输出格式（追溯图的 mermaid 已迁移到 [`cataforge viz trace`](#viz)） |

### kg add

新建一个实体（含可选 outgoing 关系边）。幂等：相同 `--content-hash` 重跑为 no-op；不同 hash 原子替换该实体的全部 quad。store 中无 `cf:Project` 节点时必须传 `--project-id`；唯一 Project 时自动选用。

```bash
cataforge kg add F-010 --class Feature --title "Profile edit" \
  --source-doc prd --source-section "F-010 Profile edit" \
  --project-id proj-myapp --slot cf:priority=high \
  --relation cf:implements=F-001
```

| 参数 | 作用 |
| ------ | ------ |
| `ENTITY_ID` | 实体 ID（如 `F-001` / `TC-042`） |
| `--class <name>` | 必填 schema class（`Feature` / `Module` / `TestCase` 等） |
| `--title <text>` | 必填可读标题 |
| `--source-doc <id>` | 来源 doc_id（默认空串） |
| `--source-section <text>` | 来源 section 标题（默认 `ENTITY_ID + title`） |
| `--content-hash <hex>` | 幂等键（默认 sha256(`source_doc \| source_section \| title`)） |
| `--project-id <id>` | 父 Project entity_id（store 中唯一 Project 时可省） |
| `--project-title <text>` | 仅在 `--project-id` 物化新 Project 节点时使用 |
| `--project-process waterfall\|agile` | 同上 |
| `--slot KEY=VALUE` | 额外 slot（可重复，KEY 可带 `cf:` 前缀） |
| `--relation PRED=OBJECT_ID` | outgoing 边（可重复） |
| `--json` | 输出 JSON status blob |

### kg update

更新现有实体的 slot。实体不存在时 exit 1。`--content-hash` 与 store 已有值相同则整次更新短路（用于幂等同步场景）。

```bash
cataforge kg update F-010 --title "Profile edit (v2)" --slot cf:priority=critical
```

| 参数 | 作用 |
| ------ | ------ |
| `ENTITY_ID` | 必填 |
| `--title <text>` | 新 title |
| `--source-section <text>` | 新 source_section |
| `--slot KEY=VALUE` | slot 更新（可重复） |
| `--content-hash <hex>` | 新 content_hash（与现有相同则跳过） |
| `--json` | 输出 JSON status blob |

至少需提供 `--title` / `--source-section` / `--slot` / `--content-hash` 之一，否则 exit 1。

### kg delete

删除一个节点（默认禁止删除有入向边的节点；`--cascade` 同时移除入向边）。默认走 stdin 交互确认；脚本场景用 `--yes`。

```bash
cataforge kg delete F-010 --cascade --yes
cataforge kg delete "doc/arch/sec/§2 Modules" --cascade --yes
```

| 参数 | 作用 |
| ------ | ------ |
| `ENTITY_ID` | 必填，按形态解析：扁平实体 id（`F-001`）/ 父域从属 id（`F-001/AC-002`）/ 结构节点 id（`doc/{doc_id}` 为 Document、`doc/{doc_id}/sec/{anchor}` 为 Section）/ 完整 http(s) IRI |
| `--cascade` | 同时移除入向边（无此 flag 且存在入向边时 exit 1） |
| `--yes` | 跳过交互确认 |
| `--json` | 输出 JSON status blob |

> KG 校验门失败统一退出码 `3`（见 §退出码）。`KGStoreError` / `KGStoreNotInitializedError` / CRUD 参数错误走 `1`。

---

## event

**何时用它**：编排器或自定义脚本需要向 `docs/EVENT-LOG.jsonl` 追加一条审计事件。

```bash
# 单条写入
cataforge event log --event phase_start --phase development --agent implementer \
  --status started --ref "dev-plan#§1.T-005"

# 从 stdin 批量原子写入 JSONL
cat events.jsonl | cataforge event log --batch
```

| 参数 | 作用 |
| ------ | ------ |
| `--event <type>` | 事件类型（`phase_start` / `phase_end` / `agent_dispatch` / `review_verdict` / `state_change` / `correction` …） |
| `--phase <name>` | 阶段名 |
| `--agent <id>` | Agent ID |
| `--status <code>` | 状态码（参考 [`status-codes.md`](./status-codes.md) §1） |
| `--task-type <type>` | 任务类型（`continuation` / `revision` / 其它） |
| `--ref <doc-ref>` | 关联文档段落引用 |
| `--detail <text>` | 自由文本细节 |
| `--data <json>` | 结构化 payload（JSON 字符串） |
| `--batch` | 从 stdin 读 JSONL，原子批量追加 |

事件类型与示例 payload 见 [`status-codes.md`](./status-codes.md) §5。

---

## correction

**何时用它**：用户/Agent 修正了上游建议、推荐选项或框架默认行为时，把这一条偏离记入 `docs/reviews/CORRECTIONS-LOG.md` 与 `docs/EVENT-LOG.jsonl` 双写。`option-override` / `review-flag` 由 hook 自动捕获，CLI 主要服务于 `interrupt-override`（手动打断）以及任何需要程序化记录的场景。

```bash
cataforge correction record \
  --trigger interrupt-override \
  --agent orchestrator \
  --phase architecture \
  --question "选 Node 版本" \
  --baseline "B: 18 LTS" \
  --actual "C: 22 LTS" \
  --deviation self-caused
```

| 参数 | 作用 |
| ------ | ------ |
| `--trigger` | 触发信号 (`option-override` / `interrupt-override` / `review-flag`) |
| `--agent` | 发起 Agent ID |
| `--phase` | 协议阶段（`architecture` / `implementation` / `review` …） |
| `--question` | 被纠偏的问题 / 假设 |
| `--baseline` | 上游推荐值 / baseline |
| `--actual` | 用户/实际选择 |
| `--deviation` | 偏差类型（`preference` / `self-caused` / `external` / `framework-bug` / `upstream-gap`） |
| `--no-event-log` | 仅写 CORRECTIONS-LOG，不双写 EVENT-LOG |

`deviation` 五个值的语义边界：

| 值 | 含义 | 触发后续 |
| ---- | ------ | ---------- |
| `preference` | 纯偏好，不算缺陷 | 仅留存档 |
| `self-caused` | 下游自身造成的偏离 | 累计 ≥ `RETRO_TRIGGER_SELF_CAUSED` (默认 5) → reflector 回顾 |
| `external` | 外部约束（依赖、政策） | 仅留存档 |
| `framework-bug` | CataForge 框架本体缺陷 | 由 `cataforge feedback bug` 上报 |
| `upstream-gap` | 上游 baseline 本身对此项目场景不准/不全 | 累计 ≥ `RETRO_TRIGGER_UPSTREAM_GAP_DEFAULT` (默认 3) → `cataforge feedback correction-export` 聚合上报 |

---

## feedback

**何时用它**：在下游项目使用 CataForge 时发现框架问题 / 改进点 / 累积的 `upstream-gap` 纠偏，把本地诊断聚合为 markdown 直接发给 CataForge 上游。三个子命令共享同一份输出 sink。

```bash
# 1. bug：聚合 doctor + EVENT-LOG + upstream-gap + framework-review FAIL
cataforge feedback bug --summary "deploy 后 hook 不触发" --gh

# 2. suggest：建议类反馈（不带 doctor 噪声）
cataforge feedback suggest --summary "希望 bootstrap 支持 --dry-run" --clip

# 3. correction-export：累计的 upstream-gap 批量回报
cataforge feedback correction-export --threshold 3 --out docs/feedback/$(date +%Y%m%d).md
```

| 参数 | 作用 |
| ------ | ------ |
| `--summary <text>` | 一句话摘要（省略时从 stdin 读，主用于 pipeline） |
| `--title <text>` | issue 标题（省略时由 kind + summary 合成） |
| `--notes <text>` | 自由文本，附在 `## Additional notes` 段 |
| `--print` | 把渲染好的 markdown 写到 stdout（默认 sink） |
| `--out <path>` | 写到文件（相对路径解析在项目根下） |
| `--clip` | 推到剪贴板（`pbcopy` / `wl-copy` / `xclip` / `xsel` / `clip`，按 PATH 顺序选第一个可用） |
| `--gh` | 直接 `gh issue create --body-file -`（需要本机已装并登录 `gh`） |
| `--include-paths` | 关闭路径脱敏（默认会把 `<project>` 与 `~` 替换为占位符） |
| `--since <YYYY-MM-DD>` | 只聚合该日期及之后的 EVENT-LOG / corrections（`bug` / `correction-export`） |
| `--event-limit <N>` | EVENT-LOG 截取条数，默认 20，0 = 不限（`bug`） |
| `--threshold <N>` | `correction-export` 的最小 `upstream-gap` 计数，默认 3，0 = 永远导出 |
| `--skip-framework-review` | `bug` 跳过 `framework-review` 预检（脚手架已损坏时可加快产出） |
| `--quiet` | 抑制 sink 完成后的提示（`Wrote ...` / `Copied ...`），`--gh` 仍会打印 issue URL |

四个 sink 互斥；都不指定时默认 `--print`。

**等价 skill 入口**：`cataforge skill run framework-feedback -- <kind> [--summary ...] [--out ...]`。CLI 与 skill 共用 `cataforge.core.feedback` 同一份 assembler，区别仅在 skill 调用会向 EVENT-LOG 写一条 `state_change`（`ref=skill:framework-feedback/...`），便于 orchestrator 跟踪反馈频次。

**隐私与脱敏**：默认对 `<project>` / `~` 做替换，`--include-paths` 仅在内部反馈或自托管 GitHub 时启用。`--gh` 通过 stdin 把 body 喂给 `gh`，不落临时文件。

**配套 issue 模板**：上游仓库 `.github/ISSUE_TEMPLATE/feedback-from-cli.yml` 字段与 CLI 输出 1:1 对齐。

---

## viz

**何时用它**：想把框架编排结构或项目结构导出为可被版本化、可内联进文档的图。复用既有数据源（framework.json 路由 + agent/skill 资产），输出确定性文本，无运行时依赖。

```bash
# 一键上手：先看哪些视图现在有数据，再一条命令起本地实时 dashboard
cataforge viz status                       # 视图就绪体检：ready / empty / needs setup + 缺啥补啥
cataforge viz quickstart                   # 生成 + 本地服务 + 自动开浏览器 + 监听源数据变更

# 编排图 orchestrator → phase → agent → skill（Mermaid，默认 stdout）
cataforge viz framework

# 资产图：全部 agent + skill 目录与依赖（agent→skill / skill→skill）
cataforge viz assets

# 追溯图：单实体或省略 ID 聚合全部 Feature
cataforge viz trace F-001
cataforge viz trace --direction both
cataforge viz trace                       # 聚合全部 Feature 的下游链

# Feature 覆盖矩阵（节点按 impl/test 状态着色）
cataforge viz coverage

# arch 依赖图（Module/Component/API/DataModel + depends_on）
cataforge viz arch

# 文档依赖图（doc-index deps；stale 上游 / 断裂 xref 高亮）
cataforge viz docs

# 任务依赖图（关键路径 / 环高亮）
cataforge viz tasks --edges "T-001→T-002,T-002→T-003" --weights "T-001:S,T-003:L"
cataforge viz tasks                       # 省略 --edges 时从 KG Task.depends_on 取数

# SDLC 阶段进度（当前阶段着色：门禁通过=绿 / 受阻=红）
cataforge viz phase

# EVENT-LOG 时间线 / CORRECTIONS-LOG 腐化时间线（mermaid timeline）
cataforge viz timeline
cataforge viz decay

# 切换输出格式 / 写文件
cataforge viz framework --format dot
cataforge viz coverage --format json -o docs/viz/coverage.json

# 自包含离线 HTML（Graph→Cytoscape.js / 时间线·指标→ECharts，覆盖 --format）
cataforge viz framework --html -o docs/viz/framework.html
cataforge viz assets --html -o docs/viz/assets.html      # 带节点搜索框
cataforge viz timeline --html -o docs/viz/timeline.html

# dashboard：把全部可用视图聚合进单文件多标签离线页（恒为 HTML）
cataforge viz dashboard -o docs/viz/index.html
cataforge viz dashboard --open                       # 无 -o 时写 docs/viz/dashboard.html 并开浏览器

# 本地静态服务：托管产物目录（默认 docs/viz/，Ctrl-C 停止）
cataforge viz serve
cataforge viz serve --watch --open                   # 源数据变更自动重生成 + 就绪后开浏览器
cataforge viz serve --dir docs/viz --host 0.0.0.0 --port 9000
```

| 参数 | 作用 | 适用 view |
| ------ | ------ | ---------- |
| `--format <mermaid\|dot\|json>` | 文本渲染器，默认 `mermaid`。`mermaid` 在 GitHub / IDE / 文档站原生渲染；`dot` 交给本地 graphviz；`json` 为稳定外部契约 | 全部（`dashboard` 除外） |
| `--html` | 输出自包含离线 HTML（内联 vendored JS，零外链）：Graph 走 Cytoscape.js（zoom/pan/搜索），Timeline/MetricSeries 走 ECharts。覆盖 `--format` | 全部单视图 |
| `-o, --output <path>` | 写到 PATH（自动建父目录）而非 stdout | 全部 |
| `--direction <downstream\|upstream\|both>` | 追溯方向，默认 `downstream` | `trace` |
| `--edges "A→B,B→C"` | 任务依赖边列表 | `tasks` |
| `--weights "A:S,B:M"` | 任务复杂度权重（S/M/L/XL），驱动关键路径长度 | `tasks` |

视图说明：

| view | 内容 | 数据源 |
| ------ | ------ | -------- |
| `status` | 视图就绪体检：逐视图标 `ready` / `empty` / `needs setup`，并给出缺啥补啥的命令（如 `run: cataforge kg init`） | 探测全部 collector（不渲染） |
| `quickstart` | 一键起本地实时 dashboard，等价 `viz serve --watch --open` | 同 `serve` |
| `framework` | orchestrator → phase → agent → skill 编排图（仅 standard 路由的 agent） | framework.json `workflow.modes.standard` + agent frontmatter `skills` |
| `assets` | 全量 agent + skill 目录图：agent→skill 与 skill→skill 依赖边（`--html` 下带搜索框） | `AgentManager` + `SkillLoader`（builtins + 项目覆写） |
| `trace` | 追溯链图（需求→模块→任务→测试）；省略 ENTITY_ID 聚合全部 Feature | KG `TraceAPI`（需先 `cataforge kg init` + `kg import`） |
| `coverage` | Feature 覆盖矩阵，每个 Feature 一个节点，按 impl/test 状态着色 | KG `bidirectional_coverage()` |
| `arch` | arch 层实体（Module/Component/API/DataModel）+ 层内 `depends_on` 边 | KG `QueryAPI` |
| `docs` | 文档依赖有向图；stale 上游标节点样式 + `stale` 边、断裂 xref 标 `xref-error` 边 | `docs/.doc-index.json`（需先 `cataforge context index`） |
| `tasks` | 任务 DAG，关键路径或环节点高亮 | `--edges` / `--weights`（authoring 时刻）；省略时读 KG `Task.depends_on`（同 `task-dep-analysis` 图算法） |
| `phase` | SDLC 阶段骨架，当前阶段按门禁结论着色（绿=通过 / 红=受阻），结论与 `cataforge phase status` 一致 | `evaluate_phase()` + framework.json `workflow.modes.standard` |
| `timeline` | EVENT-LOG 事件时间线（按日期分组的 mermaid `timeline`） | `docs/EVENT-LOG.jsonl`（容错解析，跳过坏行） |
| `decay` | CORRECTIONS-LOG 腐化时间线，每条纠偏一个事件 | `docs/reviews/CORRECTIONS-LOG.md` |
| `dashboard` | 把上述全部视图聚合进单文件多标签离线页（恒为 HTML；取不到数据的视图降级为错误面板，不中断） | 上述全部 collector |

`trace` / `coverage` / `arch` 读 KG store；store 未初始化时优雅退出并提示 `cataforge kg init`。`docs` 读 doc-index；未建索引时提示 `cataforge context index`。`phase` 读项目指令文件；非 CataForge 驱动项目优雅退出。`timeline` / `decay` 渲染为 mermaid `timeline`（`dot` 仅支持 Graph 视图，对时间线视图会报错，用 `mermaid` 或 `json`）。**mermaid 收编**：追溯图的 mermaid 表面从 `kg trace --output mermaid` 迁移到 `cataforge viz trace`（`kg trace` 保留 `table` / `json` 分析）；任务依赖图的 mermaid 从 `task-dep-analysis --format mermaid` 迁移到 `cataforge viz tasks --format mermaid`（`task-dep-analysis` 保留 `--format json` 分析）。

**自包含 HTML（`--html`）**：输出单文件离线页，vendored `cytoscape.min.js` / `echarts.min.js` 经 `importlib.resources` 内联，零外链——断网双击即开。渲染器纯按 IR 形态分发：Graph → Cytoscape.js（zoom / pan / 节点搜索），Timeline / MetricSeries → ECharts。`dashboard` 共享两库一次内联、各视图分标签页。`--html` 与 `--format` 互斥，同时给出时 `--html` 生效。

**就绪体检与一键（`viz status` / `viz quickstart`）**：新用户先跑 `viz status` —— 它逐视图探测数据源，输出 `ready`（已有数据，带节点/事件计数）/ `empty`（能渲染但暂无数据）/ `needs setup`（数据源缺失，并从 collector 自带提示里抽出 `run: cataforge kg init` 这类可直接照抄的命令）三态，让你按需补齐想看的视图。`viz quickstart` 是到实时 dashboard 的单命令路径，等价 `viz serve --watch --open`。

**本地静态服务（`viz serve`）**：用标准库 `http.server` 托管产物目录（默认 `docs/viz/`），启动时先写一份 dashboard `index.html`，再持续提供 HTTP 访问，仅依赖标准库——不引入任何服务框架。`--watch` 启动后台线程轮询 KG store / doc-index / EVENT-LOG / CORRECTIONS-LOG 的 mtime，任一变更即重生成 `index.html`，浏览器刷新即见最新。`--open` 就绪后用默认浏览器打开（监听 `0.0.0.0` 时按 `127.0.0.1` 打开）。`Ctrl-C` 干净退出。`viz dashboard --open` 在无 `-o` 时写 `docs/viz/dashboard.html` 并打开（`file://`，无服务一次性快照）。

| 参数 | 作用 | 默认 |
| ------ | ------ | ------ |
| `--dir <path>` | 托管的产物目录 | `docs/viz/` |
| `--host <addr>` | 监听地址 | `127.0.0.1` |
| `--port <n>` | 监听端口 | `8000` |
| `--watch` | 源数据变更时重生成 dashboard | 关 |
| `--open` | 就绪后用浏览器打开（`serve` / `dashboard`） | 关 |

产物默认写 `docs/viz/`（已在 `docs/.docignore` 中豁免 orphan 检查；HTML 产物另由 `.gitignore` `docs/**/*.html` 保持临时）。文本输出 stdout 时 pipe 友好，可直接喂 mermaid.live / `dot`。

---

## git

**何时用它**：PR 合并（squash）后同步本地 `main` 并清理已合并的 feature 分支；或一次性把仓库的 GitHub merge 策略设为 delete-branch-on-merge + squash-only。SessionStart `git_sync` hook 会在会话启动时自动跑同步+清理（见 [configuration.md](configuration.md#gitsession_sync)）。

```bash
cataforge git sync [--prune-gone] [--branch <name>] [--no-confirm-gh] [--yes] [--dry-run]
cataforge git prune [--branch <name>] [--no-confirm-gh] [--yes] [--dry-run]
cataforge git ensure-policy [--dry-run]
```

| 子命令 | 说明 |
| -------- | ------ |
| `git sync` | fetch 并快进本地默认分支；`--prune-gone` 同时清理 squash 合并分支。脏树 / 分叉 / detached HEAD 时拒绝并给出补救。 |
| `git prune` | 仅清理 upstream 已消失（`[gone]`）的本地分支 —— 即 squash 合并后远端 head 被删的分支，`git branch -d` 因 commit 非 ancestor 而漏判。 |
| `git ensure-policy` | 幂等设置 origin 的 GitHub merge 策略（读 `framework.json#git.remote_policy`，仅在漂移时 PATCH）。 |

| 参数 | 作用 | 默认 |
| ------ | ------ | ------ |
| `--prune-gone` | `git sync` 后清理 `[gone]` 分支（`--prune-merged` 为隐藏别名） | 关 |
| `--branch <name>` | 指定默认分支（缺省从 `origin/HEAD` 探测） | 自动 |
| `--no-confirm-gh` | 信任 `[gone]` 信号，不经 gh 二次确认 PR 是否已合并 | 关（默认确认） |
| `--yes` | 跳过删除确认提示 | 关 |
| `--dry-run` | 仅打印将执行的操作，不落盘 | 关 |

**安全语义**：默认在删除 `[gone]` 分支前经 `gh pr list --state merged` 确认其 PR 已合并（远端 head 因非合并原因消失时保留分支）；origin 非 GitHub 远程或 gh 不可用时降级为信任 `[gone]`。

合并后推荐配 `gh pr merge --squash --delete-branch`（见 [git 工作流](../../CLAUDE.md)），让远端 head 即时删除、下次 `git prune` / SessionStart hook 自动清理本地。

---

## issue

**何时用它**：维护者侧把上游仓库的 GitHub issue 拉进来分诊为 SKILL-IMPROVE 草稿，或修复落地后用模板化评论关闭。

```bash
cataforge issue triage [--repo owner/name] [--label <l>...] [--since YYYY-MM-DD] [--limit N] [--out <dir>] [--dry-run]
cataforge issue close <N> --verdict <fixed|already-fixed|wontfix> [--pr <N>] [--reason <text>] [--release-tag <tag>] [--dry-run]
```

| 子命令 | 说明 |
|--------|------|
| `issue triage` | Layer 1 分诊：从 `gh` 拉取 issue，按标签 / 状态 / 日期过滤，写出 `docs/reviews/triage/` 下的 SKILL-IMPROVE 草稿（`--dry-run` 仅打印 verdict 表）。 |
| `issue close` | 用模板化评论关闭 issue：`fixed` / `already-fixed` 需 `--pr`，`wontfix` 需 `--reason`；`--dry-run` 仅打印将发的评论。 |

`--repo` 缺省取 `framework.json#upgrade.source.repo`。完整闭环（含人工 go/no-go）见 `framework-issue-resolve` skill。

---

## penpot

**何时用它**：`design-tool: penpot` 项目需要部署 Penpot 设计稿读写能力 —— 本地 Docker 栈或托管端点 + MCP 服务。

```bash
cataforge penpot init          # 交互向导：选 Remote / Local / MCP-only 并配置
cataforge penpot deploy        # 完整部署：Penpot（Docker 栈）+ MCP 服务
cataforge penpot mcp-only      # 仅启动 MCP 服务（假定 Penpot 已在运行）
cataforge penpot remote        # 托管模式：从 PENPOT_MCP_URL 注册 MCP 端点（无 Docker/npx）
cataforge penpot start         # 启动已部署的 Penpot 服务
cataforge penpot stop          # 停止全部 Penpot 服务
cataforge penpot status        # 显示 Penpot 服务与 MCP 服务状态
cataforge penpot doctor        # 诊断 Penpot 集成故障并给修复建议
```

---

## phase

**何时用它**：只读核对当前 SDLC 阶段是否产齐预期产物（不推进、不写盘）。

```bash
cataforge phase status         # 校验当前阶段预期产物是否齐备
```

`phase status` 的门禁结论与 [`cataforge viz phase`](#viz) 着色一致；非 CataForge 驱动的项目优雅退出。

---

## claude-md

**何时用它**：项目指令文件（`CLAUDE.md` / `AGENTS.md`）体积逼近上限，或 Learnings Registry 条目超阈值需压缩归档。

```bash
cataforge claude-md check                  # 报告体积 + Learnings Registry 条目数
cataforge claude-md compact [--max N] [--dry-run]   # 裁剪 Learnings Registry，溢出条目归档
```

| 参数 | 作用 |
|------|------|
| `--max <N>` | 覆盖 `framework.json` 的 `claude_md_limits.learnings_registry_max_entries` |
| `--dry-run` | 打印压缩计划，不改文件 |

---

## 全局参数

以下参数可置于任何子命令之前，例如 `cataforge -v deploy --platform claude-code`。

| 参数 | 作用 |
| ------ | ------ |
| `--version` | 打印包版本 |
| `--help`, `-h` | 打印帮助（支持短选项） |
| `-v`, `--verbose` | 启用 `cataforge.*` logger 的 DEBUG 级别日志 |
| `-q`, `--quiet` | 仅保留错误输出（logger 级别设为 WARNING，与 `--verbose` 互斥） |
| `--project-dir <dir>` | 覆盖项目根目录探测（默认向上查找 `.cataforge/`）。影响所有子命令，包括 `agent` / `skill` / `mcp` / `plugin` / `hook` / `doctor` / `deploy` / `setup` / `upgrade`。

---

## 退出码

| 退出码 | 含义 | 典型场景 |
| ------- | ------ | ---------- |
| `0` | 成功 | 正常完成 |
| `1` | 通用失败 | `doctor` 发现 FAIL；验证不通过；缺少前置条件（如 `.cataforge/` 未初始化）；配置错误 |
| `2` | Click 用法错误 | 未知选项、缺少必需参数、参数类型不符（由 Click 自动使用） |
| `3` | KG 内容校验门失败 | `kg import` 校验失败、`kg validate` 报违例、`kg export` 渲染错误、`kg drift-check` 检测到 doc↔store 漂移；由 `CataforgeError` 子类 `KGVerificationError` 抛出。与 `1` 分开是为了让 CI 能在 "数据真有问题" 与 "环境没准备好" 之间分别动作 |
| `6` | SPARQL 查询超时 | `kg query` 超出配置的查询超时；由 `CataforgeError` 子类 `KGQueryTimeoutError` 抛出 |
| `70` | 功能未实现（stub） | `plugin install` / `plugin remove` 等路线图占位命令；由 `CataforgeError` 子类 `NotImplementedFeature` 抛出 |

> `70` 选自 BSD sysexits.h `EX_SOFTWARE`，刻意避开 Click 自动使用的用法错误码 `2`，让 CI 脚本能区分"未实现"与"命令用错"。常量定义在 [`cataforge.interface.cli.errors.EXIT_NOT_IMPLEMENTED`](../../src/cataforge/interface/cli/errors.py)。

所有非零退出均以统一的 stderr 前缀 `Error: …` 输出（`click.ClickException` 渲染），便于 CI/脚本捕获。

---

## 参考

- 配置文件清单：[`configuration.md`](./configuration.md)
- 状态码：[`status-codes.md`](./status-codes.md)
- 端到端验证：[`../guide/manual-verification.md`](../guide/manual-verification.md)
