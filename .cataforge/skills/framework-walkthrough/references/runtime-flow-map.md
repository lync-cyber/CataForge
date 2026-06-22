# 完整运行流程路径图

本文件是 framework-walkthrough 走查覆盖面的单一事实源：枚举框架运行流程的全部已知路径，按五类组织（初始化 / 核心执行链路 / 分支 / 异常 / 终止清理）。走查须逐路径处置，并在报告的「路径覆盖账本」里给出每条路径的归属，确保「没跑到」不被读作「没问题」。

路径定义的权威协议是 `ORCHESTRATOR-PROTOCOLS.md` 与 `framework.json#/workflow`；本表是**走查视角的只读投影**——只标「这条路径在走查里怎么处置、看什么」，不复制协议正文。协议变更时以协议为准、回头校准本表。

## 目录

- §1 处置与图例
- §2 初始化路径（Bootstrap）
- §3 核心执行链路（happy path 主干）
- §4 分支路径
- §5 异常处理路径
- §6 终止 / 清理路径
- §7 覆盖账本字段

## 1. 处置与图例

每条路径标一个**处置**，决定走查怎么对待它：

| 处置 | 含义 | 触发方式 |
|------|------|---------|
| `D` driven | happy path 主干，缺省 `--depth smoke` 即确定性驱动 | 跑示例项目自然经过 |
| `P` probed | 分支/异常路径，`--depth full` 时按探针清单有界触发；`smoke` 下不触发 | 对示例做最小扰动（见 example-project §探针扰动） |
| `O` observed | 不可确定性强制（依赖真实失败/截断），只能机会观察 | 自然出现即记录，否则账本标 not-reached |

探针（`P`）是**一次有界观察**，触发一条路径就够、不展开成完整 SDLC。机会观察（`O`）路径在 `smoke` 与 `full` 下都可能为 not-reached，须在账本写明原因（如「单轮未发生子代理崩溃」），不可凭空标 driven。

## 2. 初始化路径（Bootstrap）

入口：`ORCHESTRATOR-PROTOCOLS §Project Bootstrap`（{INSTRUCTION_FILE} 缺失时）。走查在沙盒 cwd 内主线程扮演 orchestrator 逐步推进。

| id | 路径 / 步骤 | 期望行为 | 处置 | 观察重点 |
|----|------------|---------|------|---------|
| I-1 | 收集项目信息 + 选执行模式 | AskUserQuestion 单独提问，写入 §项目信息.执行模式 | D | 提问是否选择题优先、是否一次问全 |
| I-2 | 创建目录结构 | 按模式建 `docs/{...}`（standard/agile-lite vs agile-prototype 不同集合） | D | 目录集合与模式是否匹配 |
| I-3 | 写 `.gitattributes` | 项目根缺失时写跨平台行尾最小集；已存在只读判断不覆盖 | D | 是否误覆盖用户自定义 |
| I-4 | 创建 {INSTRUCTION_FILE} | 按 Update Template 生成，文档状态全 `未开始`，当前阶段按模式（requirements/planning/brief） | D | 初始阶段与模式是否一致 |
| I-5 | 写框架版本 | 取 `pyproject.toml [project].version`；缺失标「未追踪」 | D | 版本是否为占位符 `0.0.0-template` |
| I-6 | 选平台 + 部署 | `cataforge setup --platform <p>`（写 `runtime.platform` 并 deploy；命令形态见 walkthrough-protocol §1.1） | D | 部署产物是否对应平台、`doctor` 是否通过 |
| I-7 | env-block + permissions | `cataforge setup env-block` 注入 §执行环境；`cataforge setup permissions` 收紧白名单 | D | env-block exit 2（未检测技术栈）是否被正确兜底 |
| I-8 | 文档索引 + 知识图谱 | `cataforge context ensure-store`（幂等；按 context.mode 水合 store，`markdown` 时跳过）+ `cataforge context index`（空索引） | D | store 水合跳过是否显式提示、context mode 分流是否正常 |
| I-9 | 进入初始阶段 | 按 Mode Routing 激活初始角色 | D | `cataforge phase status` 是否非占位符、有 `phase_start` 事件 |

## 3. 核心执行链路（happy path 主干）

阶段序列与每阶段 `execution_host` 取自 `framework.json#/workflow.modes.<mode>.phases[]`；门禁逻辑取自 `ORCHESTRATOR-PROTOCOLS`。

