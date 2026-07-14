---
id: "framework-review-adversarial-multiplatform-config-20260714-r1"
doc_type: framework-review
author: reviewer
status: approved
deps: []
consumers: ["orchestrator"]
---

# FRAMEWORK-REVIEW: 多平台配置重构对抗性审查（adversarial-multiplatform-config）

## 1. 审查范围和基线

- **被审对象**: squash commit `ad39aec` — `feat(config): multi-platform deployment state model (#487)`（已合入 main）
- **BASE_REF**: `ad693ee`（#487 的父 commit）；**HEAD_REF**: `ad39aec` = origin/main HEAD
- **工作区状态**: 审查起点 `git status --short` 为空（无未提交修改，无用户无关修改需避开）；分支 `claude/sad-panini-b71533` 与 origin/main 同点
- **变更规模**: 77 文件，+3950/−944（`git diff --stat ad693ee...ad39aec`）
- **版本事实**: cataforge 0.17.0；framework.json `schema_version: 2`；`runtime_api_version: 1.0`
- **环境**: Windows 11 Pro (26200) / Python 3.13.14 / uv 0.11.6 / git 2.53.0.windows.2
- **IDE CLI 可用性**: claude 2.1.202 ✓；cursor（仅编辑器打开器，无 agent CLI）；codex ✗；opencode ✗；cursor-agent ✗

## 2. 子代理分工及隔离方式

| 角色 | 范围 | 隔离 |
|------|------|------|
| A 配置与 Schema | config.py / config_migrate / schema / locks / config_cmd | 只读仓库 + 独立沙盒 cf-adv 域（scratchpad role-A） |
| B 部署所有权 | deployer / manifest / prune / scaffold / deploy_cmd | 只读仓库 + 独立沙盒 role-B |
| D 向后兼容与迁移 | v1 fixtures / upgrade / legacy state 迁移 | 只读仓库 + 独立沙盒 role-D |
| E1–E4 平台适配 | claude-code / codex / cursor / opencode 各一名 | 只读仓库 + 各自沙盒 + 官方文档核对 |
| F 测试有效性 | 新增/修改测试的断言强度 + mutation 预测矩阵 | 只读仓库（定点 pytest） |
| G 文档契约漂移 | docs / CLI help / schema / 模板互核 | 只读仓库 |
| H1 排列与幂等 | 24 排列 + metamorphic | 独立沙盒 /Temp/cf-adv/H1 |
| H2 shared ownership | 8 攻击场景 | 独立沙盒 /Temp/cf-adv/H2 |
| H3 doctor 矩阵 | 12 攻击场景 × 调用形态 | 独立沙盒 /Temp/cf-adv/H3 |
| H5 平台身份 | 9 串台场景 | 独立沙盒 /Temp/cf-adv/H5 |
| H6 AGENTS/CLAUDE 状态 | 7 状态攻击 | 独立沙盒 /Temp/cf-adv/H6 |
| H8 故障注入+并发 | 注入/锁竞态/多写会话 | 独立沙盒 /Temp/cf-adv/H8 |
| M1 mutation | 10 项关键 mutation | 独立 git worktree（用后即删） |

隔离规则：主工作树零故障注入；子代理互不知晓对方结论；沙盒目录互不重叠；发现的问题一律不修复。

## 3. 原始设计声明与审查结论

14 条验收声明逐条判定（证据溯源见对应章节/findings）：

| # | 声明 | 结论 | 依据 |
|---|------|------|------|
| 1 | 四个平台可在同一项目同时部署 | **partially-confirmed** | 文件系统层可共存（H1/H2 正向）；但共享 `.claude/skills` last-writer-wins（B-01/H1-01/H2-03）、cursor/opencode 原生 hook 不加载（SEC-3）使"共存且各平台正常工作"不成立 |
| 2 | 任一平台单独 redeploy 不改变其他平台产物 | **disproved** | 共享 skills 树被后写平台覆盖（B-01/H1-01/H2-03）；损坏兄弟 manifest → 跨平台误删（H2-02） |
| 3 | `deploy --platform all` 幂等、顺序无关、中断安全 | **partially-confirmed** | 中断安全成立（H8 无数据丢失、可自愈）；但 24 排列语义**不等价**（H1-01）、首跑非不动点（H1-02）、`all`=ALL_PLATFORMS 与 doctor 语义不一致（H6-06/B-04） |
| 4 | framework.json 声明/锁/本地覆盖/运行状态职责清晰 | **partially-confirmed** | 九类职责落位清晰（A 正向）；但 local 白名单机制不存在、explain 与运行时脱节（A-03/G-06） |
| 5 | 旧版 framework.json 可安全、幂等迁移 | **partially-confirmed** | 主路径幂等、备份先行（D 正向）；但类型错/新旧并存/retired-context 迁移 FAIL（D-03/04/05）、config-migrate 备份污染 rollback 摧毁 .cataforge/（D-01） |
| 6 | 多平台项目无 last-writer-wins 全局平台身份 | **confirmed** | state per-platform、无全局槽、framework.json 部署前后不变（H6 正向）。**注**：`运行时:` 字段有 audience ratchet（只增不减，H6-05），非 last-writer-wins 但非幂等 |
| 7 | AGENTS.md/CLAUDE.md 不形成两个可独立漂移的 SSOT | **partially-confirmed** | 权威链未倒置、活状态保留（H6 正向）；但双写副本无收敛、§执行环境 漂移不可检测（H6-01/02） |
| 8 | per-platform manifest/state 与 shared ownership 模型正确 | **partially-confirmed** | 正常路径正确（B/H2 正向 14+ 项）；但 `--rebuild` 摧毁 merge 型用户配置（H2-01）、损坏 manifest 保护集塌缩（H2-02） |
| 9 | doctor/migration/Hook/skill 按实际目标平台工作 | **disproved** | doctor 平台过滤正确但有 3 类 false PASS（H3-01/02/03/04）；hook 在非 cc 平台 fail-open（SEC-1）；cursor/opencode hook 格式不符（SEC-3） |
| 10 | 多写会话不能在同一工作树静默互相覆盖 | **partially-confirmed** | config set 命令级锁无 lost update（H8 正向）；但锁 TOCTOU 双持/三持（H8-06/07）、无会话级保护、upgrade 无锁（H8-04） |
| 11 | 单平台旧用法保持兼容 | **partially-confirmed** | 纯 v1 单平台 deploy/setup 语义保持（D 正向 fixture 14）；但 `config set` 后 migrate 回退平台选择（D-02） |
| 12 | 用户自定义 agent/skill/rule/command/MCP 不会被误删 | **disproved** | 普通 deploy 保留（H2 正向 6 类）；但 `.claude/rules/` 普通 deploy 即删（B-05）、`--rebuild` 摧毁 settings.json/opencode.json 用户配置（H2-01/E1-02/E4-04） |
| 13 | 文档、Schema、CLI 帮助与实现一致 | **disproved** | 三篇核心新文档对齐度高；但 15 条漂移（G 组），含 generator 模板过不了自家验证器、五处用户文档仍 v1、三条锁/schema overclaim |
| 14 | 测试真实捕获不变量破坏，而非只覆盖 happy path | **disproved** | 7/12 关键 mutation 逃逸测试（M1）；F 组 12 条测试盲区；锁测试软断言掩盖真实缺陷（F-01） |

**统计**：confirmed 1 · partially-confirmed 8 · disproved 5 · not-reached 0（真实 IDE 面见 §12）。

## 4. framework.json 配置验收矩阵

| 验收项 | 结论 | finding |
|--------|------|---------|
| 九类职责分离（声明/锁/catalog/local/secrets/manifest+state/session/last-run/tmp） | PASS（唯一同文件共存=framework.json 承载声明配置+框架 catalog，字段级所有权设计使然） | A 正向 #1 |
| deploy/doctor/platform-detection 不写回 framework.json | PASS | A 正向 #2/3/4 |
| local config gitignored | PASS | A 正向 #5 |
| secrets 仅存引用（`upgrade.source.token_env` 存变量名） | PASS | A 正向 #1 |
| 框架 catalog 防 `config set` 覆盖 | PASS（白名单外 FAIL） | A 正向 #6 |
| 五层解析优先级（CLI>env>local>project>defaults） | PASS（deployment.default_platform 逐层实测） | A 正向 #7 |
| local 层对非白名单字段生效性 | **FAIL** — explain 报 local 生效、运行时忽略（白名单机制不存在） | A-03 / G-06 |
| newer-schema 写保护（所有读写命令 FAIL） | **FAIL** — config get/set 照常读写 v3 文件 | A-02 / G-07 |
| 所有 framework.json 写路径持 config.lock | **FAIL** — migrate/scaffold/upgrade 三路径无锁 | A-07 / G-05 / B-09 / H8-04 |
| config.lock 正常并发无 lost update | PASS（25×2 轮 0 损坏） | H8 §9 |
| 锁 stale/TTL 场景互斥 | **FAIL** — TOCTOU 双持/三持 | A-01 / H8-06/07 |

## 5. 旧配置迁移矩阵（D 组 12 类 fixture 实测）

| # | fixture | 迁移 | 备份 | 幂等 | 失败恢复 |
|---|---------|------|------|------|---------|
| 1 | 无 schema_version | PASS | PASS | PASS | PASS |
| 2 | 旧 runtime.platform 单字段 | PASS | PASS | PASS | PASS |
| 3 | 缺字段 | PASS | PASS | PASS | PASS |
| 4 | 未知字段 顶层+嵌套 | PASS（保留）；action 日志失真(D-08) | PASS | PASS | PASS |
| 5 | 类型错误 | **FAIL**(D-04/D-11 静默丢弃+崩溃) | PASS | PASS | PASS |
| 6 | 已删除字段(retired context) | **FAIL**(D-05 migrate 不处理，doctor 仍 FAIL) | PASS | 假"完成" | PASS |
| 7 | 重命名/新旧并存 | **FAIL**(D-03 default∉targets validate-FAIL) | PASS | PASS | PASS |
| 8 | 插件命名空间 | PASS | PASS | PASS | PASS |
| 9 | v2→旧运行时 | **FAIL**(D-06 无检测静默降级) | N/A | N/A | N/A |
| 10 | 截断/损坏 JSON | FAIL-CLEAN(预期拒绝 exit 1，原文件完好) | N/A | N/A | PASS |
| 11 | UTF-8/CJK | PASS | PASS | PASS | PASS |
| 12 | Windows 反斜杠路径值 | PASS | PASS | PASS | PASS |

