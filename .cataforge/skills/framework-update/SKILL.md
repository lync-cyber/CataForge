---
name: framework-update
description: "CataForge 框架同步 — 把已安装包、.cataforge/ scaffold、IDE 产物、项目初始化四层对齐到当前已验证状态。幂等、升级感知：检测包↔scaffold 版本差异，升级包并刷新 scaffold，部署 IDE 产物，运行 doctor 验证；项目未初始化时进入 Project Bootstrap，已初始化时装配执行环境并交接 start-orchestrator。当用户提到 CataForge 升级、scaffold 过期、框架版本不一致、bootstrap 或刷新项目脚手架、初始化/恢复项目时，使用此 skill。"
argument-hint: "[check | apply [--dry-run] [--upgrade-package] | verify]"
suggested-tools: shell_exec, file_read, file_edit
depends: []
disable-model-invocation: false
user-invocable: true
---

# CataForge 框架同步 (framework-update)

## 能力边界
- 能做: 包↔scaffold 版本差异检测、pip/uv 包升级、scaffold 增量刷新、IDE 产物部署、doctor 验证、upgrade.state 簿记、项目 init/resume 分流
- 不做: 修改项目业务代码、升级操作系统依赖、跨平台 adapter 变更（由 platform-audit 负责）、内嵌 Project Bootstrap 协议（仅委托 orchestrator 执行）

## 输入规范
- 操作指令: `check`（只读检测）、`apply`（同步并初始化/恢复）、`verify`（迁移检查）
- 无参数时默认执行完整流程（check → 确认 → apply）
- `--dry-run`: 仅在 apply 中有效，预览 plan 不写盘
- `--upgrade-package`: 在 apply 中强制执行 pip/uv 包升级（缺省仅在 check 探测到包落后时升级）
- 脊柱命令 `cataforge bootstrap` 幂等自决每步 skip/run；本 skill 是其薄编排层

## 输出规范
- 版本对比（scaffold 版本 vs 已安装版本）与初始化状态（{INSTRUCTION_FILE} 是否存在）
- scaffold 刷新文件统计（写入数 / 保留数）、部署产物清单
- 迁移检查结果（PASS / SKIP / FAIL 逐项）
- upgrade.state 更新确认（框架版本字段由 deploy 阶段盖入）
- init/resume 决策与已装配的执行环境命令

---

## 操作指令

### 指令1: 版本与初始化状态检测 (check)

**Step 1: 读取当前状态**

并行执行:
```bash
cataforge upgrade check
```
```bash
python3 -c "import cataforge; print(cataforge.__version__)"
```

记录 `installed_version`（已安装包）、`scaffold_version`（`framework.json` 的 `version`）、二者是否一致，以及 `{INSTRUCTION_FILE}` 是否存在（→ 需 init / 已初始化）。

**Step 2: 报告**

```
已安装包  : <installed_version>
Scaffold  : <scaffold_version>
版本状态  : up-to-date | outdated
项目状态  : 未初始化（无 {INSTRUCTION_FILE}） | 已初始化
```

outdated 或未初始化时提示用户运行 `framework-update apply`。

---

### 指令2: 同步并初始化/恢复 (apply)

> 单一脊柱 `cataforge bootstrap`（幂等 setup→upgrade→deploy→doctor）只在 Step 3 调用一次；前置包升级、后置簿记、init/resume 分支分别包裹其前后。

**Step 1: 版本与状态前置检查**

执行指令1 取版本差异与初始化状态。若已 up-to-date 且已初始化，告知用户并询问是否仍强制刷新 scaffold（确认后继续，`cataforge bootstrap` 会自动跳过 current 步骤仅跑 doctor），否则结束。

**Step 2: 包升级（条件执行）**

仅当 Step 1 探测到包落后、或传入 `--upgrade-package` 时执行；`--dry-run` 时跳过。依次探测包管理器（短路，找到即停）:

```bash
uv tool list 2>/dev/null | grep -q cataforge && echo "uv"
```
```bash
pip show cataforge 2>/dev/null | grep -q Name && echo "pip"
```

- `uv` → `uv tool upgrade cataforge`
- `pip` → `pip install --upgrade cataforge`
- 均未探测到 → 提示用户手动升级包，**不 abort**，继续 Step 3 仅刷 scaffold（解耦"升级包"与"刷 scaffold"）

**Step 3: 脊柱 — 刷新 / 部署 / 验证**

先预览幂等 plan:

```bash
cataforge bootstrap --dry-run
```

`bootstrap` 按产物状态自决每步:
- scaffold 已 current → skip setup
- installed 包版本 > scaffold 版本 或 manifest drift → 跑 upgrade
- scaffold 变化 / 平台漂移 / 从未部署 → 跑 deploy
- 永远跑 doctor 作为验证门

若仅 doctor 跑，报告"已 current"。其余步骤为 run 时展示 plan、用户确认后应用:

```bash
cataforge bootstrap --yes
```

fresh install 报告缺平台时询问用户（`claude-code` 默认）并 `cataforge bootstrap --platform <id> --yes`。`cataforge upgrade check` 标记升级范围含 CHANGELOG `### BREAKING` 条目时，先摘要给用户再应用。`--dry-run` 场景输出 plan 后停止，不执行任何写入。doctor FAIL 时按指令3 解读路径处理。

**Step 4: 簿记**

1. 读 `framework.json`，更新 `upgrade.state`（`last_version` / `last_upgrade_date` / `last_commit`），用 Read + Edit 原地写入，保留其它字段
2. `cataforge claude-md check`（如可用）surface hygiene 问题；FAIL 时建议用户跑 `cataforge claude-md compact`（非阻塞，仅提示）

