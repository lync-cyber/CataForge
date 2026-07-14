# 多平台共存指南

> 同一个项目可以同时启用 Claude Code / Cursor / CodeX / OpenCode 中的多个平台：产物长期共存、各平台独立 redeploy、独立体检。本文是操作指南；模型与原理见 [`../architecture/platform-adaptation.md`](../architecture/platform-adaptation.md) §5，单平台的产物与最小配置见 [`platforms.md`](./platforms.md)。

## 1. 启用多个平台

`framework.json#deployment.targets` 是项目声明的启用平台集合，`deployment.default_platform` 是缺省平台。两种写法等价：

```bash
# 方式一：setup 追加 —— 把新平台设为缺省并并入 targets（已有成员保留）
cataforge setup --platform cursor

# 方式二：直接声明集合（缺省平台不变）
cataforge config set deployment.targets "claude-code,cursor"
```

写入后用 `cataforge config validate` 校验（平台 id 合法、`default_platform ∈ targets`），`cataforge config explain deployment.targets` 可查看值与来源层。

## 2. 部署：`deploy` 与 `--platform all`

```bash
cataforge deploy                    # 无参 = 部署全部声明 targets
cataforge deploy --platform cursor  # 只部署一个平台，不触碰其他平台产物
cataforge deploy --platform all     # 对所有支持的平台各跑一轮
```

多平台部署的三条保证：

- **逐平台独立 commit**：每个平台成功完成后才写自己的 `.cataforge/state/deploy/<platform>/state.json` + `manifest.json`（含 `owned_paths` 所有权清单与 drift 基线）。某平台失败不会留下该平台的假成功记录，也不会覆盖已成功平台的记录。
- **项目级锁**：整个 deploy 运行（含 `--platform all` 的全循环）持 `.cataforge/state/locks/deploy.lock`，并发 deploy 被拒绝而非交错写盘。
- **跨平台保护集**：一个平台的 prune / `--rebuild` 只处理本平台 manifest 认领、且未被其他平台 manifest 认领的路径；共享产物（`AGENTS.md`、`.claude/skills`）由最后一个 owner 在其自身 deploy 中清理。

## 3. 体检：`doctor --platform`

```bash
cataforge doctor                    # 缺省范围 = 已部署平台集合（无部署记录时为缺省平台）
cataforge doctor --platform cursor  # 只检一个平台
cataforge doctor --platform all     # 声明 targets ∪ 已部署平台
```

平台相关的检查段按范围逐平台执行：Deploy integrity / provenance 以各平台自己的 manifest `owned_paths` 为权威；Deploy drift 按各平台自己的基线判定；指令文件 hygiene 按平台 profile 选定 CLAUDE.md / AGENTS.md；`migration_checks` 的 `platforms` 字段限定检查的适用平台。

## 4. 共享 AGENTS.md 与 §项目状态 SSOT

cursor / codex / opencode 三平台共写 `AGENTS.md`（section-merge，不覆盖用户新增章节）。多指令文件并存时：

- **`default_platform` 的指令文件是 §项目状态 的唯一权威**（SSOT）。orchestrator 只写权威文件。
- 新启用平台首次 deploy 生成指令文件时，其 §项目状态 / §执行环境 从权威文件**播种**，而非模板占位符。
- 两份指令文件的 §项目状态 各自被编辑而分叉时，`cataforge doctor` 的「Project state projection」段报 **WARN**（不 FAIL）——人工对齐权威文件后 redeploy 即收敛。
- 共享文件按声明的平台受众渲染（`运行时:` 为 targets 排序集合、路径占位符渲染为平台中立的 `.cataforge/` 源路径），字节与部署顺序无关。

## 5. 并行开发（最低安全模型）

deploy / upgrade / config 的写路径全部经项目级文件锁（`O_CREAT|O_EXCL` 原子创建，锁文件记录 owner / pid / 创建时间）：

- 锁被其他进程持有时，第二个写进程**明确拒绝**并输出 `git worktree add ../<branch-dir> <branch>` 引导——不静默排队，也不覆盖。
- 崩溃残留的死锁按 TTL 自动回收（deploy 锁 1800 秒、config 锁 60 秒），无需手工清理。
- 真正需要并行的写操作放到独立 git worktree 各自的 `.cataforge/` 下执行。

## 6. 旧单平台项目迁移（schema v1 → v2）

### 触发时机

| 途径 | 说明 |
|------|------|
| `cataforge upgrade apply` | scaffold 刷新后自动执行迁移 |
| `cataforge bootstrap` | 计划执行时自动迁移 |
| `cataforge config migrate` | 手动触发；`--dry-run` 只报告不写盘 |

迁移幂等：已是 v2 布局时输出 "Already at current schema" 直接返回。

### 字段映射

| v1 位置 | v2 位置 |
|---------|---------|
| `runtime.platform` | `deployment.default_platform`（`targets` 播种为 `[default_platform]`） |
| `upgrade.state` | `.cataforge/state/upgrade.json`（gitignored 运行状态文件） |
| `.cataforge/.deploy-state` / `.deploy-manifest.json` | `.cataforge/state/deploy/<platform>/{state,manifest}.json`（由 deploy 入口幂等迁移，非 `config migrate` 职责） |

未迁移的项目仍可读：`deployment.default_platform` 缺失时回落 `runtime.platform`（`config explain` 显示 `legacy` 层），`upgrade.state` 读取兼容旧位置。

### 备份与回滚

- `config migrate` 写盘前把原 framework.json 备份到 `.cataforge/.backups/config-migrate-<ts>/framework.json`；需要回退时把该文件拷回 `.cataforge/framework.json` 即可。
- `upgrade apply` 的全量 scaffold 快照用 `cataforge upgrade rollback`（`--list` 列出快照）恢复。

## 7. 本机差异与 secrets

- **`.cataforge/config.local.json`**（gitignored）：本机覆盖层，白名单字段。典型用法——同一仓库在不同机器用不同 IDE 时，本机写 `{"deployment": {"default_platform": "cursor"}}`，不污染共享的 framework.json。
- **`CATAFORGE_PLATFORM` 环境变量**：平台解析的最高环境层（仅作用于 `deployment.default_platform` 路径），也是 hook 进程的显式身份信号。
- **secrets 只存环境变量名**：配置文件里的凭据字段一律是变量名而非值——如 `upgrade.source.token_env: "GITHUB_TOKEN"`，token 本体只放环境变量。

## 8. CI 建议

```bash
cataforge config validate       # schema / 平台 id / default ∈ targets；v1 布局 WARN
cataforge doctor --platform all # 全部声明 + 已部署平台逐一体检（任一 FAIL 非零退出）
```

## 参考

- 平台矩阵与单平台配置：[`platforms.md`](./platforms.md)
- 共存模型与保护集机制：[`../architecture/platform-adaptation.md`](../architecture/platform-adaptation.md)
- 配置解析层级与 `cataforge config`：[`../reference/configuration.md`](../reference/configuration.md)
- 升级与快照回滚：[`upgrade.md`](./upgrade.md)