**额外致命项（矩阵外）**：D-01 — config-migrate 备份进入 rollback 快照池且字母序恒排第一，`upgrade rollback` 默认选中它 → `restore_backup` 删空 `.cataforge/` 后仅还原单个 framework.json（agents/skills/state 全灭）。D-02 — `config set` 平台选择被随后任一 migrate 静默回退。

## 6. 四平台 24 排列测试结果（H1 动态实测）

**结论：24 排列语义等价性 disproved（硬门槛不成立）。** 全树 sha256 比较（仅排除 `.git/`；24 沙盒均无 EVENT-LOG 等日志噪音，无需额外排除项）。

- **IDE 产物层恰分 2 个等价类（12/12）**，分界 = claude-code 与 cursor 的相对部署顺序。再排除 `.claude/skills/` 后 24 个全同——即唯一分歧源是共享 skills 树。
- 差异文件 = `.cataforge/skills/` 中全部 8 个含 `{INSTRUCTION_FILE}` token 的文件（framework-review/update/walkthrough 的 SKILL.md + 2 个 references、penpot-bridge、start-orchestrator、ui-design）。cursor 晚部署 → 渲染为 AGENTS.md 口径；claude-code 晚部署 → CLAUDE.md 口径。**行为级分歧**：cursor 口径的 `start-orchestrator/SKILL.md` 指示 orchestrator「AGENTS.md 不存在→新项目分支」「仅更新 AGENTS.md §项目状态」——Claude Code 用户在 cursor 后部署（含 `deploy --platform all`，其内部 cursor 晚于 claude-code）后，编排把状态写进错误的指令文件。
- 机制锚点：cursor profile `skill_definition.target_dir: .claude/skills`（与 claude-code 同目录），skills 步骤对 `{INSTRUCTION_FILE}` 逐平台解析且**无 audience 感知**（`neutral` 中性渲染仅 `steps/instructions.py` 启用），后写者胜。坐实 B-01 / H2-03。

**metamorphic（H1）**：
- (a) `deploy --platform all` ≡ 逐平台部署（IDE 产物层字节相同）——但 `all` 内部 cursor 晚于 claude-code，故给 `.claude/skills` 留下 AGENTS.md 口径。
- (b) `all` 连跑 3 次：**第 1→2 次非不动点**（claude-code + cursor 两个 manifest 的 `source_digest` 变化），第 2→3 次零变化。诱因：codex deploy 生成 auto-prompt 文件落入 `drift.py._SOURCE_DIRS` 覆盖区，使先部署平台 baseline 立即过期 → 新鲜全量部署后 doctor 报**假阳性漂移 WARN**（H1-02）。
- (c) `all` 后单平台重部署：owned_paths 判据 PASS（未越权），但 claude-code/cursor 重部署使 8 个共享 skill 文件内容乒乓翻转；codex/opencode 重部署零变化。所有权边界精确（m2 篡改各平台 owned 文件后仅对应平台恢复）。

**H1 正向核查**：framework.json 不被 deploy 改写（24 after 全同）、owned_paths 顺序无关、doctor 只读无副作用、CLAUDE.md/AGENTS.md 24/24 字节全同（H1-03 confirmed「AGENTS.md 按声明 audience 渲染、顺序无关」）、源 skills 树永不被渲染污染、退出码全 0。

## 7. shared ownership 验证

**B 组（部署所有权，静态+沙盒动态）已返回**，正向核查 14 项通过（单平台 prune 只读自身 manifest、最后 owner 删除收敛、rebuild 不越界他平台、AGENTS.md 顺序无关、用户 commands/skill 子目录/agent 存活、manifest 损坏失败方向安全〔空集=不 prune〕、首次部署不 prune、三个 deploy 调用点全持锁、路径逃逸防护、legacy 迁移主路径幂等、junction 删除安全）。

对抗突破口（详见 §13 findings B-01…B-12）：
- **B-01 HIGH**：cursor 与 claude-code 共用 `.claude/skills`，含平台占位符的 8 个 skill 源按"当前平台"渲染整目录覆盖 → 共享 skill 产物 **last-writer-wins**，单平台 redeploy 即改写兄弟平台可见内容，无检测无告警（待 H1 排列实测交叉验证）。
- **B-02/B-03 HIGH**：`--rebuild` 把 merge 语义的 `.claude/settings.json`（用户 permissions/自建 hooks/env）与 `opencode.json`（用户 model/provider/MCP）整文件删除后仅以框架内容重建 —— 沙盒实测用户配置全部丢失，与 help 文案"user-authored files never touched"直接矛盾。
- **B-05 MEDIUM**：`.claude/rules/` 为目录级 wipe-and-replace，**普通 deploy** 即静默删除用户手写规则文件（非 rebuild 路径）。
- **B-06 MEDIUM**：cursor `.mdc` 规则无孤儿 prune，删源后 `alwaysApply: true` 的孤儿规则永久注入会话。
- **B-04 MEDIUM**：平台退出 `deployment.targets` 后 ownership 永久泄漏（无 retire 路径）；`deploy --platform all` 遍历 ALL_PLATFORMS 而非声明 targets。
- **B-10 MEDIUM**：MCP 配置与 opencode hook 插件从不入 manifest → doctor integrity 盲区（但因此 rebuild 不删它们——与 B-02/03 形成双标）。

## 8. 故障注入结果（H8 动态实测）

**部署阶段故障注入：无 CRITICAL，事务安全。** 模式 = hardexit（`os._exit`，跳过 finally，模拟 kill -9/断电），7 个中断点（after agents / instruction_files / hooks / rules / skills / mcp / **manifest↔state 之间**）。提交次序 = manifest.json 先、state.json 后，且都在全部产物落盘之后。**所有中断点下次 deploy 均完美收敛（逐文件 sha256 diff=0），无数据丢失，部分态可自愈。**

- **H8-01 HIGH**：mid-pipeline 中断留下无 manifest 的孤儿产物（如 after-agents 时盘上 13 个 agent 文件、无 CLAUDE.md/rules/skills），`doctor` 把"无 manifest"一律等同"从未部署"→报 "no deploy has been run yet — skipping integrity gate" + "✔ all passed" exit 0。half-broken 树 false green。与 H3-01 同族（doctor 可见性缺陷）。缓解：doctor 消息本身未宣称部署成功、下次 deploy 干净收敛，故非 CRITICAL。
- **H8-02 MEDIUM**：只读目标（icacls 拒写 `.claude/agents`）→ deploy 抛裸 `PermissionError [Errno 13]` traceback 无 actionable 提示（对比 JSON 损坏给出干净 `Error: Malformed JSON`）；状态一致、恢复收敛。
- 环境故障正向核查：framework.json 截断 → deploy/doctor/config get 全 exit 1 精确报错无裸 traceback；stale/空/非 JSON 锁均正确回收自愈。

## 9. 并发配置/deploy/session 结果（H8 动态实测）

**并发写正常路径 PASS，崩溃恢复期与 upgrade 路径 FAIL。**

- **config set 并发**（不同字段 25 轮×2 相 / 相同字段 25 轮）：**0 损坏、无 lost update、last-writer-wins**——config.lock 正常路径正确。验收硬门槛「并发写入无 lost update」在此路径成立。
- **并发 deploy**：两/六路 `deploy --platform all` = 1 赢 exit 0、余拒 exit 1（LockHeldError + git worktree 指引），无交错写；all vs 单平台经项目级 deploy_lock 互斥。正确。
- **锁竞态三窗口确定性实测**（坐实 A-01/A-09/B-08/F-01）：
  - **H8-06 HIGH**（窗口 b）：stale 回收 TOCTOU——A/B 同判 stale，B 装新锁，A 无条件 unlink 删掉 B 的**活锁** → 双持。确定性复现 VIOLATION。
  - **H8-07 HIGH**（窗口 c）：finally 无条件 unlink + TTL 偷锁——A 超 TTL 被 B 偷锁（二者同时自认持锁），A 退出 finally 删 B 活锁 → C 再入 → **三方并发持锁**。steal 压测（ttl=0.02s）1226/1250=98% 临界区重叠。
  - **H8-05 MEDIUM**（窗口 a）：空文件读→corrupt 回收→双持，POSIX 逻辑可达，**Windows 被 OS 挡住**（持锁进程 open 期间竞争者 unlink 抛 WinError 32），自然双持 0/N。
- **H8-03 MEDIUM**：硬崩溃（os._exit）泄漏锁，死 PID 却须等满 TTL（deploy 30 分钟），LockHeldError 文案 "another CataForge write operation is in progress" 误导（PID 已死却称进行中），未提示可手删锁。优雅异常（Ctrl-C）finally 正确释放。
- **H8-04 MEDIUM**：`upgrade apply`（migrate + copy_scaffold_to）全程无锁，与 deploy/config-set 不互斥（坐实 A-07/G-05/B-09）。
- **多写会话/worktree**：无 lease/session 子系统，仅命令级文件锁；每条 mutating 命令在其锁内原子（config set 的 load-modify-write 全在锁内），但**跨命令的读—决策—写序列无会话级保护**（应用层交错，非锁缺陷）。git worktree：`.cataforge/state/`（含 locks）gitignored → per-worktree，跨 worktree 不共享锁 → 并行部署互不影响，worktree 指引成立。

### H8 组（故障注入+并发）完整清单

