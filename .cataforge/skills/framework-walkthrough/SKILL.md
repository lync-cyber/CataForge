---
name: framework-walkthrough
description: "项目走查 — 在隔离沙盒中以指定执行模式把一个小型示例项目跑通整条 SDLC 工作流（需求→架构→TDD→评审→可选部署），观察各阶段/门禁/降级的真实行为，产出『框架本身 + 走查流程本身』两类改进建议。与 framework-review 形成动静对偶：后者静态审元资产，本 skill 动态端到端自测。当用户想验证一次框架部署是否真能跑通、为非 Claude-Code 平台做行为级冒烟、或自测 workflow-framework-generator 生成的框架时使用。"
argument-hint: "[--mode <agile-prototype|agile-lite|standard>] [--platform <claude-code|cursor|codex|opencode>] [--example <example_id>]"
suggested-tools: file_read, file_write, file_edit, file_glob, file_grep, shell_exec, agent_dispatch, user_question
depends: [start-orchestrator]
disable-model-invocation: false
user-invocable: true
---

# 项目走查 (framework-walkthrough)

## 能力边界
- 能做: 在隔离沙盒里部署目标平台资产并以指定执行模式驱动一个小型示例项目跑通端到端工作流；在每个阶段/门禁/降级处采集「观察点」；产出框架本身与走查流程本身两类改进建议报告；跨四端可移植（用能力标识符与 `cataforge` CLI 而非平台原生名）
- 不做: 修改被走查的真实项目资产或 `.cataforge/` 本体（仅在沙盒里跑、仅向 `docs/reviews/framework/` 产报告）；替代 framework-review 的静态元资产审查（互补，发现面不同）；替代 platform-audit 的 IDE 厂商对账；进入业务开发主循环（按需触发）

## 输入规范
- 可选 `--mode`: 执行模式，缺省 `agile-lite`（最能在单轮内触达 需求→架构→TDD→评审 主干）；语义见 COMMON-RULES §执行模式矩阵
- 可选 `--platform`: 目标平台，缺省取 `framework.json#/runtime.platform`
- 可选 `--example`: 示例目标 id，缺省内置 `temperature-converter`（见 [`references/example-project.md`](references/example-project.md)）；自带目标须小到单轮收敛
- 被走查的框架资产: 项目根 `.cataforge/`（必读）
- 详细执行协议: [`references/walkthrough-protocol.md`](references/walkthrough-protocol.md)；观察与归类口径: [`references/observation-rubric.md`](references/observation-rubric.md)

## 输出规范
- 走查改进报告: `docs/reviews/framework/FRAMEWORK-REVIEW-walkthrough-{YYYYMMDD}-r{N}.md`，front matter `doc_type: framework-review`（编号与字段按 COMMON-RULES §审查报告规范）
- 报告含两类 findings: `framework`（框架本身缺陷/摩擦）与 `process`（走查流程本身可改进项），各按 COMMON-RULES §统一问题分类体系 / §归因分类 / §问题格式 标注
- 沙盒运行产物: 留在 gitignored 沙盒目录供复核，不入仓；报告以「产物清单 + 关键证据」形式引用

## Anti-Patterns
- 禁止: 在宿主真实项目根直接驱动走查 — 会覆写真实 `docs/` / `PROJECT-STATE` / `EVENT-LOG` / KG store；应在 gitignored 沙盒目录内 `cataforge setup` 出独立项目后再起流程
- 禁止: 选过大的示例目标导致一轮收敛不了 — 如「做一个电商平台」；应小到单轮闭环（如温度转换 CLI），把验证重心放在工作流主干而非业务复杂度
- 禁止: 把改进建议写回被走查的 `.cataforge/` 资产本体 — 会污染单一事实来源；只产报告到 `docs/reviews/framework/`，框架修复交由后续 framework-review / 维护流程闭环
- 禁止: 只看「最终有没有产出文档」就结案 — 走查价值在过程中的门禁触发/降级是否静默/CLI 与 skill 是否报错等信号，事后无法补采；须按观察口径逐阶段记录
- 避免: 把本 skill 当 framework-review 的替代 — 静态审元资产用 framework-review，端到端跑用本 skill；二者互补不互斥

