# ADR: 多平台配置模型与部署状态模型

状态：accepted。审计依据：`docs/reviews/framework/FRAMEWORK-REVIEW-multi-platform-config-20260714-r1.md`（gitignored 工作产物，结论以本文为准归档）。

## 问题

`framework.json` 单文件同时承载用户声明配置（A）、框架 catalog（B）、版本锁定（C）、运行时状态（E：`upgrade.state`）；`runtime.platform` 单值同时表达 CLI 缺省平台、doctor 检查目标、hook 身份 fallback、指令文件渲染源五种语义；`.deploy-state`/`.deploy-manifest.json` 是全平台 last-writer-wins 单槽。四平台（claude-code/cursor/codex/opencode）无法在同一项目长期共存：切换平台即丢前一平台所有权记录，doctor 只检最后部署平台，共享 AGENTS.md 的平台身份随最后部署者翻转，配置写入无并发保护。

## 方案比较

**方案 A — 单一 framework.json 增加分区**：`schema_version: 2` + `framework`/`deployment`/`project` 分区，运行时状态仍需另寻去处（不变量 1/12 禁止其留在配置文件）。

**方案 B — 三文件分离**：`framework.json`（声明）+ `framework.lock.json`（版本/catalog digest）+ `config.local.json`（本机覆盖）+ `state/`（运行状态）。catalog（constants/features/workflow/migration_checks/dispatcher_skills）从包或 lock 读取，不再落用户配置。

**方案 C（选定）— B 的状态/锁分离骨架 + A 的单文件声明面**：`framework.json` 收窄为「声明 + catalog」单文件（`schema_version: 2`，新增 `deployment` 分区，剥离 `upgrade.state`）；运行状态全部迁入 gitignored `.cataforge/state/`；本机覆盖 `config.local.json` 作为白名单层；不引入 lock 文件。

| 维度 | A | B | C |
|------|---|---|---|
| 升级复杂度 | merge 逻辑保留且更复杂 | merge 基本消失，但 lock 生成/校验链新增 | merge 保留但改为**字段级所有权表数据驱动**，规则可测 |
| 配置可理解性 | 中（单文件分区） | 高（层即文件），但四文件心智成本 | 高（单文件 + state 目录二分） |
| Git diff 噪声 | catalog 更新仍在用户 diff | 最优 | 同 A；catalog 块升级 diff 保留（可接受：squash PR 内一次性） |
| 并发安全 | 与文件布局无关，需锁/CAS | 同左 | 同左（本 ADR 一并落地锁） |
| 单平台兼容 | 迁移最小 | 全部引用路径重写 | 迁移小（`runtime.platform` → `deployment`，其余原位） |
| 下游定制 | 手编同文件 | 声明文件干净 | 手编同文件 + local 白名单层 |
| 插件扩展 | 命名空间键同文件 | lock 侧扩展复杂 | 未知顶层键保留 + `x-` 命名空间约定 |
| 回滚与迁移 | 单文件损坏影响全部 | state/lock 可重建 | state 可重建；framework.json 迁移带备份 |
| doctor 可解释性 | 需块级注解 | 层即来源 | `config explain` 呈现 env/local/file/default 四层 |

**弃 B 纯形的决定性理由**：catalog 块被 `.cataforge/` prompt 资产（SKILL/AGENT/rules）以 `framework.json#/workflow`、`#feedback.gh.labels`、`#/dispatcher_skills` 等路径引用 21 处/9 文件，且 workflow-framework-generator 为下游生成同构模板——迁出 catalog 需要同步改写全部 prompt 引用面与下游迁移，而审计确认的全部实际缺陷（状态混入、platform 多义、preserve 丢数据、并发、单槽 state）无一依赖 catalog 迁出。catalog 的治理靠所有权表 + `config explain`，不靠搬家。

## 决策

### 1. framework.json schema v2

```json
{
  "schema_version": 2,
  "version": "<scaffold 版本，升级盖写>",
  "runtime_api_version": "1.0",
  "deployment": {
    "default_platform": "claude-code",
    "targets": ["claude-code"]
  }
}
```

- `runtime.platform` → `deployment.default_platform`；`targets` 为项目声明的启用平台集合（迁移时初始化为 `[default_platform]`）。迁移后 v2 文件不再含 `runtime` 块；读取层对 v1 文件保持兼容（`deployment.default_platform` 缺失时回落 `runtime.platform`，再回落 `claude-code`）。
- `upgrade.state` 迁出至 `.cataforge/state/upgrade.json`；`upgrade` 块仅剩 `source`（升级改为**保留用户值**）。
- 其余块原位不动。

### 2. 字段级所有权表（替代硬编码块级 preserve）

`_merge_framework_json` 改为数据驱动：所有权表声明每个顶层块 `user`（升级保留，浅合并补入新默认键）/ `framework`（升级全量覆盖）。`user` 集合 = `deployment` / `upgrade.source` / `feedback` / `kg` / `context` / `project` / `claude_md_limits` / `git`；`framework` 集合 = `version` / `runtime_api_version` / `description` / `constants` / `dispatcher_skills` / `workflow` / `features` / `migration_checks`。**未知顶层键一律保留**（修复用户自加键升级即丢）。