| id | sev | verdict | 一句话 |
|----|-----|---------|--------|
| H8-01 | HIGH | confirmed | mid-pipeline 中断留无 manifest 孤儿产物，doctor false green（与 H3-01 同族） |
| H8-06 | HIGH | confirmed(确定性) | 锁窗口 b：stale 回收 TOCTOU 删活锁 → 双持（坐实 A-01） |
| H8-07 | HIGH | confirmed(98%) | 锁窗口 c：finally 无条件 unlink + TTL 偷锁 → 三方并发持锁（坐实 A-01/F-01） |
| H8-02 | MEDIUM | confirmed | 只读目标 deploy 裸 PermissionError traceback |
| H8-03 | MEDIUM | confirmed | 硬崩溃泄漏锁、死 PID 等满 TTL、文案误导（坐实 A-09） |
| H8-04 | MEDIUM | confirmed | upgrade 路径全程无锁（坐实 A-07/G-05/B-09） |
| H8-05 | MEDIUM | partially | 锁窗口 a：POSIX 逻辑可达、Windows 被 OS 挡（不可复现） |

H8 正向核查：deploy 事务安全（manifest→state 次序 + 全产物后提交，无数据丢失、可自愈）、config.lock 正常路径无 lost update、并发 deploy 干净 fail-fast、worktree 隔离、优雅异常正确释放锁。**H8 明确判部署故障注入面无 CRITICAL。**

## 10. doctor 验收矩阵（H3 动态实测，12 场景 × 调用形态）

**结论：平台作用域与 remediation 收敛面质量良好，但 manifest/config 信任链存在 3 条 HIGH false PASS。**

PASS 场景（exit code + 行为均正确）：①仅一平台部署时未部署平台报 "not deployed" 而非 FAIL/静默；②四平台全部署各自独立 verified；④删单平台产物只该平台 FAIL+精确 remediation，他平台不牵连；⑤删共享 AGENTS.md 三共有平台各自 FAIL、单次 redeploy 全收敛；⑦migration check 平台过滤精确（cc FAIL、其余 SKIP "not applicable"）；⑨删共享 skill 目录双 owner 各报、一次 deploy 收敛；⑪c JSON 语法坏 → 单行精确报错 exit 1 无 traceback；`--platform bogus` → exit 1 + choices 列表。remediation 实际执行后 doctor 均收敛，无死循环建议。

**false PASS 场景（命中验收红线）**：

| 场景 | 现象 | finding |
|------|------|---------|
| ③ codex manifest 截断 | doctor --platform codex exit 0 "empty manifest — nothing to verify"；组合铁证：截断 manifest **并删** architect.toml 仍全绿 | H3-01 HIGH |
| ⑥ 有 MCP 但删 `.codex/config.toml` | exit 0（MCP 产物从不入 manifest） | H3-02 HIGH |
| ⑩a/b stale deploy 半记录 | 删 manifest 留 state.json → false PASS；删 state.json 留 manifest → 完全静默 | H3-01/H3-05 |
| ⑪a schema_version=99 | doctor exit 0，而 `config validate` exit 1 精确报错 | H3-03 HIGH |
| ⑪b targets 类型错 | exit 0 且垃圾串 "not-a-list" 进入 platform scope | H3-04 HIGH |
| ⑫ TTL 内残留 deploy lock | doctor exit 0 零提示，但其处方 `deploy` 被锁拒 exit 1 | H3-06 LOW |

状态词汇表实测：OK/FAIL/WARN/SKIP/NOTE/"not deployed"/"not applicable — requires platform(s)"/"requires deploy"/"empty manifest"，五种语义节级文本可区分（无规范化 token，散文措辞）；退出码二值（0 含 WARN/SKIP/not-deployed，1 为门禁 FAIL 或 CLI 错误）。两处语义塌缩：corrupt/missing manifest 塌缩进 "empty manifest"（H3-01 表象）；总结行对"平台未部署"不留痕。

### H3 组（doctor 对抗）完整清单

| id | sev | verdict | 一句话 |
|----|-----|---------|--------|
| H3-01 | HIGH | confirmed(false PASS) | manifest 损坏/缺失 → `_owned_paths_from_file` 返空集 → 完整性门禁静默永久关闭（与 H2-02/H2-04/F-09 交叉） |
| H3-02 | HIGH | confirmed(false PASS) | `_deploy_mcp` 接收 manifest 但从不 record → MCP 产物删除后 doctor 全绿（与 B-10/E4-05 交叉） |
| H3-03 | HIGH | confirmed(false PASS) | schema_version=99 doctor exit 0，config validate 却 FAIL（与 A-02/G-07 交叉） |
| H3-04 | HIGH | confirmed(false PASS) | targets 类型错误 doctor 全绿且垃圾 id 进 platform scope |
| H3-05 | MEDIUM | partially | state.json/manifest 半记录不互相印证；孤儿产物零提示 |
| H3-06 | LOW | confirmed | 残留 deploy lock doctor 不提示，但其 remediation 被锁拒 |

H3 正向核查 8 项通过（平台区分、remediation 收敛无死循环、可选 config.toml 不误判必需、migration 平台过滤、§项目状态 漂移 WARN 方向正确、JSON 语法错精确报错、bogus 平台拒绝、锁 TTL 自愈）。

## 11. mutation sensitivity（M1 隔离 worktree 实测）

**结论：硬门槛「关键 mutation 均被测试捕获」不成立——12 变体中 5 CAUGHT / 7 GAP-CONFIRMED。** F 组静态预测方向全部证实（唯一细节偏差：#7 的第二个预测测试名归属另一代码层，正确留守未失败）。基线 3254 passed / 4 skipped（`-m "not slow"`，分片合计恒等）。

| # | mutation | 实测 | 逃逸测试的缺口 |
|---|----------|------|----------------|
| 1 | 回退全局单 manifest | **CAUGHT**（5 失败） | — |
| 2 | 移除 migration 平台过滤 | **GAP** M1-01 | run_migration_checks 平台过滤零测试 |
| 3a | overwrite 渲染仅当前平台 | **CAUGHT**（2 失败，命中预测） | — |
| 3b | section-merge always_overwrite 写单平台值 | **GAP** M1-02 | 共享 AGENTS.md 顺序稳定测试回避 section-merge 分支；单元测试 tpl 值与 platform_id 共谋（退化用例） |
| 4 | 单平台 prune 越权 | **CAUGHT** | — |
| 5a | deploy_lock → nullcontext | **CAUGHT** | — |
| 5b | 仅删 CLI 侧 lock 包裹 | **GAP** M1-03 | 「部件有测试、装配无测试」缝隙 |
| 6 | config set 非原子写 | **GAP** M1-04 | _write_raw 原子性只在 docstring |
| 7 | 删同值短路 | **CAUGHT**（1/2 预测命中） | — |
| 8 | skill 可达性检查恒 PASS | **GAP** M1-05 | 整个 gating check 零测试引用 |
| 9 | doctor 误把可选 config.toml 当必需 | **GAP** M1-06 | integrity 缺「负向断言」（不该 FAIL 的场景） |
| 10 | hook 多 target 歧义静默回退 | **GAP** M1-07 | get_platform 探测链分支级零测试 |

系统性根因：doctor 各 check「仅注册即视为覆盖」（M1-01/05/06）+ 关键写路径「原语有测试、消费点/接线无测试」（M1-03/04）+ 多平台字段稳定性「测试回避真实 merge 路径」（M1-02，与 F-04 交叉）。

### M1 组（mutation 敏感度）完整清单

| id | sev | verdict | 逃逸的不变量 |
|----|-----|---------|-------------|
| M1-01 | HIGH | confirmed | migration check 平台过滤（回归后 codex-only 项目 doctor 误 FAIL） |
| M1-02 | HIGH | confirmed | 共享 AGENTS.md 运行时字段 audience 稳定性（回归后 last-writer-wins） |
| M1-03 | HIGH | confirmed | deploy CLI 锁接线（回归后并发 deploy 交错写） |
| M1-04 | HIGH | confirmed | _write_raw 原子性（回归后半写 framework.json 砖死项目） |
| M1-05 | HIGH | confirmed | skill 可达性门禁（回归后声明漂移静默通过） |
| M1-06 | HIGH | confirmed | doctor 误报方向（回归后未启用 MCP 的 codex 项目永久 FAIL） |
| M1-07 | HIGH | confirmed | hook 歧义熔断（回归后多平台 hook 静默按 default 解析，与 SEC-1 同后果） |

## 12. 真实 IDE 覆盖情况

**Claude Code（真实 smoke，版本 2.1.202，headless `claude -p`）— PASS**：

- 沙盒初始化：`git init && cataforge bootstrap --platform claude-code`（setup+deploy+doctor 全绿）
- 项目指令加载：会话不读文件即报出 CLAUDE.md 首标题 `# CataForge` ✓
- agent 原生注册：subagent types 列表含 architect/debugger/devops/implementer 等 CataForge 部署 agent ✓
- skill 原生可见：tdd-engine、start-orchestrator 均在会话可用 skills 列表 ✓（第二轮曾自报缺 start-orchestrator，第三轮定向复核证实存在——模型自报误差，非部署缺陷）
- Hook 真实执行：PreToolUse `guard_dangerous` 拦截 `rm -rf zzz-not-here-xyz`，会话原样回显拦截消息 "BLOCKED: Recursive force delete detected（建议改用 trash-cli…）" ✓；hook 命令行显式携带 `--cataforge-platform claude-code` ✓
- 前提条件记录：hook 命令为裸 `python -m cataforge.runtime.hook.scripts.*`，验证时需将项目 venv Scripts 目录置于 PATH；真实用户会话若 PATH 上的 python 不可导入 cataforge 则 hook 降级（见平台适配 findings）

**Cursor / Codex / OpenCode — not-reached（真实 IDE 会话），但 contract 级核对官方最新文档发现严重不符**：本机无 agent CLI（cursor 仅编辑器打开器）。各平台产物与厂商官方文档（均访问 2026-07-14）逐项对照：

