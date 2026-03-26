# Orchestrator Protocols

> 协议快速定位 — 核心协议: Bootstrap, Interrupt-Resume, Revision, Approved-with-Notes, Rolled-back Recovery, TDD Blocked Recovery, Sprint Review, Change Request, Agent Crash Recovery, needs_revision 计数 | 学习协议: On-Correction Learning, Adaptive Review, Retrospective & Improvement | 模板: CLAUDE.md Update Template

---
# Part 1: 核心协议 (Core Protocols)
> 编排流程的核心生命周期管理。修改需谨慎。
---

## Project Bootstrap
当项目从零开始 (CLAUDE.md 不存在) 时:
1. **收集项目基本信息** — 向用户确认: 项目名称、技术栈、命名规范、Commit格式、分支策略
2. **创建目录结构**: `mkdir -p docs/{prd,arch,dev-plan,ui-spec,test-report,deploy-spec,research,changelog,reviews}`
3. **创建 CLAUDE.md** — 按下方 Update Template 生成，所有文档状态设为"未开始"，当前阶段设为 requirements
4. **写入框架版本** — 读取 pyproject.toml 的 `[project].version` 字段填入 CLAUDE.md `框架版本` 字段（如 pyproject.toml 不存在则标注"未追踪"）
5. **创建 docs/NAV-INDEX.md** — 生成空索引骨架
6. **进入 Phase 1** — 通过agent-dispatch激活 product-manager

## Interrupt-Resume Protocol
注: 前台子代理(默认)可直接使用AskUserQuestion向用户提问。本协议仅在后台子代理返回 needs_input 时触发。
当Agent返回 needs_input 状态时:
1. 从 `<agent-result>` 中提取 questions、intermediate-outputs、resume-guidance
2. 使用 AskUserQuestion 展示问题(每批最多3个，选择题优先)
3. 收集回答，组织为 `Q1: {问题} → A: {回答}` 格式
4. 通过 agent-dispatch 重新激活同一Agent (task_type=continuation)
5. 循环控制: 每Agent每阶段最多2轮interrupt-resume，第3轮请求人工介入

## Revision Protocol
当文档状态为 needs_revision 时:
1. 确认 docs/reviews/ 下存在对应 REVIEW 报告（取编号最大的 `-r{N}` 文件）
2. 通过 agent-dispatch 调度原Agent (task_type=revision)，传递REVIEW报告路径
3. Agent按 COMMON-RULES.md Revision Protocol 执行增量修复
4. 修复完成后重新激活 reviewer 执行门禁
5. 更新返工计数: needs_revision(N)

## Approved-with-Notes Protocol
当 reviewer 返回 approved_with_notes 时:
1. 从 REVIEW 报告中提取 MEDIUM/LOW 问题列表
2. 使用 AskUserQuestion 向用户展示问题摘要，提供选项:
   - "接受并继续": 将文档状态变更为 approved，进入下一 Phase
   - "要求修复选中的问题": 将用户选中的问题标记为待修复，文档状态变更为 needs_revision，进入 Revision Protocol
3. 用户选择"接受"时，MEDIUM/LOW 问题记录保留在 REVIEW 报告中供后续参考

## Rolled-back Recovery Protocol
当 TDD REFACTOR 子代理返回 `rolled-back` 状态时:
1. 使用 GREEN 阶段产出（impl_files）作为最终产出，跳过重构结果
2. 在 code-review 时标记 MEDIUM 级别问题: "REFACTOR rolled-back，代码质量待后续优化"
3. 不自动重试 REFACTOR，不阻塞后续任务
4. 记录到 dev-plan 对应任务的备注中

## TDD Blocked Recovery Protocol
当 TDD 子代理返回 blocked 且含 `<questions>` 字段时:
1. 提取 questions 列表
2. 使用 AskUserQuestion 向用户展示（每批最多3个，选择题优先）
3. 以 continuation 模式重启同一子代理，传入答案
4. 每阶段最多 1 轮 Blocked Recovery，第 2 次 blocked 请求人工介入

## Sprint Review Protocol
当Sprint所有任务完成（dev-plan§1 Sprint表中所有任务状态=done 且 code-review通过）时:
1. 通过 agent-dispatch 激活 reviewer (task_type=new_creation, skill=sprint-review)
2. 传入: dev-plan路径, Sprint编号, 所有CODE-REVIEW报告路径, arch文档路径
3. reviewer执行sprint-review skill，产出 `SPRINT-REVIEW-s{N}-r{M}.md`
4. 结果处理:
   - **approved** → 更新CLAUDE.md Sprint字段，进入下一Sprint（或全部Sprint完成后进入Phase 6）
   - **approved_with_notes** → 按 Approved-with-Notes Protocol 处理
   - **needs_revision** → 从SPRINT-REVIEW报告中提取标记为CRITICAL/HIGH的任务ID，仅这些任务重新进入TDD（已通过的任务保持done状态不变）
