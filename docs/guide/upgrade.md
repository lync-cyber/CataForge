# 升级与脚手架刷新

> CataForge 采用**包管理器驱动**的升级模型：`pip` / `uv tool` 管理包本身，`cataforge upgrade apply` 刷新项目内 `.cataforge/` 脚手架。**不存在** "远程自升级"。

## 两条等价路径

| 路径 | 谁用 | 命令 |
|------|-----|------|
| **CLI** | 终端 / CI | `cataforge upgrade {check,apply,rollback,verify}` |
| **IDE skill** | Claude Code / Cursor 会话内 | `/self-update [check\|apply\|verify]` |

两条路径读写同一套状态。`/self-update` 内部调用 `cataforge upgrade`，并额外处理 `pip install --upgrade` / `uv tool upgrade` 这一步包管理命令。

## 升级四步法（CLI）

```bash
# 1. 对比 "已安装包版本" vs "项目 scaffold 版本"
cataforge upgrade check

# 2. 升级包本身
pip install --upgrade cataforge          # 或: uv tool upgrade cataforge

# 3. 预览 → 真刷新（自动快照）
cataforge upgrade apply --dry-run        # 逐文件列出 [new] / [update] / [user-modified] / [preserved]
cataforge upgrade apply                  # 真写，同时在 .cataforge/.backups/<ts>/ 建快照

# 4. 验证
cataforge upgrade check                  # 应打印 "Scaffold is up to date with the installed package."
cataforge upgrade verify                 # = cataforge doctor，跑 migration_checks
```

若 `upgrade check` 检测到 CHANGELOG.md 中的 `### BREAKING` 条目落在 scaffold→installed 的版本区间内，会在提示旁以黄字警告。升级前先阅读 CHANGELOG 对应段。

---

## 不要这样做

```bash
# 反例：在 main 分支直接 upgrade apply 然后推
git checkout main
cataforge upgrade apply
git add . && git commit -m "upgrade scaffold" && git push
```

为什么：`upgrade apply` 会重写 `.cataforge/` 下大量文件。`main` 受保护，且团队仓库里其他分支可能基于旧 scaffold 在做事，直接合入会产生跨分支大面积冲突。

正确做法：在 feature 分支跑 `upgrade apply`，跑 `cataforge doctor` 通过后 PR 合入，让 squash merge 把变更聚合成一条提交。

## 文件保留规则

`upgrade apply`（等价于 `setup --force-scaffold`）只保留下表中的字段/文件；`.cataforge/` 下其它文件在刷新时整体覆盖。手改过的 agent prompt、hook 脚本、skill 定义会丢失——自定义内容请放到 `.cataforge/plugins/` 或项目外。

| 文件 | 保留项 | 覆盖项 |
|------|-------|-------|
| `framework.json` | `runtime.platform`、`upgrade.state` | `constants` / `features` / `migration_checks` / `upgrade.source` / `version` |
| `PROJECT-STATE.md` | 整个文件 | — |
| 其它 `.cataforge/` 下文件 | — | 整个文件 |

> `framework.json` 的 `version` 字段在 scaffold 写入时由当前安装包的 `cataforge.__version__` 实时戳入，保证 `upgrade apply` 之后 `upgrade check` 立刻报告 "up to date"。

**每次升级前建议先跑 `upgrade apply --dry-run`**——它把上表的"覆盖"分类到具体文件上，每行附状态标签。

---

## 快照与回滚

每次 `upgrade apply` 在写入前，把当前 `.cataforge/`（`.backups/` 子目录除外）快照到 `.cataforge/.backups/<YYYYMMDD-HHMMSS>/`。不依赖 git。

```bash
# 查看所有快照（最新在前）
cataforge upgrade rollback --list

# 恢复最新快照（交互式确认，加 --yes 跳过）
cataforge upgrade rollback

# 按时间戳名恢复指定快照（list 中显示的字符串）
cataforge upgrade rollback --from 20260424-150030 --yes

# 按绝对路径恢复（适合把快照移出项目外的场景）
cataforge upgrade rollback --from /abs/path/to/backup --yes
```

Rollback 本身也会把当前状态快照到 `.backups/pre-rollback-<ts>/`，所以回滚也可再回滚。

### 快照生命周期

- 目前**不自动 GC（garbage collection，垃圾回收）**。老快照由用户手动清理：

  ```bash
  rm -rf .cataforge/.backups/<old-ts>/
  ```

- `.gitignore` 默认已排除 `.cataforge/.backups/`，不会入库。
- 典型单快照体积 5–15 MB（规模随项目 agents/skills 数量增长）。频繁升级的仓库建议每月清一次，或在 CI 加 retention job 只保留最近 N 份。

---

## 迁移检查（Migration Checks）

`cataforge doctor` / `cataforge upgrade verify` 执行 `framework.json` 中 `migration_checks` 段声明的全部检查项。任一 FAIL 时进程返回码为 1，可作 CI gate：

```bash
cataforge doctor || exit 1
```

常见检查项：

- `framework.json` / `hooks.yaml` 结构完整性
- 4 个平台 `profile.yaml` 合法性
- 关键文件存在与权限
- 依赖 IDE 产物的检查（未 deploy 前显示 `SKIP`，不会 FAIL）

---

## 常见升级场景

### 场景 1：只升级包，不刷新 scaffold

```bash
pip install --upgrade cataforge
cataforge upgrade check     # 报告 scaffold outdated
# 跳过 upgrade apply → 保持旧 scaffold 行为
```

期望输出：

```text
Installed: 0.1.15
Scaffold:  0.1.13
⚠ Scaffold is behind installed package.
  Run: cataforge upgrade apply
```

适合"新版本 CLI 对旧 scaffold 仍兼容"的保守场景。

### 场景 2：纯预览，不改动任何文件

```bash
cataforge upgrade apply --dry-run
```

期望输出（节选）：

```text
[preserved]      .cataforge/framework.json (runtime.platform, upgrade.state)
[preserved]      .cataforge/PROJECT-STATE.md
[update]         .cataforge/agents/orchestrator/AGENT.md
[user-modified]  .cataforge/agents/architect/AGENT.md  → backed up to .backups/<ts>/
[new]            .cataforge/skills/framework-review/SKILL.md
Total: 12 files (3 unchanged, 5 update, 1 user-modified, 3 new)
```

### 场景 3：回滚

```bash
cataforge upgrade rollback          # 脚手架层面
pip install cataforge==<old-version>  # 包层面（<old-version> 换成想回退到的版本号）
```

期望输出（脚手架层面）：

```text
Latest snapshot: .cataforge/.backups/20260424-150030/
Rollback to this snapshot? [y/N] y
✓ Pre-rollback snapshot saved to .cataforge/.backups/pre-rollback-20260427-091522/
✓ Restored 12 files from 20260424-150030.
Run cataforge doctor to verify.
```

---

<!-- 变更原因：FAQ 内容迁移到 docs/faq.md §升级，消除双源（diagnostic #6） -->
## 常见问题

升级相关 Q&A 集中在 [`../faq.md`](../faq.md) §升级。

---

## 参考

- CLI 命令（含 `upgrade rollback` 完整参数）：[`../reference/cli.md`](../reference/cli.md) §upgrade
- 配置文件清单：[`../reference/configuration.md`](../reference/configuration.md)
- `doctor` 用作 CI gate：[`manual-verification.md`](./manual-verification.md)