- **Cursor**（docs 版本核至 v3.11）：`.cursor/hooks.json` 缺必需 `version:1` 且用错误嵌套形状 → Cursor 3.x hook 全不加载（E3-01 CRITICAL，第三方 issue affaan-m/ECC#1519 佐证）；`.cursor/rules/*.mdc`、mcp.json、AGENTS.md 格式**符合**（E3 正向 13 项）。
- **Codex**（developers.openai.com→learn.chatgpt.com）：hooks.json/agents.toml/MCP schema **符合**官方；但 profile 三处厂商事实过时（matcher 仅 Bash→实为可拦 apply_patch/mcp_*、无 skill 面→已支持 `.agents/skills/`、per-agent model 不可用→已支持，E2-05/06）；产物需 trust 才生效未在 guide 提及（E2-07）。
- **OpenCode**（v1.17.20）：生成的 plugin 用不存在的 `event.on()` API、不返回 hooks 对象 → 加载即 TypeError（E4-01 CRITICAL）；`.opencode/plugins`/agents/mcp/AGENTS.md 路径**符合**（E4 正向 12 项）。

结论**不写作"真实平台已通过"**；SEC-3 为产物-vs-文档 confirmed + 第三方佐证，真实 IDE 会话内的加载失败未观测（见 §14）。

## 13. Findings

### 13.0 确认的 CRITICAL / HIGH 阻塞项（协调者交叉验证后）

**CRITICAL**

- **[SEC-1] 危险命令守卫在非 claude-code 平台静默 fail-open**（合并 H5-01 + E2-01 + E2-02，协调者亲手复现坐实）。`guard_dangerous.main()` 以 `matches_capability(data,"shell_exec")` 为闸门，而 `matches_capability` 只查 tool_map、不查 `hooks.tool_overrides`；且 profile.yaml 读取在 `registry.py:72` / `base.py:153` 是裸 `open()`（无 encoding），hook 进程入口不经 `ensure_utf8()`。两条路径叠加出双向失防：
  - **cp936/GBK locale（框架中文定位，维护者本机默认，实测 `getpreferredencoding=cp936`）**：读含 em-dash 的 profile 抛 `UnicodeDecodeError` 被 `_load_tool_map` 静默吞 → tool_map 退化为 claude-code 硬编码（`shell_exec: Bash`）→ cursor 的 `Shell` 事件失配 → 放行。**协调者实测**：cursor 沙盒 `{"tool_name":"Shell",...rm -rf...}` → EXIT=0；同输入 PYTHONUTF8=1 → EXIT=2 BLOCKED；claude-code baseline → EXIT=2。
  - **UTF-8 locale**：codex tool_map 正确加载但 `matches_capability` 不认 `hooks.tool_overrides` → codex 的 `Bash` 事件与 `shell_exec: shell` 失配 → 放行（E2 复现 exit 0）。
  - **第三条独立路径（E1-01）**：claude-code profile 把 `CATAFORGE_PLATFORM=claude-code` 种进 `.claude/settings.json#env`（profile.yaml:92-96），官方文档确认该 env 传给 Claude Code 派生的所有子进程；`get_platform()` 中 env 优先级高于 argv（base.py:58-67）。于是一旦部署过 claude-code，同机的 codex/cursor/opencode 会话里 hook 恒解析为 claude-code → tool_map 错配 → 守卫对真实工具名（shell/Shell/bash）失配放行。实测 `CATAFORGE_PLATFORM=claude-code` + `--cataforge-platform codex` argv → 解析 claude-code，`git push --force` 喂 codex 形态 stdin → EXIT=0。这正是本 commit 服务的"单机多 IDE 共存"场景。
  - **归属**：#487 新增的 `--cataforge-platform` argv stamping（base.py:61-77，属本 commit diff）使 cursor/codex/opencode 身份解析从偶发变为**必现**，把潜藏缺陷激活为每次触发。落在验收范围「hook / 平台适配 / 降级是否显式 / 多平台身份」。
  - **影响**：无人值守循环把 `guard_dangerous` 当作 prompt 无法保证的工具级安全网；该网在 cursor/codex/opencode 上于目标受众语言环境静默破洞，`rm -rf` / `git push --force` / `git reset --hard` 均可穿透，无任何告警。affected: cursor, codex, opencode。
- **[SEC-2 / F-01] 锁互斥测试是软断言且掩盖真实 Windows 缺陷**。`test_exclusive_within_process` 的 worker 线程异常仅降级为 pytest warning，测试恒绿；实际掩盖 `locks.py:103-105` release 的 `unlink` 在锁文件被并发读取时抛 WinError 32 被 `suppress(OSError)` 吞掉（F 组 2000 次复现 1867 次），锁滞留至 TTL，后续 fail-fast deploy 连续被拒最长 30 分钟。**协调者旁证**：全量 pytest 运行时该测试确实喷 `PytestUnhandledThreadExceptionWarning: LockHeldError` 却仍 `1 passed`。
- **[H2-01] `--rebuild` 摧毁 merge 型 JSON 配置中的全部用户内容**（H2 双向对照实测，B-02/B-03 从 HIGH 升级）。`_rebuild_purge` 的 protect 集只含 section-merge 指令文件，不含 hooks config / opencode.json 等"状态活在目标文件内"的 merge 型目标；`deploy --rebuild` 整删后仅重建框架条目。实测：`.claude/settings.json` 的 `permissions`/env/用户 hooks、`opencode.json` 用户顶层键在 rebuild 后全部蒸发，无警告、无备份、exit 0。`--rebuild` 被文档定位为"从损坏部署恢复"的推荐命令——用户在最需恢复时静默丢失全部权限白名单与主配置。命中「用户自定义文件可能被误删」。affected: 全部平台。
- **[H2-02] 损坏的兄弟平台 manifest 使跨平台保护集静默失效 → 误删他平台产物**（H2 动态坐实协调者假设，B/F 静态推演的实证）。`_owned_paths_from_file`（manifest.py:91-103）对 ConfigError 静默返回空集，`load_other_platform_owned` 保护集因此塌缩。实测：四平台部署 + 自定义 skill 被 cc/cursor 双认领后，截断 cursor manifest → `deploy --platform claude-code` 立即 `pruned orphan .claude/skills/h2-shared`（对照组 manifest 完好时该产物存活至 cursor 自己 redeploy）；`--rebuild` 变体共享 skills purge 计数 0→26。deploy 与 doctor（H2-04）双面零告警。命中「一个平台会删除其他平台产物」。affected: 全部平台。
- **[SEC-3] cursor/opencode 平台原生 hook 载体格式与厂商 API 不符 → hook 全线不加载**（E3-01 + E4-01，contract 级 confirmed；真实 IDE 运行 not-reached，本机无 cursor-agent/opencode）。与 SEC-1（加载了但 fail-open）机制不同，这里是产物根本不被平台接受：
  - **cursor**：`.cursor/hooks.json` 缺 Cursor 3.x 必需的顶层 `"version": 1`，且沿用 Claude Code 嵌套形状 `{matcher, hooks:[{type,command}]}`（Cursor 要求扁平 `{command, matcher}`）。官方 hooks 文档 + 第三方 issue（affaan-m/ECC#1519「missing required version field, all hooks fail to load on Cursor 3.x」）佐证。12 个 hook 含 `safety_critical` 的 guard_dangerous/guard_frozen_docs。测试 `test_bridge.py` 把错误嵌套形状锁成"正确"。
  - **opencode**：生成的 `.opencode/plugins/cataforge-hooks.ts` 用 `event.on()` API 并解构 `{app, event}`，而官方 Plugin API 入参为 `{project, client, $, directory, worktree}`（无 event/app），hook 必须以**返回对象的键**注册。插件加载即 `TypeError`，11 个 "native" hook 零注册。测试仅 `node --check` 语法校验，无 API 契约断言。
  - 两者叠加共同点：deploy 与 doctor 全绿、profile 标 native，制造"hook 已就位"的虚假保障。直接反驳「四平台可共存且 hook 按实际平台工作」的核心验收目标。affected: cursor, opencode。归属：BASE 既有格式缺陷，但被 #487 的"多平台一等公民 + doctor 报 native"背书放大。

**HIGH（按主题聚类，多为独立多代理交叉确认）**

- **锁并发正确性**（A-01 双持锁 + A-09 无限忙等 + B-08 steal 竞态 + F-01 release 失效，四代理独立收敛 `utils/locks.py`）：steal 路径 unlink 他人新锁致双进程同持；finally 无条件 unlink 删偷锁者的锁；stale 分支 unlink 失败 `continue` 绕过 deadline 忙等。护的正是 framework.json / deploy state 的 RMW，双持锁即 lost update。待 H8 多进程压测确认复现率。
- **用户文件误删**（B-02/B-03 `--rebuild` 整删 `.claude/settings.json`+`opencode.json` 用户配置〔沙盒实测〕；B-05 普通 deploy 即删 `.claude/rules/` 用户手写规则）——命中验收红线「用户自定义文件可能被误删」。
- **共享产物 last-writer-wins**（B-01 共享 `.claude/skills` 按当前平台渲染整目录覆盖）——命中「一个平台覆盖另一个平台产物」；待 H1 排列实测确认语义等价性是否被打破。
- **前向兼容写保护缺失**（A-02 + G-07，双代理交叉实测）：schema_version=3 时 `config get/set` 照常读写，文档称"所有读写命令显式 FAIL" overclaim；旧运行时可污染新 schema。
- **config.local.json 双真相**（A-03 + G-06，双代理交叉实测）：`config get/explain` 报 local 生效，运行时消费方只读 framework.json；白名单机制不存在。
- **迁移可致数据/配置丢失**（D-01 config-migrate 备份污染 rollback 快照池 → `upgrade rollback` 摧毁整个 `.cataforge/`〔直调实测〕；D-02 `config set` 平台选择被随后任一 migrate 静默回退）——命中「配置迁移可能丢数据 / 不可恢复」。
- **锁 overclaim**（G-05 + A-07 + B-09，三代理交叉）：upgrade apply / setup scaffold / config migrate 三条 framework.json 写路径无锁，文档承诺的并发保护不存在——命中「并发写入会 lost update」。
- **文档/契约系统性漂移**（G-01…G-04：PROJECT-STATE.md 模板、framework-update SKILL、generator 验证器、五处用户文档仍 v1；generator 模板过不了自家验证器〔实测〕；下次 deploy 会回滚本 PR 改对的 CLAUDE.md）。
- **测试盲区致不变量无守护**（F-02 deploy lock CLI 层零测试；F-03 doctor `--platform`/两个新检查段零测试；F-04 AGENTS.md 顺序稳定性回避真实 section-merge 路径）——待 M1 mutation 实测坐实。
- **平台适配**（E2-03 TOML 未转义 body；E2-04 CODEX_HOME 假信号劫持身份）。

