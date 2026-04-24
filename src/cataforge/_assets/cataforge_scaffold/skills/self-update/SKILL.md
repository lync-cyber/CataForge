---
name: self-update
description: "CataForge 自更新 — 检测已安装包与项目 scaffold 的版本差异，升级包并刷新 scaffold，运行迁移检查验证一致性。支持 pip 和 uv 两种包管理器，保留 runtime.platform、upgrade.state 和 PROJECT-STATE.md 等用户可编辑状态。当用户提到 CataForge 升级、scaffold 过期、framework 版本不一致、更新框架配置时，使用此 skill。"
argument-hint: "[check | apply [--dry-run] | verify]"
suggested-tools: Bash, Read
depends: []
disable-model-invocation: false
user-invocable: true
---

# CataForge 自更新 (self-update)

## 能力边界
- 能做: 版本差异检测、pip/uv 包升级、scaffold 增量刷新、迁移检查执行、upgrade.state 状态记录
- 不做: 修改项目业务代码、升级操作系统依赖、跨平台 adapter 变更（由 platform-audit 负责）

## 输入规范
- 操作指令: `check`（仅检测）、`apply`（升级并刷新）、`verify`（迁移检查）
- 无参数时默认执行完整四步升级流程（check → 升级包 → apply → verify）
- `--dry-run` 标志: 仅在 apply 指令中有效，预览变更不写盘

## 输出规范
- 版本对比结果（scaffold 版本 vs 已安装版本）
- scaffold 刷新文件统计（写入数 / 保留数）
- 迁移检查结果（PASS / FAIL / SKIP 逐项）
- upgrade.state 更新确认

---

## 操作指令

### 指令1: 版本检测 (check)

**Step 1: 读取当前状态**

并行执行:
```bash
cataforge upgrade check
```
```bash
python3 -c "import cataforge; print(cataforge.__version__)"
```

记录:
- `installed_version` — 已安装包版本
- `scaffold_version` — 项目 `.cataforge/framework.json` 中的 `version` 字段
- 是否一致

**Step 2: 报告差异**

输出格式:
```
已安装包: <installed_version>
Scaffold : <scaffold_version>
状态     : up-to-date | outdated
```

若 outdated，提示用户运行 `self-update apply` 或手动执行四步升级流程。

---

### 指令2: 升级并刷新 (apply)

> 此指令执行完整四步升级流程，自动检测包管理器。

**Step 1: 版本前置检查**

```bash
cataforge upgrade check
```

若已是 up-to-date，告知用户并询问是否仍要强制刷新 scaffold。用户确认后继续，否则跳过 Step 2-3。

**Step 2: 检测包管理器**

依次尝试（短路逻辑，找到第一个可用的即停止）:

```bash
uv tool list 2>/dev/null | grep -q cataforge && echo "uv"
```
```bash
pip show cataforge 2>/dev/null | grep -q Name && echo "pip"
```

- 若检测到 `uv` → 升级命令为 `uv tool upgrade cataforge`
- 若检测到 `pip` → 升级命令为 `pip install --upgrade cataforge`
- 若均未检测到 → 提示用户手动升级包后重试，并继续执行 Step 3（仅刷新 scaffold）

**Step 3: 升级包**

执行对应升级命令（除非 `--dry-run`）:

```bash
# uv 场景
uv tool upgrade cataforge

# pip 场景
pip install --upgrade cataforge
```

若 `--dry-run`:
```bash
cataforge upgrade apply --dry-run
```
输出预览后停止，不执行任何写入。

**Step 4: 刷新 scaffold**

```bash
cataforge upgrade apply
```

记录输出中的 `wrote N file(s)` 和 `kept N existing` 数值。

**Step 5: 更新 upgrade.state**

读取 `.cataforge/framework.json`，更新 `upgrade.state` 字段:

```json
{
  "upgrade": {
    "state": {
      "last_version": "<新安装版本>",
      "last_upgrade_date": "<YYYY-MM-DD>",
      "last_commit": ""
    }
  }
}
```

使用 Read + Edit 工具原地更新，保留文件其他字段不变。

**Step 6: 验证**

```bash
cataforge upgrade check
```

确认输出包含 `Scaffold is up to date with the installed package.`

---

### 指令3: 迁移验证 (verify)

**Step 1: 运行迁移检查**

```bash
cataforge doctor
```

等价于 `cataforge upgrade verify`。

**Step 2: 解读结果**

- `PASS` — 检查项通过，无需操作
- `SKIP` — 平台尚未 deploy，不计入失败，属预期行为
- `FAIL` — 检查项失败，需要修复后重试

若有 FAIL 项，输出具体失败原因并提出修复建议（通常是重新运行 `cataforge upgrade apply` 或手动修复 `framework.json` 中对应字段）。

**Step 3: 报告**

```
迁移检查结果:
  PASS  N 项
  SKIP  N 项（已部署平台）
  FAIL  N 项
整体状态: OK | 需要修复
```

---

## 完整四步升级流程（无参数默认行为）

当用户未传参数直接调用 `/self-update` 时，按顺序执行:

1. **check** — 检测版本差异
2. **询问确认** — 若已是最新版本，告知用户无需升级；若有差异，说明将执行的变更并请求确认
3. **apply** — 执行升级（用户确认后）
4. **verify** — 运行迁移检查

每步之间汇报进度，任一步骤失败时停止并说明原因。

---

## 字段保留规则

`upgrade apply` 刷新时的保留策略（由 `cataforge` 包内部实现，此 skill 不额外干预）:

| 文件 | 保留项 | 覆盖项 |
|------|--------|--------|
| `framework.json` | `runtime.platform`、`upgrade.state` | `version`、`constants`、`features`、`migration_checks`、`upgrade.source` |
| `PROJECT-STATE.md` | 整个文件 | — |
| 其它 `.cataforge/` 文件 | — | **整个文件**；`apply` 前自动快照到 `.cataforge/.backups/<ts>/`，可用 `cataforge upgrade rollback` 恢复 |

> `upgrade.state` 由本 skill 在 Step 5 手动写入，不被 `upgrade apply` 覆盖，因此升级日期和版本记录会持久保留。
> 若用户在 apply 后发现自定义改动丢失，告知他们运行 `cataforge upgrade rollback --list` 查看快照并 `rollback --from <ts>` 回滚。

## 效率策略
- 先检测包管理器，避免升级命令错误
- `--dry-run` 可安全预览变更，不影响任何文件
- 版本已一致时跳过升级步骤，仅在用户要求时强制刷新
- `upgrade.state` 记录每次升级时间，便于追溯