5. Sprint Review的needs_revision不计入Phase级needs_revision计数（独立跟踪）

## Change Request Protocol
当orchestrator检测到用户输入为变更请求（而非流程推进指令）时:
1. 通过 change-guard skill 分析变更（orchestrator直接执行，无需agent-dispatch）
2. 向用户展示 `<change-analysis>` 结果，提供选项:
   - "确认执行": 按action路由执行
   - "调整范围": 用户修改变更描述后重新分析
   - "取消": 不执行变更
3. 根据 action 路由:
   - **proceed** → 直接在当前阶段执行变更（不触发文档修订）
   - **amend_then_proceed** → 通过agent-dispatch调度affected_docs的原作者Agent(task_type=amendment)修订文档，每个文档修订后经reviewer审核，全部通过后执行变更
   - **cascade_amendment** → 从最上游affected doc开始逐级修订: PRD → ARCH → UI-SPEC(如适用) → DEV-PLAN，每级修订+审核后才进入下级

### cascade_amendment 中断规则
cascade_amendment 中任一文档修订失败(needs_revision ≥ 3):
1. 暂停后续文档修订，不继续下游文档
2. 已修订的上游文档保持 draft 状态（不标记 approved）
3. 向用户报告失败点和已完成的修订范围，提供选项:
   - "继续修复失败文档": 进入 Revision Protocol 修复当前文档
   - "回滚所有修订": `git checkout -- docs/{affected_dirs}` 恢复所有本轮修订的文档
4. 回滚后变更请求状态重置，用户可调整范围后重新提交

4. 变更完成后回到原阶段继续执行
5. Amendment 与 Revision 的区别: Revision由reviewer发起（修复问题），Amendment由用户发起（适应变更），但执行机制复用agent-dispatch和reviewer审核流程

## Framework Upgrade Protocol
框架升级时保持项目状态不变:

### 可安全覆盖（框架文件）
- .claude/agents/ — 所有 AGENT.md
- .claude/skills/ — 所有 SKILL.md + templates/ + scripts/
- .claude/rules/ — COMMON-RULES.md, ORCHESTRATOR-PROTOCOLS.md
- .claude/hooks/ — 所有 Hook 脚本 (.py)
- .claude/scripts/ — upgrade.py, check-upgrade.py, post_upgrade_check.py, setup-penpot-mcp.sh 等框架工具脚本
- .claude/compat-matrix.json
- pyproject.toml

### 绝不触碰（项目数据）
- CLAUDE.md 的 "项目状态" 段
- docs/ 目录下所有文档
- src/ 目录下所有代码
- .claude/learnings/ 下的经验文件

### 需要合并（混合文件）
- .claude/settings.json — 保留项目 env、自定义 permissions、用户独有 mcpServers
- .claude/upgrade-source.json — 保留用户已配置的 repo/url，仅补充新字段
- CLAUDE.md 全局约定 — 保留用户已填写的值，新增框架默认字段

### 升级步骤（本地路径方式）
1. 运行: `python .claude/scripts/upgrade.py <新版CataForge路径> --dry-run`
2. 确认变更列表无异常
3. 运行: `python .claude/scripts/upgrade.py <新版CataForge路径>`
3.5. upgrade.py 自动运行 `post_upgrade_check.py`，检查新功能状态和文件完整性
4. 检查: `git diff .claude/` 确认变更合理
5. 提交: `git commit -m "chore: upgrade CataForge framework to vX.Y.Z"`

### 升级步骤（远程拉取方式）
1. 配置 `.claude/upgrade-source.json`（设置 type/repo/url/branch）
2. 运行: `python .claude/scripts/check-upgrade.py --check` 检测新版本
3. 运行: `python .claude/scripts/check-upgrade.py --dry-run` 预览变更
4. 运行: `python .claude/scripts/check-upgrade.py --apply` 执行升级
5. 检查: `git diff .claude/` 确认变更合理
6. 提交: `git commit -m "chore: upgrade CataForge framework to vX.Y.Z"`