（下方各组完整清单，去重后终判见 §16）

### 协调者直接取证（主线程第一手）

#### [R-COORD-1] MEDIUM: 全量 pytest 存在 1 例陈旧失败测试（升级保留契约的 e2e 无保护）
- **category**: test-quality
- **root_cause**: self-caused
- **描述**: `tests/e2e/test_install_and_upgrade.py::test_upgrade_apply_preserves_user_mods_and_runtime_platform` 在 HEAD 必然失败：断言 `fw["runtime"]["platform"] == "claude-code"`（v1 布局），而 v2 `setup` 已写 `deployment.default_platform`、不再产生 `runtime` 键（沙盒实测确认 fresh setup 无 `runtime` 键）。#487 测试计划仅跑 `-m "not slow"`，该 slow e2e 从未在 v2 下执行。
- **影响**: (a) `uv run pytest`（全量）在 main 上红，"所有必需测试通过"验收门不成立；(b) "upgrade apply 保留用户修改"这一声明当前失去可运行的 e2e 保护。
- **证据**: pytest-full.log — `1 failed, 3273 passed, 6 skipped in 510.15s`；KeyError: 'runtime' at tests/e2e/test_install_and_upgrade.py:144。

#### [R-COORD-2] MEDIUM: run_local 在 Windows 开发机不绿（mypy strict 平台性失败）
- **category**: consistency
- **root_cause**: upstream-caused（#485 引入，非被审 #487）
- **描述**: `src/cataforge/runtime/unattended.py:206` 在 `os.name == "nt"` 的 else 分支调用 `os.killpg/os.getpgid/signal.SIGKILL`；运行时安全，但 mypy 不对 `os.name` 做平台收窄，Windows 上 strict 报 3 错 → `run_local.py` FAIL。CI（Linux）不受影响，即"本地通过 ≈ CI 通过"的承诺在 Windows 上被打破。
- **建议方向**: 用 `sys.platform` 守卫替代 `os.name` 分支（mypy 可收窄），或对该行加显式 type: ignore[attr-defined] 并注明平台条件。

#### [R-COORD-3] MEDIUM: 深路径项目 bootstrap 直接 FileNotFoundError（Windows MAX_PATH）
- **category**: error-handling
- **root_cause**: self-caused（长期存在，非 #487 引入；#487 的 scaffold 路径深度维持现状）
- **描述**: scaffold 内最深文件相对路径约 97 字符（`.cataforge/skills/workflow-framework-generator/templates/platform-profiles/claude-code.yaml.tmpl`）；项目根绝对路径超过约 160 字符时，未启用 LongPathsEnabled 的 Windows 上 `copy_scaffold_to` 抛裸 `FileNotFoundError`（实测复现于 268 字符路径），无诊断信息。
- **建议方向**: scaffold 复制失败时给出 MAX_PATH 定向提示；或文档声明路径深度前提。

### B 组（部署所有权）完整清单

| id | sev | verdict | 一句话 | 关键锚点 |
|----|-----|---------|--------|----------|
| B-01 | HIGH | confirmed | 共享 `.claude/skills` 按当前平台渲染整目录覆盖，last-writer-wins，8 个含占位符 skill 受影响；coexistence 测试刻意绕开该目录 | steps/skills.py:136,174-181; cursor profile `skill_definition.target_dir` |
| B-02 | HIGH | confirmed | `--rebuild` 整删 `.claude/settings.json` 后重建，用户 permissions/自建 hooks/env 全丢（沙盒实测） | deployer.py:195-204,528-572; hooks_config.py:84-143 |
| B-03 | HIGH | confirmed | 同上于 `opencode.json`（OpenCode 主配置：model/provider/MCP 全丢） | opencode.py:64-65 |
| B-04 | MEDIUM | confirmed | 平台退役无路径：ownership/audience/state 永久泄漏；`--platform all` 遍历 ALL_PLATFORMS 非声明 targets | manifest.py:140-150,191-205; deploy_cmd.py:147-148 |
| B-05 | MEDIUM | confirmed | `.claude/rules/` 目录级 wipe：普通 deploy 静默删用户手写规则（实测） | steps/commands_rules.py:95,106; steps/skills.py:170-172 |
| B-06 | MEDIUM | confirmed | cursor `.mdc` 无孤儿 prune：删源后 `alwaysApply: true` 规则永久注入 | adapter/platform/cursor.py:35-44,90-124 |
| B-07 | MEDIUM | partially | 中断窗口一半可检测（missing→doctor FAIL 自愈）、一半永久盲（已写未入 manifest 的 orphan） | deployer.py:233-257 |
| B-08 | MEDIUM | partially | 锁 steal 竞态（unlink 他人新锁→双持）与 release 无条件 unlink（删偷锁者的锁）——代码推演，待 H8 实测 | utils/locks.py:88-105 |
| B-09 | MEDIUM | confirmed | `upgrade apply`/setup 的 scaffold 重写不持 deploy 锁：并发时混版本产物 + drift 基线掩蔽 | upgrade_cmd.py:186-215; setup_cmd.py:178 |
| B-10 | MEDIUM | confirmed | MCP 产物/opencode hook 插件不入 manifest：doctor integrity 盲区、docstring 失实 | deployer.py:659-679; steps/mcp.py:12-32 |
| B-11 | LOW | partially | legacy 双记录同时损坏时仍无条件 unlink（所有权记账未迁移即删除） | manifest.py:246-268 |
| B-12 | LOW | confirmed | 仅 framework.json 有部署快照：源文件 mid-deploy 变更使 drift 基线记新源、产物为旧渲染 | deployer.py:181-183,241-248 |

### G 组（文档与契约漂移）完整清单

| id | sev | verdict | 一句话 | 关键锚点 |
|----|-----|---------|--------|----------|
| G-01 | HIGH | confirmed | PROJECT-STATE.md 模板 §统一配置仍是 v1 叙述；下次 deploy 会把本 PR 改对的 CLAUDE.md 回滚 | .cataforge/PROJECT-STATE.md:85-90 vs CLAUDE.md:75-79 |
| G-02 | HIGH | confirmed | framework-update SKILL.md 指示把 `upgrade.state` 写回 framework.json（主动重建 v1 布局）+"全量覆盖"承诺与实现相反 | SKILL.md:111,122,182,191 vs upgrade_state.py / scaffold.py:267-282 |
| G-03 | HIGH | confirmed | generator 模板已 v2 但自带验证器仍强制 `runtime.platform` → 生成产物过不了自家验证（实测复现） | framework.json.tmpl vs validate_framework.py:257-260 |
| G-04 | HIGH | confirmed | 五处用户文档保留 v1 契约；upgrade.md 把 `upgrade.source` 列为"刷新项"（实现为 preserve），方向性错误 | docs/guide/upgrade.md:61,154 等五处 |
| G-05 | HIGH | confirmed | "所有 framework.json 写路径持 config.lock" overclaim：upgrade apply / setup scaffold / config migrate 三条写路径无锁（与 B-09 独立收敛） | upgrade_cmd.py:204; setup_cmd.py:253-259; config_migrate.py:123-156 |
| G-06 | HIGH | confirmed | config.local.json 双真相：`config get/explain` 报告 local 生效，运行时消费方（design_tool/context.mode）只读 framework.json（实测复现） | config.py:148-182 vs :231-235; kg/_dispatch.py:152 |
| G-07 | HIGH | confirmed | 文档称高 schema_version 时"所有读写命令显式 FAIL"，实测 `config get/set` 照常读写（set 成功写盘 v3 文件） | configuration.md:176 vs config_cmd.py:99-179 |
| G-08 | MEDIUM | confirmed | deploy --help 指向已退役的 `.cataforge/.deploy-manifest.json`；未说明无参=部署全部 targets | deploy_cmd.py:86-91,101-111 |
| G-09 | MEDIUM | confirmed | docs/reference/cli.md 未收录 `config` 命令组 / doctor --platform / deploy 缺省语义 | cli.md:9-14,56-71,99-116 |
| G-10 | MEDIUM | confirmed | ADR 四点漂移：manifest_version 2 vs 实现 1；ConfigSnapshot 类型不存在；validate 无未知键报告；framework 集漏 schema_version | adr-multi-platform-config.md:53,60,79,80 |
| G-11 | MEDIUM | confirmed | 仓库 CLAUDE.md「框架版本: 0.16.0」vs 实装 0.17.0；:74 仍称 runtime.platform 决定平台 | CLAUDE.md:7,74 |
| G-12 | MEDIUM | confirmed | framework-walkthrough skill 观测口径仍要求 setup 写 runtime.platform（v2 下会产出假 findings） | SKILL.md:19,55; runtime-flow-map.md:42 |
| G-13 | LOW | confirmed | configuration.md 三处细节漂移（is_async 例子、inline 模板大小写、targets 示例） | configuration.md:68,324,425 |
| G-14 | LOW | confirmed | audience 实现= targets∪deployed∪current，文档只写 targets | deployer.py:308-336 vs platform-adaptation.md:89 |
| G-15 | LOW | confirmed | setup --force-scaffold help 双向欠述（保留面/覆盖面均不准） | setup_cmd.py vs scaffold.py:262-333 |

G 组正向核查 14 项通过（config 5 子命令与文档一致、解析层级、锁参数、状态目录布局、v1→v2 迁移文档、doctor 平台化、hook 身份链、read-first 降级、AGENTS.md 播种、`0.0.0-template` 为文档化占位机制〔非漂移〕、profile↔能力矩阵、ORCHESTRATOR-PROTOCOLS 已更新等）。

### F 组（测试有效性）完整清单