## 执行步骤

### Step 1: 准备隔离沙盒
1. 在 gitignored 沙盒目录（缺省 `walkthrough-sandbox/<run-id>/`，`<run-id>` = `<platform>-<mode>-<时间戳>`，时间戳取 `Get-Date -Format yyyyMMdd-HHmmss` / `date +%Y%m%d-%H%M%S`，保证并发/重跑各占独立目录）新建空项目目录；目标目录非空时另起新 run-id 或先 `--clean` 清空，非空目录直接复用会让两次走查互相写入对方产物、归因困难
2. 在沙盒 cwd 内 `cataforge setup --platform <platform>` 部署目标平台资产；确认 `framework.json#/version` 非占位符 `0.0.0-template`
3. 校验沙盒与宿主隔离：沙盒有独立的 `.cataforge/` 与空 `docs/`，后续所有写入均在沙盒 cwd 内

### Step 2: 选定示例目标
1. 缺省载入 `references/example-project.md` 的 `temperature-converter` 目标、功能项、架构契约与验收标准
2. 自带目标时按 references 的「示例目标合格性清单」自检（小到单轮收敛、能触达主干、确定性可验证）

### Step 3: 选定执行模式
1. 缺省 `agile-lite`：触达 需求→架构→TDD→评审 且单轮收敛；`agile-prototype` 更快更浅、`standard` 最全最重
2. 模式与阶段集合、文档产出、TDD 档位、门禁的对应见 COMMON-RULES §执行模式矩阵

### Step 4: 端到端驱动工作流
1. 在沙盒 cwd 内按 start-orchestrator 的角色假设起流程：主线程扮演 orchestrator，按 `ORCHESTRATOR-PROTOCOLS §Project Bootstrap` 推进
2. 逐阶段推进至 development 完成且评审通过；阶段转换处遵循 MANUAL_REVIEW_CHECKPOINTS（沙盒内可由走查者代答以保持单轮闭环）
3. 每跨一个阶段/门禁/降级即按 `references/observation-rubric.md` 记录观察点（产物是否生成、门禁是否如期触发、降级是否静默、CLI/skill/hook 是否报错、文档加载与 KG 分流是否正常）

### Step 5: 收集证据
1. 汇总沙盒产物清单（`docs/` 各文档、`docs/reviews/*`、`PROJECT-STATE`）
2. 抽取 `docs/EVENT-LOG.jsonl` 关键事件与任何错误/卡点的原始输出

### Step 6: 产出走查改进报告
1. 按观察点把问题归为 `framework` 与 `process` 两类，套 COMMON-RULES §问题格式（category / root_cause / severity / 描述含证据 / 建议）
2. 写 `docs/reviews/framework/FRAMEWORK-REVIEW-walkthrough-{YYYYMMDD}-r{N}.md`，首行 YAML front matter（id/doc_type/author/status/deps）
3. 三态判定按 COMMON-RULES §三态判定逻辑；本 skill 默认不阻塞业务流程，仅产报告供维护决策

### Step 7: 清理与归档
1. 沙盒目录可整体删除（gitignored，不入仓）；如需保留证据，仅在报告内以路径+摘要引用
2. 报告留仓作为后续 framework-review / 演进决策的一手输入

## 效率策略
- 缺省 `agile-lite` + `temperature-converter`：单轮闭环、确定性强、token 可控
- 跨平台只换 `--platform`：沙盒部署与驱动协议不变，差异由 deployer 与降级策略吸收
- 与 framework-review 配合：本 skill 先动态跑出摩擦点，再用 framework-review 对命中的元资产做定点静态复核