> `{INSTRUCTION_FILE}` §项目信息.框架版本 由 Step 3 deploy 阶段以 `{FRAMEWORK_VERSION}` 占位符盖入已安装包版本，本 skill 不写版本字段。

> bootstrap 中若遇 EVENT-LOG schema FAIL（历史旁路写入触发），按 hint 跑 `cataforge event accept-legacy` 设水位线即可，不影响本次同步。

**Step 5: 项目初始化 / 恢复（分支）**

依 `{INSTRUCTION_FILE}` 是否存在分流:

- **缺 — from-scratch 项目**: 委托执行 `{AGENTS_SRC_DIR}/orchestrator/ORCHESTRATOR-PROTOCOLS.md` §Project Bootstrap（收集项目信息、选执行模式、建 `docs/` 结构、写 `{INSTRUCTION_FILE}`、装配 env + permissions、进入初始 phase）。目标平台已由 Step 3 确定，从 `framework.json` `runtime.platform` 读取，不重新选型/部署。
- **在 — 已初始化**: 不重跑 Project Bootstrap。若 `{INSTRUCTION_FILE}` §执行环境 仍是占位符或技术栈变化:

  ```bash
  cataforge setup env-block      # 注入 §执行环境；exit 2 = 无已知技术栈
  cataforge setup permissions    # 收紧 permissions.allow 到技术栈
  ```

  exit 2 时写 `- 无自动检测到的标准包管理器（请根据实际技术栈手动填写）` 并询问用户包管理器 + 测试命令。随后交接 `/start-orchestrator continue` 做 phase 恢复。

**Step 6: 报告**

汇总：框架同步（scaffold vs installed 版本、哪几步跑了）、包升级结果、init/resume 决策、探测到的技术栈与已装配命令、用户仍需手动跟进项。

---

### 指令3: 迁移验证 (verify)

**Step 1: 运行迁移检查**

```bash
cataforge doctor
```

等价于 `cataforge upgrade verify`。

**Step 2: 解读**

- `PASS` — 通过，无需操作
- `SKIP` — 平台未 deploy，不计失败，属预期
- `FAIL` — 失败，需修复后重试

FAIL 时输出具体原因并建议修复（通常重跑 `framework-update apply` 或手动修 `framework.json` 对应字段）。

**Step 3: 报告**

```
迁移检查结果:
  PASS  N 项
  SKIP  N 项（已部署平台）
  FAIL  N 项
整体状态: OK | 需要修复
```

---

## 完整流程（无参数默认行为）

未传参数直接调用时，按顺序:

1. **check** — 检测版本差异与初始化状态
2. **确认** — 已最新且已初始化则告知无需操作；有差异或未初始化则说明将执行的变更并请求确认
3. **apply** — 包升级（条件）+ `cataforge bootstrap` 编排刷新/部署/验证 + 簿记 + init/resume（用户确认后）

每步之间汇报进度，任一步骤失败时停止并说明原因。`verify` 保留为独立入口，供"只想跑诊断不升级"的场景。

---

## 字段保留规则

`upgrade apply` 刷新时的保留策略（由 `cataforge` 包内部实现，本 skill 不额外干预）:

| 文件 | 保留项 | 覆盖项 |
|------|--------|--------|
| `framework.json` | `runtime.platform`、`upgrade.state` | `version`、`constants`、`features`、`migration_checks`、`upgrade.source` |
| 其它 `.cataforge/` 文件 | — | **整个文件**；apply 前自动快照到 `.cataforge/.backups/<ts>/`，用 `cataforge upgrade rollback` 恢复 |

> `upgrade.state` 由本 skill Step 4 手动写入，不被 `upgrade apply` 覆盖，因此升级日期与版本记录持久保留。
> 用户在 apply 后发现自定义改动丢失时，告知运行 `cataforge upgrade rollback --list` 查快照并 `rollback --from <ts>` 回滚。

## Anti-Patterns
- 禁止: 把 Step 5 的 init 分支派发给非 orchestrator 子代理执行 —— init 会写 `{INSTRUCTION_FILE}` §项目状态（orchestrator 独占权限）；本 skill 必须由 orchestrator 主线程内联调用，init 分支只委托 ORCHESTRATOR-PROTOCOLS §Project Bootstrap，不内嵌协议
- 禁止: 跳过 Step 4 的 `cataforge claude-md check` —— 升级后 Learnings Registry 膨胀是真实事故源
- 禁止: 在 apply 里用 `git checkout` / `git restore` 清场用户文件 —— 用户改动应走 `cataforge upgrade rollback --list` + `--from <ts>` 快照通道
- 禁止: 升级时在 `framework.json` 写 `runtime.platform` / `upgrade.state` 之外的用户态字段 —— 这两个字段是契约保留项，其它字段全量覆盖
- 避免: 包管理器探测失败就 abort 整个 apply —— 应继续走 Step 3 仅刷 scaffold 路径，把"升级包"和"刷 scaffold"解耦

## 效率策略
- 先探测包管理器再升级，避免升级命令错误
- `--dry-run` 安全预览 plan，不动任何文件
- 版本已一致且已初始化时跳过升级与 init，仅在用户要求时强制刷新
- `cataforge bootstrap` 幂等自决 skip/run，无需本 skill 重复判断每步是否需要
- init/resume 分支只在 Step 5 委托一次，权限边界与协议主体留在 orchestrator