### 3. 运行状态目录 `.cataforge/state/`（gitignored）

```
.cataforge/state/
  deploy/<platform>/state.json      # {platform, package_version}
  deploy/<platform>/manifest.json   # {manifest_version: 2, owned_paths, source_digest, package_version}
  upgrade.json                      # {event_log_validate_since, ...}
  locks/deploy.lock                 # 项目级部署互斥（O_CREAT|O_EXCL + owner/pid/时间戳/TTL 过期恢复）
  locks/config.lock                 # framework.json 写互斥（短 TTL）
```

- 旧 `.deploy-state` / `.deploy-manifest.json` 由 deploy 入口幂等迁移（读侧全程双布局兼容，doctor 只读不迁移）。
- **prune 跨平台保护集**：平台 P 的 prune 候选 = 在 P 自身 prior manifest 中 ∧ 不在任何其他平台 manifest 中 ∧ 源已删除。共享产物（`.claude/skills` 双平台、AGENTS.md 三平台）由此天然免于跨平台误删，无需独立 shared manifest 写者协调。
- drift baseline per-platform（各自 manifest 内）。
- `deploy --platform all`：先获取 `deploy.lock`，对全部目标做配置校验（plan），逐平台部署（apply），**每平台成功才写各自 state/manifest（commit）**；任一平台失败不产生该平台的成功 state，已成功平台的 state 保留。

### 4. 配置解析层级与 CLI

```
CLI flags  >  CATAFORGE_* env（显式映射，仅 CATAFORGE_PLATFORM → 平台解析）
  >  .cataforge/config.local.json（gitignored，白名单字段）
  >  .cataforge/framework.json  >  代码内默认值
```

- deploy/doctor 开始时构造不可变 `ConfigSnapshot`，全程单快照（drift digest 用快照内容，不再中途重读磁盘）。
- 新增 `cataforge config` 子命令最小闭环：`validate`（schema + 未知键报告）、`explain <path>`（值 + 来源层）、`get <path>`、`set <path> <value>`（白名单路径、同值不写盘、`--dry-run`）、`migrate`（v1→v2，幂等，先备份）。不实现 unset/list/diff。

### 5. 平台身份与 doctor 平台化

- **hook 身份注入**：各平台生成的 hook 配置显式携带平台标识——claude-code 经 `settings.json#env.CATAFORGE_PLATFORM`；cursor/codex 的 hook command 追加平台参数；opencode TS plugin 的 spawn env 注入。`platform_from_env` 保持四级链；多平台项目（`targets` ≥ 2）中无显式信号时 hook FAIL 而非回落单值。
- **doctor `--platform <id>|all`**：缺省 = 已部署平台集合。deploy integrity/provenance 改以 per-platform manifest `owned_paths` 为权威（静态表删除）；hygiene 按 profile `instruction_file.targets[0].path` 选文件与 remediation；shell_preference 仅 claude-code 执行；migration checks schema 增加 `platforms` 字段，runner 按已部署平台过滤。
- **Codex/OpenCode skill 降级契约**：translator 对 `needs_skill_deploy: false` 平台把 agent 声明的 skills 渲染为「先读取 `.cataforge/skills/<id>/SKILL.md`」的显式指令清单注入 agent 正文；doctor 校验每个 agent 的 skill 依赖至少一种可达路径。

### 6. 共享指令文件与项目状态

- AGENTS.md `运行时:` 字段渲染为 **targets 排序集合**（仅依赖声明集合，与部署顺序无关，换序部署字节稳定）；共享 instruction 文件中的平台相关占位符（`{RULES_DIR}` 等）渲染为平台中立的 `.cataforge/` 源路径。
- 项目状态 SSOT：`default_platform` 的指令文件为 §项目状态 唯一权威；deploy 时将权威文件的 runtime 节播种到其他指令文件；doctor 检测双文件投影 drift。结构化状态文件（JSON SSOT + 只读投影）记为后续演进方向，本次不落地——双 Markdown 并写的同步安全无法证明，故收敛为单权威 + 投影。

### 7. 并行开发最低安全模型

完整 session/worktree 管理（lease 心跳、任务 deliverables 声明、owner_session）超出本次合理范围，落地最低要求：

- deploy/upgrade/config 写路径全部经项目级锁；锁含 owner/pid/创建时间/TTL，过期可恢复，无永久锁。
- 第二个写进程在锁被持有时**明确拒绝**并输出 `git worktree add` 引导文案，不静默排队覆盖。
- 完整 lease/session 模型记入后续演进。

## 后果

- 正：四平台产物可长期共存、独立 redeploy、独立 doctor；升级不再丢用户配置；配置写入并发安全；每个配置值来源可解释；单平台旧项目经 `config migrate`（或 upgrade apply 自动触发）无感迁移。
- 负：`.cataforge/state/` 新目录概念需文档与 gitignore 维护；读侧双布局兼容期代码存在两条路径；catalog 块仍在 framework.json（diff 噪声保留，接受）。
- 重新评估条件：Codex/OpenCode 推出原生 skill/命令目录契约时，重评 R-003 降级契约；下游多平台项目出现真实并行写冲突时，重评完整 lease 模型。