## Agent Crash Recovery Protocol
当子代理返回结果不含 `<agent-result>` 标签且 agent-dispatch 的标签缺失兜底也无法推断状态时（即真正的崩溃/截断场景）:
1. 通过 `git status docs/ src/` 检查是否有本次调度后的新增或修改文件
2. 向用户展示崩溃信息和部分产出情况，提供选项:
   - "从部分产出继续": 以 continuation 模式重新调度同一Agent，传入已有产出路径
   - "从头重试": 以 new_creation 模式重新调度同一Agent（先 `git checkout -- docs/{相关目录}` 清理部分产出）
   - "跳过此阶段": 仅在非关键路径阶段可用，标记阶段为 blocked 并请求人工后续处理
3. 每Agent每阶段最多 1 次 Crash Recovery，第 2 次崩溃请求人工介入
4. 崩溃事件记录到 CORRECTIONS-LOG.md 供 reflector 分析

## needs_revision 计数规范
`needs_revision(N)` 中的 N 为本阶段累计返工次数，格式为 `needs_revision(2)` 而非独立字段。
- N=1: 正常修订流程
- N>=2: 触发 Adaptive Review Protocol
- N>=3: 暂停自动推进，请求人工介入

---
# Part 2: 学习协议 (Learning Protocols)
> 自学习反思机制。聚焦三个高价值触发场景。
---

## On-Correction Learning Protocol
触发条件: Interrupt-Resume 过程中用户回答推翻了 agent 的 [ASSUMPTION]
执行者: orchestrator
步骤:
1. 对比 agent 原始 [ASSUMPTION] 内容与用户实际回答
2. 如果存在明显偏差（用户选择了 agent 未预期的选项），追加记录到 docs/reviews/CORRECTIONS-LOG.md：
   ```
   ### {date} | {agent_id} | {phase}
   - 原假设: {assumption content}
   - 用户决策: {user answer}
   - 偏差类型: {preference|constraint|domain-knowledge}
   ```
3. CORRECTIONS-LOG.md 为追加写入，不覆盖
4. 项目结束时，reflector 在 Retrospective & Improvement 中将此文件作为额外输入源

## Adaptive Review Protocol
触发条件: 任一文档达到 needs_revision(N>=2)
执行者: orchestrator 自身（不启动子代理）
步骤:
1. 扫描 docs/reviews/ 下当前阶段的 REVIEW 文件（含 -r{N} 归档版本），提取 root_cause=self-caused 的问题按 category 聚合
2. 同一 category >=2 次 → 在下次 agent-dispatch 调度同一 Agent 时注入临时提示：
   ```
   === 本项目已识别的反复问题 ===
   - {category}: {问题描述}，已出现{N}次
   ```

## Retrospective & Improvement Protocol
触发条件: 所有 Phase 完成后执行一次（不阻塞项目交付）
步骤:
1. 检查 docs/reviews/ 下 REVIEW 文件数量 ≥ MIN_REVIEW_SOURCES (见 COMMON-RULES §框架配置常量)，否则跳过
2. 通过 agent-dispatch 激活 reflector (task_type=retrospective)
3. reflector 产出 docs/reviews/RETRO-{project}-{ver}.md（含 EXP 经验条目和改进建议）
4. orchestrator 向用户展示 RETRO 报告中的改进建议
5. 用户审批后，通过 agent-dispatch 激活 reflector (task_type=skill-improvement)，传入审批通过的 EXP 条目
6. reflector 产出 docs/reviews/SKILL-IMPROVE-{skill_id}.md（含具体 Agent/Skill 文件修改建议）
7. 用户确认后执行修改，git commit，message 格式: `learn: apply EXP-{NNN} to {target_file}`
8. 如果 reflector 返回 blocked 或失败，仅记录日志，不影响项目完成状态

## CLAUDE.md Update Template
每次阶段转换时更新:
```
## 项目状态 (orchestrator专属写入区，其他Agent禁止修改)
- 当前阶段: {phase_name}
- 上次完成: {agent目录名} — {完成的工作描述}
- 下一步行动: {具体的下一步}
- 已完成阶段: [{阶段列表}]
- 当前Sprint: {Sprint编号，非DEV阶段填 —}
- 文档状态:
  - prd: {状态}
  - arch: {状态}
  - ui-spec: {状态}
  - dev-plan: {状态}
  - test-report: {状态}
  - deploy-spec: {状态}
  <!-- changelog 由 devops 产出但不纳入门禁追踪 -->
```
<!-- 状态值: 未开始 | draft | review | approved | needs_revision | needs_revision(N) | N/A -->