| id | 路径 | 期望行为 | 处置 | 观察重点 |
|----|------|---------|------|---------|
| C-1 | Mode Routing | 按 §项目信息.执行模式 路由出本模式的阶段序列与文档类型 | D | 路由结果与 COMMON-RULES §执行模式矩阵一致 |
| C-2 | execution_host 分派 | `inline` 阶段主线程承载（交互角色）；`subagent` 阶段派隔离子代理 | D | interactive=true 的阶段是否走 inline、子代理是否真被派发而非空转 |
| C-3 | 文档产出 + 定稿 | 角色经 context authoring 产文档、`context finalize` 落 status=draft | D | 产物路径/命名/front matter 合规、是否注册索引 |
| C-4 | doc-review 门禁 | Layer 1 强制；按 `DOC_REVIEW_L2_SKIP_*` 判断 Layer 2 短路 | D | 该审却没审 / 该短路却全跑；Layer 1 退出码 |
| C-5 | Phase Transition | 8 步状态持久化 + 一致性门（见 §3.1） | D | 8 步是否全做、顺序是否在派发下一阶段前完成 |
| C-6 | TDD development | 按 tdd-engine 档位执行 RED/GREEN/REFACTOR（standard）或 light 合并或 prototype-inline | D | 档位选择是否符合 `TDD_*` 常量、子代理隔离是否成立 |
| C-7 | code-review 门禁 | GREEN 后跑 code-review；按 `CODE_REVIEW_L2_SKIP_*` 判断短路 | D | 短路判定、security/error-handling 关键字是否抑制短路 |
| C-8 | phase status 硬校验 | 每跨完一阶段跑 `cataforge phase status`，退出非 0 即该阶段 blocked | D | 委派子代理「只部署不驱动」会在此暴露 |

### 3.1 Phase Transition Protocol 的子路径（C-5 展开）

`ORCHESTRATOR-PROTOCOLS §Phase Transition Protocol` 的一致性门是走查最易漏看的过程信号，逐子步观察：

| id | 子步 | 期望行为 | 观察重点 |
|----|------|---------|---------|
| C-5a | 文档头 + {INSTRUCTION_FILE} 状态更新 | status: draft→approved，阶段字段同步 | 文档头与 {INSTRUCTION_FILE} 是否一致 |
| C-5b | `cataforge context validate`（依赖新鲜度） | 无 stale_deps 通过；有则给分支选项 | stale_deps 是否被检出（见 §4 B-8） |
| C-5c | `cataforge context reconcile`（一致性守门） | 无漂移通过；图后端未启用为 no-op WARN | 漂移是否被捕获、remediation 路由（见 §4 B-9） |
| C-5d | `cataforge skill run doc-consistency`（Phase 2+） | exit 0/2 继续，exit 1 给分支选项 | ≥2 文档 approved 时是否真触发（见 §4 B-10） |
| C-5e | EVENT BATCH | 单次 stdin 一次性写 4 条事件（phase_end→review_verdict→state_change→phase_start） | 是否原子写入、有无半截状态 |
| C-5f | `cataforge claude-md check`（hygiene 门） | exit 0 通过；exit 1 阻塞转换给 compact 选项 | 阈值越界是否真阻塞（见 §4 B-11） |
| C-5g | 进入下一阶段 | 按 execution_host 分派 | 是否在 5a–5f 全部完成后才分派 |

## 4. 分支路径

非异常的多路分叉，多数由用户决策或项目配置驱动。`--depth full` 时按探针清单触发可达者。

| id | 路径 | 触发 | 期望行为 | 处置 | 观察重点 |
|----|------|------|---------|------|---------|
| B-1 | 模式三分叉 | 走查 `--mode` | standard / agile-lite / agile-prototype 路由出不同阶段集合 | P | 跨模式重跑时阶段集合/文档产出差异是否符合矩阵 |
| B-2 | Manual Review Checkpoint | 阶段转换命中检查点 | 按 MANUAL_REVIEW_CHECKPOINTS 暂停确认；pre_deploy demo gate | D | 命中判定是否正确、沙盒代答是否记为交互负担观察点 |
| B-3 | Approved-with-Notes | reviewer 出 approved_with_notes | 4 选项（接受/修复选中/暂停/全量 inline-fix） | P | 选项 4 的展示条件（≥8 LOW / ≤50 行 / 非冻结类）是否被正确门控 |
| B-4 | Sprint Review 短路 | Sprint 任务数 ≤ `SPRINT_REVIEW_MICRO_TASK_COUNT` 且全 approved | 跳过 sprint-review，直接视为 approved | P | 短路条件判定、跳过事件是否记录 |
| B-5 | Parallel Task Dispatch | 同 sprint_group ≥2 无依赖任务 | 单消息批量调度（上限 3）；共享模块批量化 C2；validation 任务走 AskUserQuestion 不进 TDD | P | 是否真并行、deliverables 路径冲突是否降级串行 |
| B-6 | Change Request | 走查中途提交变更描述 | change-guard 分析 → proceed / amend_then_proceed / cascade_amendment | P | action 路由是否正确、cascade 是否从最上游逐级 |
| B-7 | 模式回退提示 | lite 文档超阈值 / agile-lite 任务数 >25 | AskUserQuestion 提示升档；不自动改写模式字段 | P | 是否检出超阈值信号、是否误自动改写 |
| B-8 | stale_deps 分支 | C-5b 检出过期依赖 | cascade_amendment / 降级 WARN / 暂停 三选项 | O | 上游变更后下游是否真被标 stale |
| B-9 | reconcile drift 分支 | C-5c 检出图谱漂移 | remediation：export(finalize) / ingest(回灌) / manual | O | drift 方向判定与 remediation 是否匹配 |
| B-10 | doc-consistency 分支 | C-5d exit 1 | cascade_amendment / 降级 WARN / 暂停 | O | 跨文档矛盾是否被检出 |
| B-11 | claude-md hygiene 分支 | C-5f exit 1 | 自动 compact / 手动处理，阻塞转换 | O | 阈值越界是否真阻塞而非 WARN 放行 |
| B-12 | skippable 阶段 N/A | §阶段配置 标 ui_design/testing/deployment N/A | 路由跳过该阶段，不产对应文档 | P | N/A 阶段是否被正确跳过、不误判为缺产物 |

