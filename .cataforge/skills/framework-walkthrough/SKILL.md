---
name: framework-walkthrough
description: "项目走查 — 在隔离沙盒中以指定执行模式把一个小型示例项目跑通整条 SDLC 工作流（初始化→核心执行链路→分支→异常→终止清理），逐路径观察各阶段/门禁/降级/恢复的真实行为，产出『框架本身 + 走查流程本身』两类改进建议。与 framework-review 形成动静对偶：后者静态审元资产，本 skill 动态端到端自测。当用户想验证一次框架部署是否真能跑通、为非 Claude-Code 平台做行为级冒烟、或自测 workflow-framework-generator 生成的框架时使用。"
argument-hint: "[--mode <agile-prototype|agile-lite|standard>] [--platform <claude-code|cursor|codex|opencode>] [--example <example_id>] [--depth <smoke|full>]"
suggested-tools: file_read, file_write, file_edit, file_glob, file_grep, shell_exec, agent_dispatch, user_question
depends: [start-orchestrator]
disable-model-invocation: false
user-invocable: true
---

# 项目走查 (framework-walkthrough)

## 能力边界
- 能做: 在隔离沙盒里部署目标平台资产并以指定执行模式驱动一个小型示例项目跑通端到端工作流；按 [`references/runtime-flow-map.md`](references/runtime-flow-map.md) 逐路径覆盖完整运行流程的五类路径（初始化 / 核心执行链路 / 分支 / 异常 / 终止清理），在每个阶段/门禁/降级/恢复处采集「观察点」；产出框架本身与走查流程本身两类改进建议报告 + 路径覆盖账本；跨四端可移植（用能力标识符与 `cataforge` CLI 而非平台原生名）
- 不做: 修改被走查的真实项目资产或 `.cataforge/` 本体（仅在沙盒里跑、仅向 `docs/reviews/framework/` 产报告）；替代 framework-review 的静态元资产审查（互补，发现面不同）；替代 platform-audit 的 IDE 厂商对账；进入业务开发主循环（按需触发）

## 输入规范
- 可选 `--mode`: 执行模式，缺省 `agile-lite`（最能在单轮内触达 初始化→核心链路→终止 主干）；语义见 COMMON-RULES §执行模式矩阵
- 可选 `--platform`: 目标平台，缺省取 `framework.json#/runtime.platform`
- 可选 `--example`: 示例目标 id，缺省内置 `temperature-converter`（见 [`references/example-project.md`](references/example-project.md)）；自带目标须小到单轮收敛
- 可选 `--depth`: 覆盖深度，缺省 `smoke`。`smoke` 只确定性驱动 happy path 主干、对分支/异常路径仅机会观察；`full` 额外按路径图探针清单逐个触发可达的分支/异常路径
- 被走查的框架资产: 项目根 `.cataforge/`（必读）
- 完整运行流程路径图: [`references/runtime-flow-map.md`](references/runtime-flow-map.md)；详细执行协议: [`references/walkthrough-protocol.md`](references/walkthrough-protocol.md)；观察与归类口径: [`references/observation-rubric.md`](references/observation-rubric.md)

## 输出规范
- 走查改进报告: `docs/reviews/framework/FRAMEWORK-REVIEW-walkthrough-{YYYYMMDD}-r{N}.md`，front matter `doc_type: framework-review`（编号与字段按 COMMON-RULES §审查报告规范）
- 报告含: 两类 findings（`framework` 框架本身缺陷/摩擦 + `process` 走查流程本身可改进项，各按 COMMON-RULES §统一问题分类体系 / §归因分类 / §问题格式 标注）+ 路径覆盖账本（路径图每条路径标 driven / probed / observed / not-reached(原因)，字段见 runtime-flow-map §7）
- 沙盒运行产物: 留在 gitignored 沙盒目录供复核，不入仓；报告以「产物清单 + 关键证据」形式引用

## Anti-Patterns
- 禁止: 在宿主真实项目根直接驱动走查 — 会覆写真实 `docs/` / `PROJECT-STATE` / `EVENT-LOG` / KG store；应在 gitignored 沙盒目录内 `cataforge setup` 出独立项目后再起流程
- 禁止: 选过大的示例目标导致一轮收敛不了 — 如「做一个电商平台」；应小到单轮闭环（如温度转换 CLI），把验证重心放在工作流主干而非业务复杂度
- 禁止: 把改进建议写回被走查的 `.cataforge/` 资产本体 — 会污染单一事实来源；只产报告到 `docs/reviews/framework/`，框架修复交由后续 framework-review / 维护流程闭环
- 禁止: 只跑通 happy path 就把报告写成「全流程正常」 — 分支/异常/恢复路径未触发就是 not-reached，须在覆盖账本里如实标原因，不可让「没跑到」读作「没问题」
- 禁止: 只看「最终有没有产出文档」就结案 — 走查价值在过程中的门禁触发/降级是否静默/CLI 与 skill 是否报错等信号，事后无法补采；须按观察口径逐路径记录
- 避免: 把本 skill 当 framework-review 的替代 — 静态审元资产用 framework-review，端到端跑用本 skill

