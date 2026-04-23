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

---

## doctor

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
cataforge hook test <name>  # 测试指定 hook（v0.2+）
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
# cataforge plugin install   # 规划中 (v0.3)
# cataforge plugin remove    # 规划中 (v0.3)
```

发现来源：Python entry points (`cataforge.plugins`) + 本地目录 `.cataforge/plugins/*/cataforge-plugin.yaml`。

---

## upgrade

```bash
cataforge upgrade check     # 对比已装包版本与项目 scaffold 版本
cataforge upgrade apply     # 刷新 scaffold（保留用户字段）
cataforge upgrade verify    # 别名：cataforge doctor
```

详见 [`../guide/upgrade.md`](../guide/upgrade.md)。

---

## docs

```bash
cataforge docs list         # 列出已发现的文档
cataforge docs load <ref>   # 按 {doc_id}#§{section} 精准加载段落
```

文档引用格式详见 [`status-codes.md`](./status-codes.md) §文档引用格式。

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