## 5. 异常处理路径

恢复型协议，多数依赖真实失败信号，`O` 居多。`needs_input` / `needs_revision` 可由探针确定性触发故为 `P`。

| id | 路径 | 触发 | 期望行为 | 处置 | 观察重点 |
|----|------|------|---------|------|---------|
| E-1 | Interrupt-Resume | 子代理返回 needs_input | AskUserQuestion 代问 → continuation 重启；每阶段 2 轮上限，第 3 轮请人工 | P | 轮次上限是否生效、是否重复提问 |
| E-2 | Revision | reviewer 返回 needs_revision | 调原 Agent task_type=revision，增量审查；needs_revision(N) N≥2 请人工 | P | 增量审查是否只审 diff + 上轮 CRITICAL/HIGH 维度、计数是否累计 |
| E-3 | Rolled-back Recovery | REFACTOR 子代理 rolled-back | 用 GREEN 产出，code-review 标 MEDIUM，不重试 | O | 回滚是否静默、是否误重试 |
| E-4 | TDD Blocked Recovery | TDD 子代理 blocked + questions | AskUserQuestion → continuation；每阶段 1 轮上限 | O | 第 2 次 blocked 是否请人工 |
| E-5 | Agent Crash Recovery | 子代理无 `<agent-result>` 且兜底无法推断 | git status 查部分产出 → 继续/重试/跳过；每阶段 1 次上限 | O | 崩溃是否记 CORRECTIONS-LOG |
| E-6 | Sub-Agent Truncation Recovery | 截断征兆 + 有未提交 artifact | ≥70% 主线程接管收尾；<70% blocked；每任务 1 次 | O | 完成度评估是否跑测试/lint、接管 vs blocked 判定 |
| E-7 | cascade_amendment 中断 | cascade 中某文档 needs_revision ≥3 | 暂停下游，上游保 draft，给继续/回滚选项 | O | 是否误标 approved、回滚是否干净 |
| E-8 | phase status → blocked | `cataforge phase status` 退出非 0 | 该阶段判 blocked，记 framework/blocked finding 并停推进 | D | 硬门槛是否真阻塞（区分「已部署」与「真被驱动」） |
| E-9 | Layer 1 FAIL | 审查 Layer 1 返回 2/127 / no executable | 判 FAIL，先 `cataforge doctor`；运行时异常/超时降级进 Layer 2 | O | 四态返回是否被正确区分 |
| E-10 | 单轮预算保护（走查自身） | 某路径反复 needs_revision/blocked 超两轮 | 停止驱动，把卡点记 framework/blocked finding 转出报告 | D | 走查不死磕示例完成度，价值在暴露了什么 |

## 6. 终止 / 清理路径

| id | 路径 | 期望行为 | 处置 | 观察重点 |
|----|------|---------|------|---------|
| T-1 | 收敛判定 | development 全部 approved + 评审通过；任务数 ≤ micro 阈值跳 sprint-review；deployment 标 N/A | D | 收敛条件是否齐备、有无遗留 needs_revision |
| T-2 | 项目完成态 | {INSTRUCTION_FILE} 当前阶段可达 completed（或走查在 development 收口即停） | D | 状态与产物是否一致 |
| T-3 | 证据收集 | 汇总产物清单 + EVENT-LOG 关键事件 + 错误原始输出 | D | EVENT-LOG 与实际推进是否一致、有无漏写事件 |
| T-4 | 走查报告 | 产 FRAMEWORK-REVIEW-walkthrough（两类 findings + 覆盖账本 + 三态判定） | D | 账本是否覆盖本表全部路径 |
| T-5 | 沙盒清理 | gitignored 沙盒整体可删；保留证据时报告内以路径+摘要引用 | D | 是否误删/误入仓 |

## 7. 覆盖账本字段

报告的「路径覆盖账本」对 §2–§6 每条路径给一行：

| 字段 | 取值 | 说明 |
|------|------|------|
| `path_id` | I-* / C-* / B-* / E-* / T-* | 对应本表 id |
| `disposition` | driven / probed / observed / not-reached | 实际处置（not-reached 须填原因） |
| `result` | ok / finding / n-a | ok=如期；finding=见报告对应编号；n-a=本模式/配置不适用 |
| `evidence` | 阶段 + 命令 + 产物路径 / `file:line` | observation-rubric §3 的证据要求 |

账本让覆盖面可审计：哪条 happy path 真跑了、哪条分支被探针触发、哪条异常路径因单轮未发生真实失败而 not-reached，一目了然，杜绝「跑了 happy path 就声称全流程正常」。