| id | sev | verdict | 一句话 |
|----|-----|---------|--------|
| F-01 | CRITICAL | confirmed | 锁互斥测试软断言（worker 异常仅 warning，恒绿）且掩盖真实 Windows 缺陷：锁文件被并发读时 release unlink 抛 WinError 32 被 suppress 吞掉（2000 次复现 1867 次）→ 锁滞留至 TTL（config 60s / deploy 1800s）；后续 deploy fail-fast 连续被拒最长 30 分钟 |
| F-02 | HIGH | confirmed | deploy lock 只有单元级测试；CLI 接线层（真正的保护位置）零测试——删 CLI 锁包裹全绿 |
| F-03 | HIGH | confirmed | doctor `--platform` 分发/三层作用域解析/未知 id、新增投影漂移检查与 skill 可达性检查（gating）全部零测试 |
| F-04 | HIGH | confirmed | "AGENTS.md 顺序无关"测试用合成 overwrite profile，回避真实 section-merge 路径；不变量当前成立（探针证实）但无守护 |
| F-05 | MEDIUM | confirmed | 24 排列覆盖数=0；仅 3 个两平台对；opencode 在 515 行共存测试中完全缺席 |
| F-06 | MEDIUM | confirmed | migration checks 平台过滤零测试（真实配置已依赖） |
| F-07 | MEDIUM | confirmed | framework.json 写路径无故障注入测试；_config_lock 持锁无测试 |
| F-08 | MEDIUM | confirmed | doctor hygiene 测试测 mock 而非实现（FakeCfg 使 adapter 分支永不执行，只测 fallback） |
| F-09 | MEDIUM | partially | 损坏 per-platform manifest 的空集语义（含 protected 集少算→他平台 prune 误删共有路径的风险）无测试 |
| F-10 | MEDIUM | confirmed | hook 平台识别消费侧（argv 解析、多 target 歧义 RuntimeError）零测试 |
| F-11 | LOW | confirmed | deploy CLI 新行为（无参=全 targets、--platform all、newer-schema 前置拒绝）无测试 |
| F-12 | LOW | confirmed | 弱断言例外清单（migration WARN 只断子串不断退出码等） |

F 组 mutation 静态预测：稳捕获 4（#1 manifest 布局、#3a overwrite 渲染、#4 prune 越权、#7 同值短路）；条件捕获 2（#5 锁本体层捕获/CLI 层 GAP、#10 生成侧捕获/消费侧 GAP）；SUSPECT-GAP 4（#2 迁移平台过滤、#6 非原子写、#8 skill 可达性恒 PASS、#9 codex config.toml 条件误必需）。实测由 M1 在隔离 worktree 进行中。

### A 组（配置与 Schema）完整清单

| id | sev | verdict | 一句话 | 锚点 |
|----|-----|---------|--------|------|
| A-01 | HIGH | confirmed | 锁三种交错破坏互斥：steal 双持锁 / 空 payload 窗口 / release 删偷锁者的锁（与 F-01/B-08/A-09 交叉） | locks.py:51-60,89-105 |
| A-02 | HIGH | confirmed | schema_version=3 时 `config set/get` 不拒绝，照常读写（与 G-07 交叉，实测） | config_cmd.py:124-179 |
| A-03 | HIGH | confirmed | config.local.json 白名单机制不存在；explain 报 local 生效，运行时消费方只读 framework.json（与 G-06 交叉） | config.py:131-146,163-165 |
| A-04 | MEDIUM | confirmed | explain 把 schema default_factory 注入值误标为 `framework` 层（应为 default） | config.py:76-78,166-171 |
| A-05 | MEDIUM | confirmed | `config set default_platform` 不并 targets/不弹 legacy，产出 validate-FAIL 状态（与 D-02/D-03 交叉） | config_cmd.py:166-178 |
| A-06 | MEDIUM | confirmed | `config set` no-change 判定用解析值（含 env/local），高层遮蔽时静默丢写团队文件 | config_cmd.py:154-158 |
| A-07 | MEDIUM | confirmed | migrate 与 scaffold merge 越过 config.lock（与 G-05/B-09 交叉） | config_migrate.py:123-156; scaffold.py:284-333 |
| A-08 | MEDIUM | confirmed | 迁移静默覆盖已声明的 default_platform 且漏报 action 行 | config_migrate.py:139-140,82-83 |
| A-09 | MEDIUM | partially | stale 分支 unlink 失败 `continue` 绕过 deadline → 无限忙等（Windows sharing violation 触发） | locks.py:93-99 |
| A-10 | LOW | confirmed | local 层空 targets 列表不归一化 → 无参 deploy 静默零平台 no-op | config.py:163-170 |
| A-11 | LOW | partially | atomic_write 无 fsync；Windows 目标被读时 os.replace 抛 PermissionError 无重试 | atomic_write.py:49-57 |

A 组正向核查 11 项通过（九类职责分离落位〔唯一同文件共存=framework.json 声明配置+框架 catalog，字段级所有权设计使然〕、deploy/doctor/detection 零写回、local gitignored、框架 catalog 防 config set、五层解析顺序、migration 保数据、`0.0.0-template` 为设计占位、锁基本语义有测试）。

### D 组（向后兼容与迁移）完整清单

| id | sev | verdict | 一句话 | 锚点 |
|----|-----|---------|--------|------|
| D-01 | HIGH | confirmed | config-migrate 备份进 rollback 快照池且字母序恒排第一 → `upgrade rollback` 摧毁整个 `.cataforge/`（直调实测） | config_migrate.py:147-150; scaffold_backup.py:115-156 |
| D-02 | HIGH | confirmed | `config set` 平台选择被随后任一 migrate 静默回退（与 A-05 交叉，实测） | config_cmd.py:166-179; config_migrate.py:82-83 |
| D-03 | MEDIUM | confirmed | runtime.platform + 已声明 targets 并存时迁移产出 default∉targets 的 validate-FAIL 配置 | config_migrate.py:82-85 |
| D-04 | MEDIUM | confirmed | runtime/deployment 非 dict 时 validate/explain/doctor 裸 AttributeError traceback | config_cmd.py:68-69; config.py:174 |
| D-05 | MEDIUM | confirmed | 三迁移入口语义不一致；config migrate 不处理 retired context → migrate 后 doctor 仍 FAIL | bootstrap_cmd.py:241-254; scaffold.py:239-259 |
| D-06 | MEDIUM | confirmed | v2 配置交旧运行时静默当 claude-code 部署，无 schema 检测（静态推演旧代码） | 旧 config.py/deploy_cmd.py |
| D-07 | MEDIUM | partially | 损坏 legacy 记录三入口行为分裂；manifest 缺 platform 键时 owned_paths 未迁移即被删（与 H2-05 交叉） | manifest.py:246-268,153-172 |
| D-08 | LOW | confirmed | migrate action 日志双向失真（漏报/误报 platform 迁移） | config_migrate.py:139-140 |
| D-09 | LOW | confirmed | `schema_version:"3"`（字符串）绕过 newer-schema 拒绝，被强降为 int 2 | config_migrate.py:36,52 |
| D-10 | LOW | confirmed | `upgrade apply --dry-run` 承诺保留 runtime.platform/upgrade.state，真实 apply 恰迁走 | upgrade_cmd.py:130 |
| D-11 | LOW | confirmed | 非 dict upgrade.state 迁移时静默丢弃无 action | config_migrate.py:91-99 |
| D-12 | LOW | partially | 深路径备份目录 mkdir 抛 WinError 206 裸 traceback（失败恢复本身正确） | config_migrate.py:148 |

D 组 12 类 fixture 迁移矩阵：类 1/2/3/8/11/12 全 PASS；类 4 保留但 action 失真；类 5/6/7 迁移 FAIL；类 9 无降级检测；类 10 FAIL-CLEAN（预期拒绝、原文件完好）。备份/幂等/失败恢复三列除深路径 D-12 外全 PASS。

### E1 组（claude-code 适配）完整清单

| id | sev | verdict | 一句话 | 锚点 |
|----|-----|---------|--------|------|
| E1-01 | HIGH | confirmed | `CATAFORGE_PLATFORM=claude-code` 种入 settings.json#env 压制 argv，非 cc 会话守卫失效（并入 SEC-1 第三路径） | profile.yaml:92-96; base.py:58-67 |
| E1-02 | MEDIUM | confirmed | `--rebuild` 整删 settings.json 丢用户 permissions/外来 hook（与 H2-01 交叉） | deployer.py:528-572,634-636 |
| E1-03 | LOW | partially | custom hook argv 注入契约未文档化；README exit-code 语义与官方偏差 | bridge.py:194-197 |
| E1-04 | LOW | confirmed | `CATAFORGE_PLATFORM` 双语义（config override + hook 身份），文档只覆盖其一 | config.py:159-162; base.py:58 |

E1 对 claude-code 本体 13 项正向核查全过（官方文档+沙盒双证：原生路径全套、agent frontmatter 字段、skill 可达性、hook 事件/matcher、多平台无信号硬失败、MCP 格式、instruction 状态模型、doctor scope、降级路径、deploy 锁、测试回归）。与协调者亲测 claude-code smoke 一致——claude-code 单平台面健康。

### E2 组（codex 适配）完整清单

| id | sev | verdict | 一句话 |
|----|-----|---------|--------|
| E2-01 | HIGH | confirmed | UTF-8 下 `matches_capability` 不查 tool_overrides → codex guard_dangerous fail-open（并入 SEC-1） |
| E2-02 | HIGH | confirmed | GBK 下 profile 读取崩溃回退 claude-code map（并入 SEC-1） |
| E2-03 | MEDIUM | confirmed | `.codex/agents/*.toml` body 未转义，含正则/Win 路径/三引号的 agent 生成非法 TOML |
| E2-04 | MEDIUM | partially | CODEX_HOME 是用户状态目录变量，当身份信号双向不可靠、劫持其他平台会话 |
| E2-05 | MEDIUM | disproved | 厂商事实过时："Codex matcher 仅 Bash" 实为可拦 apply_patch/mcp_*（官方文档 2026-07-14）→ lint_format 白降级 |
| E2-06 | MEDIUM | disproved | 厂商事实过时：Codex 已支持 `.agents/skills/` 原生发现 + per-agent model |
| E2-07 | MEDIUM | confirmed | Codex 产物需 trust 才生效，guide/deploy 全链未提 |
| E2-08 | MEDIUM | partially | guard_frozen_docs 取 file_path，Codex apply_patch 载荷是 patch 信封（not-reached） |
| E2-09/10 | LOW | confirmed | matcher_map 死配置；Notification 可映射 PermissionRequest 未映射 |

