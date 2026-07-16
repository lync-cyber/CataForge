# Orchestrator Recovery Protocols

> 异常路径协议族——仅在命中触发征兆时按需加载（触发索引见
> [`ORCHESTRATOR-PROTOCOLS.md`](ORCHESTRATOR-PROTOCOLS.md) §Recovery Protocols 触发索引）。

## Rolled-back Recovery Protocol
当 TDD REFACTOR 子代理返回 `rolled-back` 状态时:
1. **[EVENT]** 记录异常事件:
   ```bash
   cataforge event log --event incident --phase development --status rolled-back --detail "REFACTOR rolled-back，使用 GREEN 产出"
   ```
2. 使用 GREEN 阶段产出（impl_files）作为最终产出，跳过重构结果
3. 在 code-review 时标记 MEDIUM 级别问题: "REFACTOR rolled-back，代码质量待后续优化"
4. 不自动重试 REFACTOR，不阻塞后续任务
5. 记录到 dev-plan 对应任务的备注中

## TDD Blocked Recovery Protocol
当 TDD 子代理返回 blocked 且含 `<questions>` 字段时:
1. 提取 questions 列表
2. 使用 AskUserQuestion 向用户展示（见 COMMON-RULES §MAX_QUESTIONS_PER_BATCH，选择题优先）
3. 以 continuation 模式重启同一子代理，传入答案
4. 每阶段最多 1 轮 Blocked Recovery，第 2 次 blocked 请求人工介入

## Agent Crash Recovery Protocol
当子代理返回结果不含 `<agent-result>` 标签且 agent-dispatch 的标签缺失兜底也无法推断状态时（即真正的崩溃/截断场景）:
1. 通过 `git status docs/ src/` 检查是否有本次调度后的新增或修改文件
2. 向用户展示崩溃信息和部分产出情况，提供选项:
   - "从部分产出继续": 以 continuation 模式重新调度同一Agent，传入已有产出路径
   - "从头重试": 以 new_creation 模式重新调度同一Agent（先 `git checkout -- docs/{相关目录}` 清理部分产出）
   - "跳过此阶段": 仅在非关键路径阶段可用，标记阶段为 blocked 并请求人工后续处理
3. 每Agent每阶段最多 1 次 Crash Recovery，第 2 次崩溃请求人工介入
4. 崩溃事件记录到 docs/reviews/CORRECTIONS-LOG.md 供 reflector 分析

> **与 §Sub-Agent Truncation Recovery 的区分**：本协议针对 process 死（无任何输出 / agent-dispatch 端兜底无法推断状态）。
> task-notification truncation 是另一回事 —— 子代理走完全程但 token budget 耗尽，artifact 已部分落地，仅
> `<agent-result>` JSON 没回。后者由下一节专门处理。

## Sub-Agent Truncation Recovery Protocol

当子代理被 task-notification truncation 打断（征兆：100+ tools / 100K+ tokens / 5min+ / `<agent-result>`
缺失，但 `git status` 显示已有未提交 artifact），主线程**接管收尾**而非 blocked：

1. **评估完成度**（按任务类型选 1-2 项）：代码任务跑 `{test_command}` 看 PASS 率 + `biome lint` / `ruff check` /
   `tsc --noEmit` 看类型/lint 错数；文档任务核对 deliverables 齐全 + frontmatter 完整
2. **决策**：
   - **≥ 70% AC PASS（或 deliverables 齐全）** → 主线程接管：inline-fix 残留 lint/typecheck 错 + 补落盘缺漏 + 补
     `<agent-result>` 等价信息到 EVENT-LOG（`event=state_change`，`detail="truncation recovery: main-thread takeover"`）
   - **< 70%** → blocked，请求人工介入（不允许从零接管，成本不可控）
   - **无任何 artifact** → 走 §Agent Crash Recovery（process 死，本协议不适用）
3. **每任务最多 1 次**；第 2 次截断说明 prompt 设计有问题，blocked + 标 backlog 给下次 retrospective
4. 事件记录：`event=state_change` + `agent={truncated_agent_id}` +
   `detail="truncation recovery: <70%|≥70%>"`，供 reflector 检测频次（≥5 次/月触发 SKILL-IMPROVE）

**与 tdd-engine §Mid-Progress Drop Contract 的关系**：mid-progress 是**预防**（边推进边落盘）；本协议是**事后兜底**。