## 执行步骤
本流程把「框架完整运行流程」拆为五类路径驱动；每条路径的触发条件、期望行为、走查处置（driven/probed/observed）见 [`references/runtime-flow-map.md`](references/runtime-flow-map.md)。

### Step 1: 准备隔离沙盒（初始化前置）
1. 在 gitignored 沙盒目录（缺省 `walkthrough-sandbox/<run-id>/`，`<run-id>` = `<platform>-<mode>-<时间戳>`，时间戳取 `Get-Date -Format yyyyMMdd-HHmmss` / `date +%Y%m%d-%H%M%S`，保证并发/重跑各占独立目录）新建空项目目录；目标目录非空时另起新 run-id 或先 `--clean` 清空，非空目录直接复用会让两次走查互相写入对方产物、归因困难
2. 在沙盒 cwd 内部署目标平台资产（命令形态见 walkthrough-protocol §1.1）；确认 `framework.json#/version` 非占位符 `0.0.0-template`、`cataforge doctor` 通过
3. 校验沙盒与宿主隔离：沙盒有独立的 `.cataforge/` 与空 `docs/`，后续所有写入均在沙盒 cwd 内

### Step 2: 选定示例目标与执行模式
1. 缺省载入 `references/example-project.md` 的 `temperature-converter` 目标、功能项、架构契约与验收标准；自带目标按该文件「示例目标合格性清单」自检
2. 缺省 `agile-lite`：单轮收敛且触达主干；`agile-prototype` 更快更浅、`standard` 最全最重（差异见 COMMON-RULES §执行模式矩阵）
3. `--depth full` 时，从 example-project §探针扰动 取本轮要触发的分支/异常路径清单

### Step 3: 驱动初始化路径（Bootstrap → 路径图 §2）
1. 在沙盒 cwd 按 start-orchestrator 角色假设起流程：主线程扮演 orchestrator，按 `ORCHESTRATOR-PROTOCOLS §Project Bootstrap` 逐步推进
2. 逐步观察 Bootstrap 各产物落地（路径图 I-1~I-9：目录结构 / .gitattributes / {INSTRUCTION_FILE} 初版 / 框架版本 / runtime.platform / env-block / permissions / kg store 水合 / context index），口径见 observation-rubric §1
3. Bootstrap 完成后跑 `cataforge phase status`，确认进入初始阶段且非占位符

### Step 4: 驱动核心链路 + 分支/异常路径（路径图 §3–§5）
1. 逐阶段推进至 development 完成且评审通过；每个 Phase Transition 逐子步观察一致性门（路径图 C-5a~C-5g：validate / reconcile / doc-consistency / claude-md check）与 execution_host 分派（inline vs subagent）
2. happy path 上自然触发的门禁/降级即时记录；`--depth full` 时按 walkthrough-protocol §6 探针程序逐个触发可达的分支路径（B-*）与可探针异常路径（E-1/E-2），每个探针是一次有界观察、不展开成完整 SDLC
3. 机会观察类异常路径（路径图标 `O`：crash / truncation / rolled-back 等）若自然出现即记录，否则账本标 not-reached
4. 单轮预算保护：某路径反复 needs_revision / blocked 超两轮仍不收敛，停止驱动并把卡点记为 finding（见 walkthrough-protocol §4）

### Step 5: 驱动终止/清理路径并收集证据（路径图 §6）
1. 确认收敛条件成立（development 全部 approved + 评审通过；任务数 ≤ `SPRINT_REVIEW_MICRO_TASK_COUNT` 时跳过 sprint-review；deployment 标 N/A）
2. 汇总沙盒产物清单（`docs/` 各文档、`docs/reviews/*`、`PROJECT-STATE`）与 `docs/EVENT-LOG.jsonl` 关键事件、任何错误/卡点的原始输出

### Step 6: 产出走查改进报告
1. 按观察点把问题归为 `framework` 与 `process` 两类，套 COMMON-RULES §问题格式（category / root_cause / severity / 描述含证据 / 建议）
2. 填路径覆盖账本：路径图 §2–§6 每条路径标 driven / probed / observed / not-reached(原因)，字段按 runtime-flow-map §7
3. 写 `docs/reviews/framework/FRAMEWORK-REVIEW-walkthrough-{YYYYMMDD}-r{N}.md`，首行 YAML front matter（id/doc_type/author/status/deps）；三态判定按 COMMON-RULES §三态判定逻辑；本 skill 默认不阻塞业务流程，仅产报告供维护决策

### Step 7: 清理与归档
1. 沙盒目录可整体删除（gitignored，不入仓）；如需保留证据，仅在报告内以路径+摘要引用
2. 报告留仓作为后续 framework-review / 演进决策的一手输入

## 效率策略
- 缺省 `agile-lite` + `temperature-converter` + `--depth smoke`：单轮闭环、确定性强、token 可控；要全路径覆盖时才升 `--depth full`
- 跨平台只换 `--platform`：沙盒部署与驱动协议不变，差异由 deployer 与降级策略吸收
- 与 framework-review 配合：本 skill 先动态跑出摩擦点，再用 framework-review 对命中的元资产做定点静态复核