### E3 组（cursor 适配）完整清单

| id | sev | verdict | 一句话 |
|----|-----|---------|--------|
| E3-01 | CRITICAL | confirmed(产物级) | `.cursor/hooks.json` 缺 `version:1` + 错误嵌套形状 → Cursor 3.x 全部 hook 不加载（并入 SEC-3，第三方 issue 佐证） |
| E3-02 | HIGH | confirmed | GBK locale cursor hook fail-open（并入 SEC-1，本机复现） |
| E3-03 | MEDIUM | partially | `.cursor/agents/<name>/AGENT.md` 嵌套布局非官方文档化（claude-code 已改 flat，cursor 未同步） |
| E3-04 | MEDIUM | confirmed | supported_fields 六字段无一官方文档化，`background` 拼写错（应 is_background） |
| E3-05 | MEDIUM | partially | tier_map 产 `model: opus/sonnet` 短别名非官方文档取值 |
| E3-06 | MEDIUM | confirmed | doctor hook 降级摘要恒用 default_platform，`--platform cursor` 报 claude-code 口径（与 E4-11 交叉） |
| E3-07 | MEDIUM | partially | `.cursor/commands` 已去文档化（Cursor 转向 skills） |
| E3-08…13 | LOW | mixed | matcher_map/get_project_root_env_var 死配置、tools 折叠不去重、mcp stdio type、env 共存顺序无测试、`pre-M5` 里程碑残留 |

### E4 组（opencode 适配）完整清单

| id | sev | verdict | 一句话 |
|----|-----|---------|--------|
| E4-01 | CRITICAL | confirmed(契约级) | plugin 用不存在的 `event.on()` API、不返回 hooks 对象 → 加载即 TypeError，11 hook 零注册（并入 SEC-3） |
| E4-02 | HIGH | confirmed | TS→Python payload 无 `tool→tool_name/args→tool_input` 适配 → 即便 E4-01 修好仍 fail-open |
| E4-03 | HIGH | partially | opencode.json `instructions` 键内用户条目被整键覆盖（clobbering 只修了跨平台一半） |
| E4-04 | HIGH | confirmed | `--rebuild` 整删 opencode.json 丢用户 model/provider/mcp/agent（与 H2-01 交叉） |
| E4-05 | MEDIUM | confirmed | plugin 文件不入 manifest → doctor 察觉不到缺失、永不 prune |
| E4-06 | MEDIUM | confirmed | `custom:` hook 前缀在 opencode 生成非法模块名 → observe 丢失/block 永久阻塞 |
| E4-07 | HIGH | confirmed | GBK opencode hook fail-open（并入 SEC-1，本机复现） |
| E4-08 | MEDIUM | disproved | 厂商事实过时：OpenCode 已原生支持 `.opencode/skills/` + 读 `.claude/skills` |
| E4-09/10 | MEDIUM | mixed | agent frontmatter tools 应为 map+mode、缺 mode；多平台 CLI 层身份仍静默回退 default |
| E4-11…15 | LOW | mixed | doctor scope、`.opencode/rules` 无消费者、plugin hooks 不入 TS、version_tested 严重过时(1.3 vs 1.17) |

### H1 组（24 排列与幂等）完整清单

| id | sev | verdict | 一句话 |
|----|-----|---------|--------|
| H1-01 | HIGH | disproved | 24 排列语义等价性不成立：共享 `.claude/skills` 8 文件按后写平台渲染 CLAUDE.md↔AGENTS.md 乒乓，行为级分歧（坐实 B-01/H2-03） |
| H1-02 | MEDIUM | partially | `deploy --platform all` 首跑非不动点（codex 生成物落入 source_digest 区）；新鲜全量部署后 doctor 假阳性漂移 WARN |
| H1-03 | — | confirmed | 声明验证（非缺陷）：AGENTS.md 按声明 audience 渲染、24 排列字节全同 |

### H2 组（shared ownership）完整清单

| id | sev | verdict | 一句话 |
|----|-----|---------|--------|
| H2-01 | CRITICAL | confirmed | `--rebuild` 摧毁 merge 型 JSON（settings.json/opencode.json）全部用户内容（并入 13.0） |
| H2-02 | CRITICAL | confirmed | 损坏兄弟 manifest → 保护集塌缩 → 跨平台误删共认领产物（并入 13.0） |
| H2-03 | HIGH | confirmed | 共享 skills last-writer-wins（md5 坐实，坐实 B-01/H1-01） |
| H2-04 | MEDIUM | confirmed | doctor 对损坏 manifest 报"empty — nothing to verify"，H2-02 攻击窗口不可见 |
| H2-05 | LOW | confirmed | 损坏 legacy 静默丢弃/透传无告警（与 D-07 交叉） |
| H2-06 | MEDIUM | confirmed | 文档称 skill 目录 junction 往返，实为 copy+render，用户改部署副本被静默覆盖 |
| H2-07 | LOW | confirmed | MCP 配置不入 manifest（此攻击面下反成保护，但换 design_tool 后残留） |

H2 场景 1（删源单平台 redeploy）、2（6 类用户自建文件存活）、4（单平台 rebuild 域限本平台）经实测 PASS。

### H5 组（平台身份串台）完整清单

| id | sev | verdict | 一句话 |
|----|-----|---------|--------|
| H5-01 | CRITICAL | confirmed | GBK 下守卫 fail-open（协调者亲手复现，并入 SEC-1） |
| H5-02 | HIGH | confirmed | 游离 `CATAFORGE_PLATFORM` env 压过 deploy argv，全平台 hook 误判身份 |
| H5-03 | MEDIUM | confirmed | 多目标无 argv 时 block hook 抛 RuntimeError exit 1 = fail-open（非 fail-closed） |
| H5-04 | MEDIUM | confirmed | 多 IDE env 并存按硬编码顺序静默选平台，无告警 |
| H5-05 | LOW | partially | env-sniffer 忽略 CLAUDECODE |
| H5-06 | LOW | confirmed | EVENT-LOG 无平台归属字段 |
| H5-07 | LOW | confirmed | doctor "Default platform" 反映游离 env 而非持久化配置 |

H5 验收达标项：多目标+无信号时 hook `get_platform()` 显式 RuntimeError（不静默取默认）；deploy 产物均带显式 `--cataforge-platform` argv；单一 target 无信号取该平台合理。**但** SEC-1 三路径 + H5-02/03 表明"身份不明确时显式失败"的达标被 env/编码/argv-缺失多个旁路绕过。

### H6 组（AGENTS/CLAUDE 状态攻击）完整清单

验收目标 7「只有一个状态 SSOT」= **部分成立**。PASS 面：活状态不被 redeploy 覆盖（section-merge runtime-preserve）、4 组交替部署顺序无关字节全等、用户自定义章节保留、无全局"最后部署平台"槽、framework.json 部署前后字节不变、主文件缺失重建不反灌投影（权威方向未倒置）、fresh-seed 完整。FAIL 面：

| id | sev | verdict | 一句话 |
|----|-----|---------|--------|
| H6-01 | HIGH | confirmed | `§执行环境` 段漂移完全不可检测（doctor 投影检查只比对 `^## 项目状态`），次平台读陈旧测试/lint 口径且"in sync"假信心 |
| H6-02 | MEDIUM | partially | 双写副本无自动收敛；codex 上 orchestrator 写 AGENTS.md 使投影比"SSOT"新，WARN 方向可能倒置 |
| H6-03 | MEDIUM | confirmed | 截断投影 redeploy 只恢复框架段，§项目状态/用户章节永久残缺（劣于整删——整删反而 fresh-seed 全恢复） |
| H6-04 | MEDIUM | confirmed | 两文件全删后 redeploy 双双占位符重生，doctor 报"in sync"假绿、活状态清零无信号 |
| H6-05 | MEDIUM | confirmed | audience ratchet：deploy record 只增不减，误 `deploy cursor` 后 `运行时:` 永久含 cursor（坐实 B-04/G-14） |
| H6-06 | MEDIUM | confirmed | `deploy --platform all`=ALL_PLATFORMS 而 doctor all=targets∪deployed，语义不一致（坐实 B-04/F-11） |
| H6-07/08/09 | LOW | confirmed | 三处 profile 注释称 `运行时:` 为当前平台实为 audience 集合；WARN 补救文案不可执行（redeploy 不收敛）；状态模型关键路径零测试 |

### M1 组（mutation 敏感度）

M1 组 7 条 HIGH test-gap（M1-01…M1-07）完整清单见 §11。H3 组见 §10、H8 组见 §9。

## 14. not-reached 路径

- **Cursor / Codex / OpenCode 真实 IDE 会话内 hook 触发**：本机无 cursor-agent/codex/opencode CLI。SEC-3（cursor hooks.json version 缺失、opencode plugin API 不符）为**产物 vs 厂商文档 schema 对照 confirmed** + 第三方 issue 佐证，但未在真实 IDE 会话观测 hook 是否真的不加载。
- **Codex apply_patch hook 载荷形状**（E2-08）：guard_frozen_docs 能否取到 file_path，官方未文档化载荷 schema，无法本机终证。
- **cursor/codex/opencode agent frontmatter/model 别名运行时容忍度**（E3-03/04/05、E4-09）：schema 不符已确证，IDE 实际忽略/报错行为 not-reached。
- **锁窗口(a) 双持在 POSIX 的真实命中**（H8-05）：Windows 被 OS 挡住，POSIX 逻辑可达但未在 POSIX 机器实测。
- 说明：SEC-1（守卫 fail-open）**已在真实 CLI 层由协调者亲手复现**（cursor 沙盒 cp936 下 EXIT=0），非 not-reached；仅"真实 IDE 会话内触发该 hook"这一层未验证，但 hook 进程行为是纯 CLI 逻辑，复现证据链完整。

## 15. 剩余风险

