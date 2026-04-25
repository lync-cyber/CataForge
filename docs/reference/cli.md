# CLI 参考

> `cataforge` 命令的全部子命令与关键参数。完整帮助请用 `cataforge <cmd> --help`。

## 命令总览

| 命令 | 说明 |
|------|------|
| [`cataforge doctor`](#doctor) | 健康诊断，可作 CI gate |
| [`cataforge setup`](#setup) | 初始化项目、设定运行时平台 |
| [`cataforge deploy`](#deploy) | 投放资产到目标平台 |
| [`cataforge agent`](#agent) | Agent 发现与校验 |
| [`cataforge skill`](#skill) | Skill 发现与执行 |
| [`cataforge hook`](#hook) | Hook 列表与测试 |
| [`cataforge mcp`](#mcp) | MCP 服务注册与生命周期 |
| [`cataforge plugin`](#plugin) | 插件发现 |
| [`cataforge upgrade`](#upgrade) | 脚手架升级与校验 |
| [`cataforge docs`](#docs) | 文档索引与段落加载 |
| [`cataforge event`](#event) | 写事件日志 |

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
|------|------|
| `--platform <id>` | 目标平台：`claude-code` / `cursor` / `codex` / `opencode` |
| `--force-scaffold` | 强制刷新 scaffold（保留用户字段），等价于 `upgrade apply` |
| `--deploy` | 初始化后立即部署（默认不部署） |
| `--dry-run` | 预演将要做的变更，不写盘 |
| `--check` / `--check-only` | 仅检查前置条件，不安装（互为别名） |
| `--show-diff` | 打印 framework.json 将变更的字段 |
| `--no-deploy` | ⚠️ **已弃用**（v0.3 移除）：不部署已是默认行为，无需显式传入 |

> 自 v0.1.2 起，`setup` 默认**只** 初始化 `.cataforge/` 脚手架与记录目标平台，**不再**自动写入 IDE 产物。

---

## deploy

**何时用它**：`setup` 后写入 IDE 产物；或 `.cataforge/` 内容改动后重新投放。

```bash
cataforge deploy [--dry-run] [--platform <id>]
```

投放资产到目标平台（Agent / 规则 / Hook / MCP）。

| 参数 | 作用 |
|------|------|
| `--dry-run` | 预演，输出预期动作但不实际写盘 |
| `--platform <id>` | 临时覆盖 `framework.json` 中的平台设置（可选 `all` 部署到所有平台） |
| `--conformance` | 仅执行平台 conformance 检查 |
| `--check` | ⚠️ **已弃用**（v0.3 移除）：`--dry-run` 的别名，运行时会提示 |

多次 `deploy` 幂等；会自动清理孤儿产物。

---

## agent

```bash
cataforge agent list        # 列出已发现的 Agent
cataforge agent validate    # 校验 Agent 定义合法性
```

---

## skill

```bash
cataforge skill list        # 列出已发现的 Skill
cataforge skill run <id>    # 执行指定 Skill
```

---

## hook

```bash
cataforge hook list         # 列出 hooks.yaml 中定义的 hook
cataforge hook test <name>  # 测试指定 hook（接受 --fixture 文件或 --inline JSON）
```

Hook 按事件分组：`PreToolUse` / `PostToolUse` / `Stop` / `Notification` / `SessionStart`。

---

## mcp

```bash
cataforge mcp list          # 列出已注册的 MCP 服务
cataforge mcp start <id>    # 启动 MCP 服务
cataforge mcp stop <id>     # 停止 MCP 服务
```

声明位置：`.cataforge/mcp/*.yaml`；状态持久化到 `.cataforge/.mcp-state/`。

---

## plugin

```bash
cataforge plugin list       # 列出已发现的插件
```

发现来源：Python entry points (`cataforge.plugins`) + 本地目录 `.cataforge/plugins/*/cataforge-plugin.yaml`。

`cataforge plugin install <source>` 与 `cataforge plugin remove <id>` 仍为 stub（规划中，进度跟踪：[lync-cyber/CataForge issues](https://github.com/lync-cyber/CataForge/issues?q=is%3Aopen+plugin+install)）。届时将支持从 Git / 本地目录安装插件并写入 `pyproject.toml` 的 entry points；当前版本需手动克隆到 `.cataforge/plugins/` 下或通过 `pip install` 注册 entry point。

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

> 保留字段：`framework.json` 的 `runtime.platform` / `upgrade.state`、整个 `PROJECT-STATE.md`。其它文件整体覆盖 — 详见 [`../guide/upgrade.md`](../guide/upgrade.md)。

### upgrade rollback

从 `.backups/` 下的快照恢复 `.cataforge/`。回滚前会把当前状态再次快照到 `.backups/pre-rollback-<ts>/`，所以 rollback 本身也可再 rollback。

| 参数 | 作用 |
|------|------|
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

## docs

```bash
cataforge docs list         # 列出已发现的文档
cataforge docs load <ref>   # 按 {doc_id}#§{section} 精准加载段落
```

文档引用格式详见 [`status-codes.md`](./status-codes.md) §文档引用格式。

---

## event

**何时用它**：编排器或自定义脚本需要向 `docs/EVENT-LOG.jsonl` 追加一条审计事件。协议里长期引用的 `event_logger.py` 在 v0.1.7 起改由本命令实现（shim 保留兼容）。

```bash
# 单条写入
cataforge event log --event phase_start --phase development --agent implementer \
  --status started --ref "dev-plan#§1.T-005"

# 从 stdin 批量原子写入 JSONL
cat events.jsonl | cataforge event log --batch
```

| 参数 | 作用 |
|------|------|
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

## 全局参数

以下参数可置于任何子命令之前，例如 `cataforge -v deploy --platform claude-code`。

| 参数 | 作用 |
|------|------|
| `--version` | 打印包版本 |
| `--help`, `-h` | 打印帮助（支持短选项） |
| `-v`, `--verbose` | 启用 `cataforge.*` logger 的 DEBUG 级别日志 |
| `-q`, `--quiet` | 仅保留错误输出（logger 级别设为 WARNING，与 `--verbose` 互斥） |
| `--project-dir <dir>` | 覆盖项目根目录探测（默认向上查找 `.cataforge/`）。影响所有子命令，包括 `agent` / `skill` / `mcp` / `plugin` / `hook` / `doctor` / `deploy` / `setup` / `upgrade`。

---

## 退出码

| 退出码 | 含义 | 典型场景 |
|-------|------|----------|
| `0`  | 成功 | 正常完成 |
| `1`  | 通用失败 | `doctor` 发现 FAIL；验证不通过；缺少前置条件（如 `.cataforge/` 未初始化）；配置错误 |
| `2`  | Click 用法错误 | 未知选项、缺少必需参数、参数类型不符（由 Click 自动使用） |
| `70` | 功能未实现（stub） | `plugin install` / `plugin remove` 等路线图占位命令；由 `CataforgeError` 子类 `NotImplementedFeature` 抛出 |

> 历史版本（v0.1.x）使用退出码 `2` 表示 stub，与 Click 的用法错误冲突。v0.2 起改为 BSD sysexits 约定 `70` (`EX_SOFTWARE`)，CI 脚本可据此区分"未实现"与"用错命令"。

所有非零退出均以统一的 stderr 前缀 `Error: …` 输出（`click.ClickException` 渲染），便于 CI/脚本捕获。

---

## 参考

- 配置文件清单：[`configuration.md`](./configuration.md)
- 状态码：[`status-codes.md`](./status-codes.md)
- 端到端验证：[`../guide/manual-verification.md`](../guide/manual-verification.md)