1. **安全网静默失效面广**：SEC-1 三条独立触发路径（GBK 编码回落 / matches_capability 不查 overrides / env 压制 argv）+ SEC-3 两平台原生格式断裂，共同使"cursor/codex/opencode 上 guard hook native"在真实环境不成立，且 doctor 报 native 制造虚假保障。框架中文定位 + 维护者本机 cp936 使 GBK 路径为常态而非边角。
2. **锁在崩溃恢复期不可靠**：H8-06/07 确定性双持/三持仅在存在 stale 锁 + 并发回收时触发（正常路径 config.lock 正确）。无人值守循环的 kill-重拉正是批量制造 stale 锁的场景（用户画像强调无人值守），触发面高于一般项目。
3. **`--rebuild` 是数据丢失陷阱**：文档定位为"从损坏部署恢复"的推荐命令，却摧毁 settings.json/opencode.json 全部用户配置——用户在最需恢复时踩雷。
4. **doctor 作为门禁的可信度**：3 类 false PASS（manifest 损坏 / MCP 不记账 / schema 不兼容）使 CI 以 doctor 为部署健康门时形同虚设。
5. **测试无法守护重构不变量**：7/12 关键 mutation 逃逸 + 锁软断言，重构引入的回归大概率静默通过绿灯。
6. **文档系统性 v1 残留**：generator/framework-update/PROJECT-STATE 模板会主动把项目打回 v1 布局或产出过不了验证的配置，且下次 deploy 回滚本 PR 改对的 CLAUDE.md。

## 16. 最终 verdict

**needs_revision。**

判据（任一即触发，本轮多项同时成立）：

- **CRITICAL 存在**：SEC-1（守卫 fail-open，亲手复现）、SEC-2/F-01（锁软断言掩盖 Windows release 失效）、SEC-3（cursor/opencode 原生 hook 格式断裂）、H2-01（`--rebuild` 摧毁用户配置）、H2-02（损坏 manifest 跨平台误删）。
- **24 排列语义不等价**（H1-01 实测）。
- **`deploy --platform all` 非幂等**（首跑非不动点 H1-02）。
- **单平台 redeploy 影响其他平台**（B-01/H1-01/H2-03 共享 skills last-writer-wins）。
- **config migration 可丢数据**（D-01 rollback 摧毁 .cataforge/）。
- **并发写在崩溃恢复期 lost update**（H8-06/07 锁双持/三持）。
- **doctor 产生 false PASS**（H3-01/02/03/04）。
- **平台身份可静默串台**（SEC-1 = H5-01/E1-01/E2-01 三路径）。
- **用户自定义文件可能被误删**（H2-01/B-05）。
- **关键 mutation 未被测试捕获**（M1 7/12 逃逸）。
- **必需测试未全绿**：全量 pytest 1 failed（R-COORD-1，v1 断言的升级 e2e）；run_local FAIL（R-COORD-2，Windows mypy strict，#485 遗留）。

**须澄清的正向面（避免整改过度）**：多平台**文件系统隔离与状态职责模型的主体是健康的**——per-platform manifest/state 布局、锁的正常路径、deploy 事务的 manifest→state 次序（中断无数据丢失、可自愈）、AGENTS.md 按声明 audience 顺序无关渲染、用户文件在普通 deploy 下存活、config.lock 正常并发无 lost update、claude-code 单平台面（真实 smoke 通过）、v1→v2 主迁移路径幂等——这些经多代理正向核查确认。缺陷集中在**四个可预测的断层**：(a) hook 平台身份/编码/格式的安全面，(b) 锁的 stale/TTL 崩溃恢复语义，(c) `--rebuild` 与损坏-manifest 的破坏性边界，(d) 测试与文档未追上实现。整改应聚焦这四处，而非重做状态模型。

## 17. 静态质量门结果

| 检查 | 结果 | 备注 |
|------|------|------|
| full pytest（`-n auto --dist loadscope`，含 slow） | **FAIL**（1 failed / 3273 passed / 6 skipped，510s） | R-COORD-1 陈旧 e2e |
| run_local.py（ruff、format、mypy strict、全部 check_*、uv lock --check） | **FAIL**（仅 mypy strict 1 项） | R-COORD-2，Windows 平台性；其余 28 项含 ruff/lint/文档守卫/lockfile 全 PASS |
| pytest `-m "not slow"` 等价面 | PASS（全量中除 slow e2e 外均绿） | 与 PR 自述一致 |

## 18. 整改计划（needs_revision — 按依赖排序，等用户授权后另起独立工作流）

本轮默认不修源码。若授权整改，建议按下列依赖顺序，每项附验收测试；整改完成后须从**独立审查基线重新全审**，不得只重跑曾失败的测试。

**批次 0 · 先修红灯（无依赖，解锁"必需测试全绿"门槛）**
- R-COORD-1：修 `test_upgrade_apply_preserves_user_mods_and_runtime_platform` 断言为 v2 布局（`deployment.default_platform`）。验收：全量 pytest 绿。
- R-COORD-2：`unattended.py:206` 用 `sys.platform` 守卫替代 `os.name`（mypy 可收窄）或加平台条件 type-ignore。验收：Windows `run_local.py` 绿。

**批次 1 · 安全面（最高优先，SEC-1/SEC-3，彼此独立可并行）**
- SEC-1：`registry.py:72`/`base.py:153` 补 `encoding="utf-8"`；hook 脚本入口统一 `ensure_utf8()`；`matches_capability` 同时消费 `hooks.tool_overrides`；`_load_tool_map` 对"profile 存在但解析失败"fail-closed/告警而非静默退 claude-code；评估 argv 优先级提到 env 之上（或不再把 CATAFORGE_PLATFORM 种入 settings.json#env）。验收：cursor/codex/opencode 身份 + 各自 shell 工具名 + `rm -rf`/`git push --force` → exit 2；GBK 与 UTF-8 两 locale 均拦截；M1-07 歧义熔断单测。
- SEC-3：cursor 输出 `version:1` + 扁平 hook entry；opencode plugin 改为返回 hooks 对象（tool 事件具名键 + session 事件通用 event 键）+ TS→Python payload 适配（tool→tool_name/args→tool_input）。验收：产物 vs 厂商 schema 快照测试；条件允许时真实 IDE smoke。

**批次 2 · 破坏性边界（H2-01/H2-02/B-05/D-01，独立可并行）**
- H2-01/E1-02/E4-04：`--rebuild` 的 protect 集扩展为所有 merge 型目标（settings.json/opencode.json/hooks config/mcp json），或对这些文件键级摘除而非整删。验收：rebuild 后用户 permissions/model/自建 hook 存活的对照测试。
- H2-02/H3-01/H8-01：`_owned_paths_from_file` 区分"不存在"（合法空集）与"存在但损坏"（哨兵/抛出）；doctor 对损坏 manifest 与"产物在盘但无 manifest"报 FAIL/WARN。验收：损坏 cursor manifest 后 cc redeploy 不误删共享 skill；doctor 察觉损坏/半部署。
- B-05：`.claude/rules/` 改 per-file manifest prune（对齐 commands）。验收：`.claude/rules/` 用户文件普通 deploy 后存活。
- D-01：config-migrate 备份移出 rollback 快照池（独立目录或 `list_backups` 按快照命名过滤）。验收：`.backups/` 含 config-migrate 时 `upgrade rollback` 不摧毁 `.cataforge/`。

**批次 3 · 共享产物顺序无关（B-01/H1-01，依赖 batch2 的 manifest 语义清晰）**
- 共享 `.claude/skills` 复用 instructions 的 audience 中性渲染（`{INSTRUCTION_FILE}`→平台无关短语或 default_platform）。验收：24 排列共享 skills 树字节全同；coexistence fixture 加含 token 的 skill（M1-02/F-04）。

**批次 4 · 锁并发正确性（A-01/H8-06/07/03，独立）**
- steal 改原子 compare-and-delete（rename 占位或带 nonce 的 CAS）；finally 释放前校验锁归属；`_is_stale` 增世代/nonce；同机 PID liveness 快路回收；stale unlink 失败不绕过 deadline（A-09）；LockHeldError 文案区分"进行中"与"疑似崩溃残留"。验收：`lock_stress.py` window_b/c + steal 压测双持率归零。
- H8-04/A-07/G-05：upgrade apply / setup scaffold / config migrate 落盘段包 config.lock。

**批次 5 · doctor 门禁与配置一致性（H3-02/03/04、A-02/03）**
- MCP 产物入 manifest（H3-02/B-10/E4-05）；doctor 增 schema 兼容节复用 `config validate`（H3-03/04）；`config get/set` 入口统一 `reject_newer_schema`（A-02/G-07）；local 层按显式白名单过滤 + explain 对白名单外跳过 local（A-03/G-06）；`config set default_platform` 路由到 `set_default_platform`（A-05/D-02）。

**批次 6 · 状态可检测性 + audience 一致（H6-01/05/06、B-04）**
- doctor 投影检查覆盖 section_policy.runtime 全集（含 §执行环境，H6-01）；`deploy --platform all` 收敛为 targets∪deployed（与 doctor 一致，H6-06/B-04）；提供 `deploy --retire <platform>` 回收 audience ratchet（H6-05/B-04）。

**批次 7 · 测试与文档（M1 7 条 + F 12 条 + G 15 条，可与上批次并行补测）**
- 每个 gating doctor check 配 FAIL 路径单测 + 负向断言（M1-01/05/06）；deploy CLI 锁接线测试（M1-03）；`_write_raw` 原子性接缝测试（M1-04）；共享 AGENTS.md section-merge 顺序测试 + 修正退化单元用例（M1-02）；文档 15 条漂移逐条订正（G 组，重点 generator 验证器 G-03、framework-update SKILL G-02、PROJECT-STATE 模板 G-01、三条 overclaim G-05/06/07）。

**非阻塞 backlog（LOW，不进整改主线）**：R-COORD-3（MAX_PATH 诊断）、E2-09/E3-08 死配置清理、pre-M5 里程碑残留（E3-13）、EVENT-LOG 平台字段（H5-06）、各 profile version_tested 刷新。
